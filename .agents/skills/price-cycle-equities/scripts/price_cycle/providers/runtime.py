from __future__ import annotations

from ..models import Market
from .base import ProviderRegistry
from .config import (
    EnvironmentCredentialResolver,
    ProviderAccessMode,
    ProviderConfiguration,
)
from .eodhd import EodhdDailyProvider, EodhdTransport


class ProviderRuntimeError(RuntimeError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def build_remote_registry(
    configuration: ProviderConfiguration,
    *,
    credential_resolver: EnvironmentCredentialResolver | None = None,
    eodhd_transport: EodhdTransport | None = None,
) -> ProviderRegistry:
    if not configuration.allow_network:
        raise ProviderRuntimeError(
            "Remote analysis requires allow_network=true in the explicit config",
            "NETWORK_DISABLED",
        )
    resolver = credential_resolver or EnvironmentCredentialResolver()
    providers = []
    for settings in configuration.providers:
        if not settings.enabled:
            continue
        descriptor = configuration.catalog.get(settings.provider_id)
        if descriptor is None or descriptor.access_mode is not ProviderAccessMode.REMOTE:
            continue
        if settings.provider_id == "eodhd":
            arguments: dict[str, object] = {"credential_resolver": resolver}
            if eodhd_transport is not None:
                arguments["transport"] = eodhd_transport
            providers.append(EodhdDailyProvider(**arguments))
            continue
        raise ProviderRuntimeError(
            "An enabled remote provider has no runtime factory",
            "RUNTIME_PROVIDER_NOT_AVAILABLE",
        )
    if not providers:
        raise ProviderRuntimeError(
            "The explicit config enables no runnable remote provider",
            "NO_REMOTE_PROVIDER",
        )
    return ProviderRegistry(tuple(providers))


def resolve_remote_route(
    configuration: ProviderConfiguration,
    registry: ProviderRegistry,
    *,
    market: Market,
    data_kind: str = "daily_bars",
) -> tuple[str, ...]:
    order = configuration.route_for(data_kind, market)
    if order is None:
        raise ProviderRuntimeError(
            "The explicit config has no route for this market and data kind",
            "ROUTE_NOT_CONFIGURED",
        )
    unavailable = [
        provider_id
        for provider_id in order
        if registry.get(provider_id) is None
    ]
    if unavailable:
        raise ProviderRuntimeError(
            "The selected remote route contains a provider unavailable in this mode",
            "RUNTIME_ROUTE_UNAVAILABLE",
        )
    return order
