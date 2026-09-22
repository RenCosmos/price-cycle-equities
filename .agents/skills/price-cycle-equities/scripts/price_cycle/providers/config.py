from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tomllib

from ..models import Market
from .base import DataAssuranceMode


CONFIG_SCHEMA_VERSION = 1
MAX_CONFIG_BYTES = 256 * 1024
_PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_CREDENTIAL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ENVIRONMENT_VARIABLE_PATTERN = re.compile(
    r"^PRICE_CYCLE_[A-Z][A-Z0-9_]{1,79}$"
)
_DATA_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ProviderConfigError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class CredentialUnavailableError(RuntimeError):
    def __init__(self, environment_variable: str) -> None:
        super().__init__(
            "Credential environment variable is unavailable: "
            + environment_variable
        )
        self.code = "CREDENTIAL_ENV_MISSING"
        self.environment_variable = environment_variable


class ProviderAccessMode(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


@dataclass(frozen=True, slots=True)
class CredentialSpec:
    name: str
    environment_variable: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _CREDENTIAL_NAME_PATTERN.fullmatch(
            self.name
        ):
            raise ValueError("Invalid credential name")
        if not isinstance(
            self.environment_variable,
            str,
        ) or not _ENVIRONMENT_VARIABLE_PATTERN.fullmatch(self.environment_variable):
            raise ValueError(
                "Credential environment variables must begin with PRICE_CYCLE_"
            )


TUSHARE_TOKEN_SPEC = CredentialSpec(
    "token",
    "PRICE_CYCLE_TUSHARE_TOKEN",
)


class SecretValue:
    """A deliberately non-serializable wrapper for a resolved credential."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Secret value cannot be blank")
        self._value = value

    def reveal(self) -> str:
        """Return the value only at the provider request boundary."""

        return self._value

    def __repr__(self) -> str:
        return "<SecretValue [REDACTED]>"

    def __str__(self) -> str:
        return "[REDACTED]"

    def __reduce_ex__(self, protocol: int) -> object:
        del protocol
        raise TypeError("SecretValue cannot be serialized")


class EnvironmentCredentialResolver:
    __slots__ = ("_environment",)

    def __init__(
        self,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if environment is not None and not isinstance(environment, Mapping):
            raise ValueError("Credential environment must be a mapping")
        self._environment = os.environ if environment is None else environment

    def is_available(self, spec: CredentialSpec) -> bool:
        value = self._environment.get(spec.environment_variable)
        return isinstance(value, str) and bool(value.strip())

    def resolve(self, spec: CredentialSpec) -> SecretValue:
        value = self._environment.get(spec.environment_variable)
        if not isinstance(value, str) or not value.strip():
            raise CredentialUnavailableError(spec.environment_variable)
        return SecretValue(value)

    def __repr__(self) -> str:
        return "<EnvironmentCredentialResolver>"

    def __reduce_ex__(self, protocol: int) -> object:
        del protocol
        raise TypeError("EnvironmentCredentialResolver cannot be serialized")


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider_id: str
    assurance_mode: DataAssuranceMode
    access_mode: ProviderAccessMode
    implemented: bool
    credentials: tuple[CredentialSpec, ...]
    supported_markets: tuple[Market, ...]
    data_kinds: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.provider_id,
            str,
        ) or not _PROVIDER_ID_PATTERN.fullmatch(self.provider_id):
            raise ValueError("Invalid provider descriptor ID")
        if not isinstance(self.assurance_mode, DataAssuranceMode):
            raise ValueError("Invalid provider assurance mode")
        if not isinstance(self.access_mode, ProviderAccessMode):
            raise ValueError("Invalid provider access mode")
        if type(self.implemented) is not bool:
            raise ValueError("Provider implemented flag must be boolean")
        if not isinstance(self.credentials, tuple) or any(
            not isinstance(item, CredentialSpec) for item in self.credentials
        ):
            raise ValueError("Provider credentials must be CredentialSpec values")
        credential_names = tuple(item.name for item in self.credentials)
        if len(credential_names) != len(set(credential_names)):
            raise ValueError("Provider credential names must be unique")
        credential_variables = tuple(
            item.environment_variable for item in self.credentials
        )
        if len(credential_variables) != len(set(credential_variables)):
            raise ValueError("Provider credential environment variables must be unique")
        if not isinstance(self.supported_markets, tuple) or not self.supported_markets:
            raise ValueError("Provider descriptor must support a market")
        if any(not isinstance(item, Market) for item in self.supported_markets):
            raise ValueError("Provider descriptor contains an invalid market")
        if len(self.supported_markets) != len(set(self.supported_markets)):
            raise ValueError("Provider markets must be unique")
        if not isinstance(self.data_kinds, tuple) or not self.data_kinds:
            raise ValueError("Provider descriptor must support a data kind")
        if len(self.data_kinds) != len(set(self.data_kinds)):
            raise ValueError("Provider data kinds must be unique")
        if any(
            not isinstance(data_kind, str)
            or not _DATA_KIND_PATTERN.fullmatch(data_kind)
            for data_kind in self.data_kinds
        ):
            raise ValueError("Invalid provider data kind")


class ProviderCatalog:
    def __init__(self, descriptors: tuple[ProviderDescriptor, ...]) -> None:
        if not isinstance(descriptors, tuple) or not descriptors:
            raise ValueError("Provider catalog cannot be empty")
        if any(not isinstance(item, ProviderDescriptor) for item in descriptors):
            raise ValueError("Provider catalog contains an invalid descriptor")
        self._descriptors = {
            descriptor.provider_id: descriptor for descriptor in descriptors
        }
        if len(self._descriptors) != len(descriptors):
            raise ValueError("Provider catalog contains duplicate IDs")

    def get(self, provider_id: str) -> ProviderDescriptor | None:
        return self._descriptors.get(provider_id)

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    @property
    def data_kinds(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    data_kind
                    for descriptor in self._descriptors.values()
                    for data_kind in descriptor.data_kinds
                }
            )
        )


DEFAULT_PROVIDER_CATALOG = ProviderCatalog(
    (
        ProviderDescriptor(
            provider_id="manual_csv",
            assurance_mode=DataAssuranceMode.USER_SUPPLIED_UNVERIFIED,
            access_mode=ProviderAccessMode.LOCAL,
            implemented=True,
            credentials=(),
            supported_markets=(Market.CN, Market.US),
            data_kinds=("daily_bars",),
        ),
        ProviderDescriptor(
            provider_id="tushare",
            assurance_mode=DataAssuranceMode.PROVIDER_VERIFIED,
            access_mode=ProviderAccessMode.REMOTE,
            implemented=False,
            credentials=(TUSHARE_TOKEN_SPEC,),
            supported_markets=(Market.CN,),
            data_kinds=("daily_bars",),
        ),
        ProviderDescriptor(
            provider_id="eodhd",
            assurance_mode=DataAssuranceMode.PROVIDER_VERIFIED,
            access_mode=ProviderAccessMode.REMOTE,
            implemented=False,
            credentials=(
                CredentialSpec("token", "PRICE_CYCLE_EODHD_TOKEN"),
            ),
            supported_markets=(Market.CN, Market.US),
            data_kinds=("daily_bars",),
        ),
    )
)


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    provider_id: str
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(
            self.provider_id,
            str,
        ) or not _PROVIDER_ID_PATTERN.fullmatch(self.provider_id):
            raise ValueError("Invalid provider ID")
        if type(self.enabled) is not bool:
            raise ValueError("Provider enabled flag must be boolean")


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    data_kind: str
    market: Market
    provider_order: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.data_kind,
            str,
        ) or not _DATA_KIND_PATTERN.fullmatch(self.data_kind):
            raise ValueError("Invalid route data kind")
        if not isinstance(self.market, Market):
            raise ValueError("Invalid route market")
        if not isinstance(self.provider_order, tuple) or not self.provider_order:
            raise ValueError("Provider route cannot be empty")
        if len(self.provider_order) != len(set(self.provider_order)):
            raise ValueError("Provider route cannot contain duplicate IDs")
        if any(
            not isinstance(provider_id, str)
            or not _PROVIDER_ID_PATTERN.fullmatch(provider_id)
            for provider_id in self.provider_order
        ):
            raise ValueError("Provider route contains an invalid ID")


@dataclass(frozen=True, slots=True)
class ProviderConfiguration:
    schema_version: int
    allow_network: bool
    providers: tuple[ProviderSettings, ...]
    routes: tuple[ProviderRoute, ...]
    catalog: ProviderCatalog = DEFAULT_PROVIDER_CATALOG

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int:
            raise ProviderConfigError(
                "Provider config schema version must be an integer",
                code="CONFIG_SCHEMA_INVALID",
            )
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise ProviderConfigError(
                "Unsupported provider config schema version",
                code="CONFIG_SCHEMA_UNSUPPORTED",
            )
        if type(self.allow_network) is not bool:
            raise ProviderConfigError(
                "Provider config network flag must be boolean",
                code="CONFIG_NETWORK_FLAG_INVALID",
            )
        if not isinstance(self.catalog, ProviderCatalog):
            raise ProviderConfigError(
                "Provider config catalog is invalid",
                code="CONFIG_CATALOG_INVALID",
            )
        if not isinstance(self.providers, tuple) or not self.providers or any(
            not isinstance(item, ProviderSettings) for item in self.providers
        ):
            raise ProviderConfigError(
                "Provider configuration must contain provider settings",
                code="CONFIG_PROVIDERS_INVALID",
            )
        if not isinstance(self.routes, tuple) or not self.routes or any(
            not isinstance(item, ProviderRoute) for item in self.routes
        ):
            raise ProviderConfigError(
                "Provider configuration must contain routes",
                code="CONFIG_ROUTES_INVALID",
            )
        provider_ids = tuple(item.provider_id for item in self.providers)
        if len(provider_ids) != len(set(provider_ids)):
            raise ProviderConfigError(
                "Provider configuration contains duplicate IDs",
                code="DUPLICATE_PROVIDER",
            )
        route_keys = tuple((route.data_kind, route.market) for route in self.routes)
        if len(route_keys) != len(set(route_keys)):
            raise ProviderConfigError(
                "Provider configuration contains duplicate routes",
                code="DUPLICATE_ROUTE",
            )
        settings_by_id = {item.provider_id: item for item in self.providers}
        for settings in self.providers:
            descriptor = self.catalog.get(settings.provider_id)
            if descriptor is None:
                raise ProviderConfigError(
                    "Provider configuration contains an unknown provider ID",
                    code="UNKNOWN_PROVIDER",
                )
            if settings.enabled and not descriptor.implemented:
                raise ProviderConfigError(
                    "Provider is enabled but not implemented: "
                    + settings.provider_id,
                    code="PROVIDER_NOT_AVAILABLE",
                )
        for route in self.routes:
            for provider_id in route.provider_order:
                settings = settings_by_id.get(provider_id)
                descriptor = self.catalog.get(provider_id)
                if settings is None or descriptor is None:
                    raise ProviderConfigError(
                        "Route references an unknown provider ID",
                        code="UNKNOWN_PROVIDER",
                    )
                if not settings.enabled:
                    raise ProviderConfigError(
                        f"Route references disabled provider: {provider_id}",
                        code="ROUTE_PROVIDER_DISABLED",
                    )
                if route.market not in descriptor.supported_markets:
                    raise ProviderConfigError(
                        f"Provider does not support market {route.market.value}: "
                        f"{provider_id}",
                        code="PROVIDER_MARKET_UNSUPPORTED",
                    )
                if route.data_kind not in descriptor.data_kinds:
                    raise ProviderConfigError(
                        f"Provider does not support data kind {route.data_kind}: "
                        f"{provider_id}",
                        code="PROVIDER_DATA_KIND_UNSUPPORTED",
                    )
                if (
                    descriptor.access_mode is ProviderAccessMode.REMOTE
                    and not self.allow_network
                ):
                    raise ProviderConfigError(
                        "A remote provider is routed while allow_network=false",
                        code="NETWORK_DISABLED",
                    )

    def provider(self, provider_id: str) -> ProviderSettings | None:
        for settings in self.providers:
            if settings.provider_id == provider_id:
                return settings
        return None

    def route_for(
        self,
        data_kind: str,
        market: Market,
    ) -> tuple[str, ...] | None:
        for route in self.routes:
            if route.data_kind == data_kind and route.market is market:
                return route.provider_order
        return None

    @property
    def fingerprint(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "allow_network": self.allow_network,
            "providers": [
                {
                    "provider_id": settings.provider_id,
                    "enabled": settings.enabled,
                }
                for settings in sorted(
                    self.providers,
                    key=lambda item: item.provider_id,
                )
            ],
            "routes": [
                {
                    "data_kind": route.data_kind,
                    "market": route.market.value,
                    "provider_order": list(route.provider_order),
                }
                for route in sorted(
                    self.routes,
                    key=lambda item: (item.data_kind, item.market.value),
                )
            ],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def public_summary(
        self,
        *,
        check_credentials: bool = False,
        resolver: EnvironmentCredentialResolver | None = None,
    ) -> dict[str, object]:
        selected_resolver = resolver
        if check_credentials and selected_resolver is None:
            selected_resolver = EnvironmentCredentialResolver()
        providers = []
        for settings in sorted(
            self.providers,
            key=lambda item: item.provider_id,
        ):
            descriptor = self.catalog.get(settings.provider_id)
            if descriptor is None:
                continue
            credentials = []
            for spec in descriptor.credentials:
                if not settings.enabled:
                    status = "disabled"
                elif not check_credentials:
                    status = "not_checked"
                elif selected_resolver is not None and selected_resolver.is_available(
                    spec
                ):
                    status = "available"
                else:
                    status = "missing"
                credentials.append(
                    {
                        "name": spec.name,
                        "environment_variable": spec.environment_variable,
                        "status": status,
                    }
                )
            providers.append(
                {
                    "provider_id": settings.provider_id,
                    "enabled": settings.enabled,
                    "implemented": descriptor.implemented,
                    "access_mode": descriptor.access_mode.value,
                    "assurance_mode": descriptor.assurance_mode.value,
                    "credentials": credentials,
                }
            )
        return {
            "schema_version": self.schema_version,
            "allow_network": self.allow_network,
            "fingerprint": self.fingerprint,
            "providers": providers,
            "routes": [
                {
                    "data_kind": route.data_kind,
                    "market": route.market.value,
                    "provider_order": list(route.provider_order),
                }
                for route in sorted(
                    self.routes,
                    key=lambda item: (item.data_kind, item.market.value),
                )
            ],
        }

    def missing_enabled_credentials(
        self,
        resolver: EnvironmentCredentialResolver,
    ) -> tuple[str, ...]:
        missing = []
        for settings in self.providers:
            if not settings.enabled:
                continue
            descriptor = self.catalog.get(settings.provider_id)
            if descriptor is None:
                continue
            for spec in descriptor.credentials:
                if not resolver.is_available(spec):
                    missing.append(spec.environment_variable)
        return tuple(sorted(set(missing)))


def _reject_unknown_keys(
    table: Mapping[str, object],
    allowed: set[str],
    *,
    location: str,
) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ProviderConfigError(
            f"Unknown key in {location}",
            code="CONFIG_UNKNOWN_KEY",
        )


def _load_toml_document(path: Path) -> dict[str, object]:
    read_error: ProviderConfigError | None = None
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        read_error = ProviderConfigError(
            "The explicitly selected provider config file was not found",
            code="CONFIG_NOT_FOUND",
        )
    except OSError:
        read_error = ProviderConfigError(
            "The explicitly selected provider config file could not be read",
            code="CONFIG_UNREADABLE",
        )
    if read_error is not None:
        raise read_error
    if len(raw) > MAX_CONFIG_BYTES:
        raise ProviderConfigError(
            "Provider config file exceeds the size limit",
            code="CONFIG_TOO_LARGE",
        )
    decode_error: ProviderConfigError | None = None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        decode_error = ProviderConfigError(
            "Provider config must use UTF-8",
            code="CONFIG_ENCODING_INVALID",
        )
    if decode_error is not None:
        raise decode_error
    parse_error: ProviderConfigError | None = None
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        parse_error = ProviderConfigError(
            "Provider config is not valid TOML",
            code="CONFIG_TOML_INVALID",
        )
    if parse_error is not None:
        raise parse_error
    return document


def _parse_provider_settings(
    provider_table: object,
    *,
    catalog: ProviderCatalog,
) -> tuple[ProviderSettings, ...]:
    if not isinstance(provider_table, dict) or not provider_table:
        raise ProviderConfigError(
            "providers must be a non-empty table",
            code="CONFIG_PROVIDERS_INVALID",
        )
    parsed: list[ProviderSettings] = []
    for provider_id, raw_settings in provider_table.items():
        if catalog.get(provider_id) is None:
            raise ProviderConfigError(
                "Provider configuration contains an unknown provider ID",
                code="UNKNOWN_PROVIDER",
            )
        if not isinstance(raw_settings, dict):
            raise ProviderConfigError(
                f"Provider settings must be a table: {provider_id}",
                code="PROVIDER_SETTINGS_INVALID",
            )
        _reject_unknown_keys(
            raw_settings,
            {"enabled"},
            location=f"providers.{provider_id}",
        )
        enabled = raw_settings.get("enabled", False)
        if type(enabled) is not bool:
            raise ProviderConfigError(
                f"Provider enabled flag must be true or false: {provider_id}",
                code="PROVIDER_ENABLED_INVALID",
            )
        parsed.append(ProviderSettings(provider_id, enabled))
    return tuple(sorted(parsed, key=lambda item: item.provider_id))


def _parse_routes(
    routes_table: object,
    *,
    catalog: ProviderCatalog,
) -> tuple[ProviderRoute, ...]:
    if not isinstance(routes_table, dict) or not routes_table:
        raise ProviderConfigError(
            "routes must be a non-empty table",
            code="CONFIG_ROUTES_INVALID",
        )
    routes: list[ProviderRoute] = []
    for data_kind, market_table in routes_table.items():
        if data_kind not in catalog.data_kinds:
            raise ProviderConfigError(
                "Provider configuration contains an unsupported data kind",
                code="ROUTE_DATA_KIND_UNKNOWN",
            )
        if not isinstance(market_table, dict) or not market_table:
            raise ProviderConfigError(
                f"Route must contain one or more markets: {data_kind}",
                code="ROUTE_MARKETS_INVALID",
            )
        for market_name, raw_order in market_table.items():
            market_error: ProviderConfigError | None = None
            try:
                market = Market(market_name.upper())
            except (AttributeError, ValueError):
                market_error = ProviderConfigError(
                    "Provider configuration contains an unknown market",
                    code="ROUTE_MARKET_UNKNOWN",
                )
            if market_error is not None:
                raise market_error
            if not isinstance(raw_order, list) or not raw_order:
                raise ProviderConfigError(
                    f"Provider order must be a non-empty array: "
                    f"{data_kind}.{market.value}",
                    code="ROUTE_ORDER_INVALID",
                )
            if any(not isinstance(item, str) for item in raw_order):
                raise ProviderConfigError(
                    f"Provider order must contain provider IDs: "
                    f"{data_kind}.{market.value}",
                    code="ROUTE_ORDER_INVALID",
                )
            if any(
                not _PROVIDER_ID_PATTERN.fullmatch(item) for item in raw_order
            ):
                raise ProviderConfigError(
                    "Provider order contains an invalid provider ID",
                    code="ROUTE_ORDER_INVALID",
                )
            if len(raw_order) != len(set(raw_order)):
                raise ProviderConfigError(
                    f"Provider route contains duplicates: "
                    f"{data_kind}.{market.value}",
                    code="DUPLICATE_PROVIDER",
                )
            routes.append(
                ProviderRoute(
                    data_kind=data_kind,
                    market=market,
                    provider_order=tuple(raw_order),
                )
            )
    return tuple(
        sorted(routes, key=lambda item: (item.data_kind, item.market.value))
    )


def load_provider_config(
    path: str | Path,
    *,
    catalog: ProviderCatalog = DEFAULT_PROVIDER_CATALOG,
) -> ProviderConfiguration:
    document = _load_toml_document(Path(path))
    _reject_unknown_keys(
        document,
        {"schema_version", "allow_network", "providers", "routes"},
        location="root",
    )
    schema_version = document.get("schema_version")
    if type(schema_version) is not int:
        raise ProviderConfigError(
            "schema_version must be an integer",
            code="CONFIG_SCHEMA_INVALID",
        )
    if schema_version != CONFIG_SCHEMA_VERSION:
        raise ProviderConfigError(
            "Unsupported provider config schema version",
            code="CONFIG_SCHEMA_UNSUPPORTED",
        )
    allow_network = document.get("allow_network", False)
    if type(allow_network) is not bool:
        raise ProviderConfigError(
            "allow_network must be true or false",
            code="CONFIG_NETWORK_FLAG_INVALID",
        )
    return ProviderConfiguration(
        schema_version=schema_version,
        allow_network=allow_network,
        providers=_parse_provider_settings(
            document.get("providers"),
            catalog=catalog,
        ),
        routes=_parse_routes(document.get("routes"), catalog=catalog),
        catalog=catalog,
    )
