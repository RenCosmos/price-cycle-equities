from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
import re
import socket
from typing import Callable, ClassVar, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from ..models import Bar, DataSet, Market, PriceBasis
from .base import (
    DataAssuranceMode,
    DataRequest,
    ProviderFailure,
    ProviderLoadResult,
    SourceArtifact,
)
from .config import (
    CredentialUnavailableError,
    EODHD_TOKEN_SPEC,
    EnvironmentCredentialResolver,
    SecretValue,
)


HISTORY_CALENDAR_DAYS = 550
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_ROWS = 6000
_EODHD_BASE_URL = "https://eodhd.com/api"
_CN_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}$")
_US_SYMBOL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,14}$")
_SPLIT_PATTERN = re.compile(
    r"^(?P<numerator>[0-9]+(?:\.[0-9]+)?)/"
    r"(?P<denominator>[0-9]+(?:\.[0-9]+)?)$"
)
_MARKET_TIMEZONES = {
    Market.CN: ZoneInfo("Asia/Shanghai"),
    Market.US: ZoneInfo("America/New_York"),
}
_CN_BENCHMARK_ETF_ALLOWLIST = {
    "510050": ("SSE", "SHG"),
    "510300": ("SSE", "SHG"),
    "510500": ("SSE", "SHG"),
    "588000": ("SSE", "SHG"),
    "159915": ("SZSE", "SHE"),
    "159919": ("SZSE", "SHE"),
}
_US_BENCHMARK_ETF_ALLOWLIST = frozenset(
    {"VTI", "SPY", "QQQ", "IWM"}
)

_TRANSPORT_ERROR_CODES = frozenset(
    {
        "UPSTREAM_AUTHORIZATION_FAILED",
        "UPSTREAM_HTTP_ERROR",
        "UPSTREAM_NOT_FOUND",
        "UPSTREAM_PERMISSION_DENIED",
        "UPSTREAM_RATE_LIMITED",
        "UPSTREAM_REDIRECT_REJECTED",
        "UPSTREAM_RESPONSE_INVALID",
        "UPSTREAM_RESPONSE_TOO_LARGE",
        "UPSTREAM_UNAVAILABLE",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _finalized_daily_cutoff(
    requested_as_of: date,
    *,
    market: Market,
    observed_at: datetime,
) -> date:
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    local_observed_at = observed_at.astimezone(_MARKET_TIMEZONES[market])
    cutoff = min(requested_as_of, local_observed_at.date())
    if (
        cutoff == local_observed_at.date()
        and local_observed_at.timetz().replace(tzinfo=None) < time(23, 0)
    ):
        cutoff -= timedelta(days=1)
    return cutoff


class EodhdTransport(Protocol):
    def fetch(
        self,
        *,
        endpoint: str,
        symbol: str,
        token: SecretValue,
        params: Mapping[str, str],
    ) -> object:
        ...


class EodhdTransportError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        if code not in _TRANSPORT_ERROR_CODES:
            raise ValueError("Unsupported EODHD transport error code")
        if type(retryable) is not bool:
            raise ValueError("EODHD transport retryable must be boolean")
        super().__init__("EODHD transport failed")
        self.code = code
        self.retryable = retryable


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: object,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        raise EodhdTransportError(
            "UPSTREAM_REDIRECT_REJECTED",
            retryable=False,
        )


def _default_opener() -> object:
    return build_opener(_RejectRedirect())


@dataclass(frozen=True, slots=True)
class HttpsEodhdTransport:
    timeout_seconds: float = 20.0
    max_response_bytes: int = MAX_RESPONSE_BYTES
    opener: object = field(default_factory=_default_opener, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive number")
        if type(self.max_response_bytes) is not int or self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive integer")
        if not hasattr(self.opener, "open"):
            raise ValueError("opener must provide open()")

    def fetch(
        self,
        *,
        endpoint: str,
        symbol: str,
        token: SecretValue,
        params: Mapping[str, str],
    ) -> object:
        if endpoint not in {"eod", "splits"}:
            raise ValueError("Unsupported EODHD endpoint")
        if not symbol or any(character in symbol for character in "/?#"):
            raise ValueError("Invalid EODHD symbol")
        public_params = dict(params)
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in public_params.items()
        ):
            raise ValueError("EODHD params must contain strings")
        query_params = dict(public_params)
        query_params["api_token"] = token.reveal()
        encoded_symbol = quote(symbol, safe=".-")
        url = (
            f"{_EODHD_BASE_URL}/{endpoint}/{encoded_symbol}?"
            + urlencode(query_params)
        )
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "price-cycle-equities/0.2",
            },
            method="GET",
        )
        response: object | None = None
        payload: bytes | None = None
        transport_error: EodhdTransportError | None = None
        try:
            response = self.opener.open(
                request,
                timeout=float(self.timeout_seconds),
            )
            status = getattr(response, "status", 200)
            if status != 200:
                raise EodhdTransportError(
                    "UPSTREAM_HTTP_ERROR",
                    retryable=status >= 500,
                )
            headers = getattr(response, "headers", None)
            content_type = headers.get("Content-Type", "") if headers else ""
            if content_type and "json" not in content_type.lower():
                raise EodhdTransportError(
                    "UPSTREAM_RESPONSE_INVALID",
                    retryable=False,
                )
            payload = response.read(self.max_response_bytes + 1)
        except EodhdTransportError as error:
            transport_error = EodhdTransportError(
                error.code,
                retryable=error.retryable,
            )
        except HTTPError as error:
            mapping = {
                401: ("UPSTREAM_AUTHORIZATION_FAILED", False),
                403: ("UPSTREAM_PERMISSION_DENIED", False),
                404: ("UPSTREAM_NOT_FOUND", False),
                429: ("UPSTREAM_RATE_LIMITED", True),
            }
            code, retryable = mapping.get(
                error.code,
                (
                    "UPSTREAM_UNAVAILABLE"
                    if error.code >= 500
                    else "UPSTREAM_HTTP_ERROR",
                    error.code >= 500,
                ),
            )
            try:
                error.close()
            except Exception:
                pass
            transport_error = EodhdTransportError(
                code,
                retryable=retryable,
            )
        except (URLError, TimeoutError, socket.timeout, OSError):
            transport_error = EodhdTransportError(
                "UPSTREAM_UNAVAILABLE",
                retryable=True,
            )
        except Exception:
            transport_error = EodhdTransportError(
                "UPSTREAM_RESPONSE_INVALID",
                retryable=False,
            )
        finally:
            if response is not None and hasattr(response, "close"):
                try:
                    response.close()
                except Exception:
                    if transport_error is None:
                        transport_error = EodhdTransportError(
                            "UPSTREAM_RESPONSE_INVALID",
                            retryable=False,
                        )

        if transport_error is not None:
            raise transport_error
        if payload is None:
            raise EodhdTransportError(
                "UPSTREAM_RESPONSE_INVALID",
                retryable=False,
            )
        if len(payload) > self.max_response_bytes:
            raise EodhdTransportError(
                "UPSTREAM_RESPONSE_TOO_LARGE",
                retryable=False,
            )
        try:
            text = payload.decode("utf-8")
            return json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EodhdTransportError(
                "UPSTREAM_RESPONSE_INVALID",
                retryable=False,
            ) from None


@dataclass(frozen=True, slots=True)
class _ListingIdentity:
    upstream_symbol: str
    venue: str | None
    segment: str | None


def _cn_listing(
    symbol: str,
    *,
    venue: str | None,
    segment: str | None,
    benchmark: bool,
) -> _ListingIdentity:
    if not _CN_SYMBOL_PATTERN.fullmatch(symbol):
        raise ProviderFailure(
            "CN symbols must be provider-neutral six-digit codes",
            code="INVALID_SYMBOL",
            retryable=False,
            fallback_allowed=True,
        )
    prefix = symbol[:3]
    if benchmark:
        benchmark_route = _CN_BENCHMARK_ETF_ALLOWLIST.get(symbol)
        if benchmark_route is None:
            raise ProviderFailure(
                "CN remote benchmark is not in the approved ETF proxy list",
                code="UNSUPPORTED_BENCHMARK",
                retryable=False,
                fallback_allowed=True,
            )
        inferred_venue, suffix = benchmark_route
        inferred_segment = None
    elif prefix in {"600", "601", "603", "605"}:
        inferred_venue, inferred_segment, suffix = "SSE", "MAIN", "SHG"
    elif prefix in {"688", "689"}:
        inferred_venue, inferred_segment, suffix = "SSE", "STAR", "SHG"
    elif prefix in {"000", "001", "002", "003"}:
        inferred_venue, inferred_segment, suffix = "SZSE", "MAIN", "SHE"
    elif prefix in {"300", "301"}:
        inferred_venue, inferred_segment, suffix = "SZSE", "CHINEXT", "SHE"
    elif symbol.startswith(("4", "8", "9")):
        raise ProviderFailure(
            "EODHD does not provide a verified Beijing Stock Exchange route",
            code="UNSUPPORTED_VENUE",
            retryable=False,
            fallback_allowed=True,
        )
    else:
        raise ProviderFailure(
            "The CN listing venue cannot be inferred safely from this code",
            code="INSTRUMENT_IDENTITY_UNKNOWN",
            retryable=False,
            fallback_allowed=True,
        )
    if venue is not None and venue != inferred_venue:
        raise ProviderFailure(
            "The requested venue conflicts with the CN security code",
            code="INSTRUMENT_IDENTITY_MISMATCH",
            retryable=False,
            fallback_allowed=True,
        )
    if (
        not benchmark
        and segment is not None
        and segment != inferred_segment
    ):
        raise ProviderFailure(
            "The requested segment conflicts with the CN security code",
            code="INSTRUMENT_IDENTITY_MISMATCH",
            retryable=False,
            fallback_allowed=True,
        )
    return _ListingIdentity(
        upstream_symbol=f"{symbol}.{suffix}",
        venue=inferred_venue,
        segment=inferred_segment,
    )


def _us_listing(
    symbol: str,
    *,
    venue: str | None,
    benchmark: bool,
) -> _ListingIdentity:
    if not _US_SYMBOL_PATTERN.fullmatch(symbol):
        raise ProviderFailure(
            "US symbols must be provider-neutral tickers without a vendor suffix",
            code="INVALID_SYMBOL",
            retryable=False,
            fallback_allowed=True,
        )
    normalized_symbol = symbol.upper()
    if benchmark and normalized_symbol not in _US_BENCHMARK_ETF_ALLOWLIST:
        raise ProviderFailure(
            "US remote benchmark is not in the approved ETF proxy list",
            code="UNSUPPORTED_BENCHMARK",
            retryable=False,
            fallback_allowed=True,
        )
    if venue is not None:
        raise ProviderFailure(
            "The EODHD composite US route cannot independently verify a venue",
            code="INSTRUMENT_IDENTITY_NOT_VERIFIED",
            retryable=False,
            fallback_allowed=True,
        )
    return _ListingIdentity(
        upstream_symbol=f"{normalized_symbol}.US",
        venue=None,
        segment=None,
    )


def _listing_identity(
    symbol: str,
    *,
    market: Market,
    venue: str | None,
    segment: str | None,
    benchmark: bool,
) -> _ListingIdentity:
    if market is Market.CN:
        return _cn_listing(
            symbol,
            venue=venue,
            segment=segment,
            benchmark=benchmark,
        )
    return _us_listing(symbol, venue=venue, benchmark=benchmark)


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _numeric(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} is not numeric")
    try:
        normalized = float(value)
    except OverflowError:
        raise ValueError(f"{field_name} is too large") from None
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} is not finite")
    return normalized


def _iso_date(value: object, *, field_name: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f"{field_name} is not an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field_name} is not an ISO date") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} is not canonical")
    return parsed


def _normalize_splits(
    response: object,
    *,
    start_date: date,
    as_of: date,
) -> tuple[tuple[date, float], list[dict[str, object]]]:
    if not isinstance(response, list) or len(response) > MAX_RESPONSE_ROWS:
        raise ProviderFailure(
            "EODHD returned an invalid splits payload",
            code="UPSTREAM_RESPONSE_INVALID",
            retryable=False,
            fallback_allowed=True,
        )
    parsed: list[tuple[date, float]] = []
    canonical: list[dict[str, object]] = []
    try:
        for item in response:
            if not isinstance(item, dict):
                raise ValueError("Split row is not an object")
            split_date = _iso_date(item.get("date"), field_name="split date")
            if split_date < start_date or split_date > as_of:
                raise ValueError("Split date is outside the request")
            raw_ratio = item.get("split")
            if not isinstance(raw_ratio, str):
                raise ValueError("Split ratio is not a string")
            match = _SPLIT_PATTERN.fullmatch(raw_ratio)
            if match is None:
                raise ValueError("Split ratio is invalid")
            numerator = float(match.group("numerator"))
            denominator = float(match.group("denominator"))
            if (
                not math.isfinite(numerator)
                or not math.isfinite(denominator)
                or numerator <= 0
                or denominator <= 0
            ):
                raise ValueError("Split ratio is invalid")
            factor = numerator / denominator
            parsed.append((split_date, factor))
            canonical.append(
                {
                    "date": split_date.isoformat(),
                    "factor": factor,
                    "split": raw_ratio,
                }
            )
    except (TypeError, ValueError, OverflowError):
        raise ProviderFailure(
            "EODHD returned invalid split values",
            code="INVALID_SOURCE_DATA",
            retryable=False,
            fallback_allowed=True,
        ) from None
    parsed.sort(key=lambda item: item[0])
    canonical.sort(key=lambda item: str(item["date"]))
    split_dates = [item[0] for item in parsed]
    if len(split_dates) != len(set(split_dates)):
        raise ProviderFailure(
            "EODHD returned duplicate split dates",
            code="INVALID_SOURCE_DATA",
            retryable=False,
            fallback_allowed=True,
        )
    return tuple(parsed), canonical


def _split_adjustment(
    session_date: date,
    splits: tuple[tuple[date, float], ...],
) -> float:
    factor = 1.0
    for split_date, split_factor in splits:
        if split_date > session_date:
            factor *= split_factor
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("Split adjustment is invalid")
    return factor


def _normalize_bars(
    response: object,
    *,
    splits: tuple[tuple[date, float], ...],
    start_date: date,
    as_of: date,
    market: Market,
) -> tuple[tuple[Bar, ...], list[dict[str, object]], bool]:
    if (
        not isinstance(response, list)
        or not response
        or len(response) > MAX_RESPONSE_ROWS
    ):
        raise ProviderFailure(
            "EODHD returned no usable daily-bar array",
            code="NO_SOURCE_DATA" if response == [] else "UPSTREAM_RESPONSE_INVALID",
            retryable=False,
            fallback_allowed=True,
        )
    parsed: list[tuple[Bar, dict[str, object]]] = []
    required_fields = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
    }
    try:
        for item in response:
            if not isinstance(item, dict) or not required_fields.issubset(item):
                raise ValueError("Daily row schema is invalid")
            session_date = _iso_date(item.get("date"), field_name="bar date")
            if session_date < start_date or session_date > as_of:
                raise ValueError("Daily row date is outside the request")
            raw_values = {
                name: _numeric(item.get(name), field_name=name)
                for name in ("open", "high", "low", "close", "adjusted_close")
            }
            if min(raw_values.values()) <= 0:
                raise ValueError("Daily price is not positive")
            volume = _numeric(item.get("volume"), field_name="volume")
            if volume < 0:
                raise ValueError("Daily volume is negative")
            adjustment = _split_adjustment(session_date, splits)
            adjusted = {
                name: raw_values[name] / adjustment
                for name in ("open", "high", "low", "close")
            }
            known_at = datetime.combine(
                session_date,
                time(23, 0),
                tzinfo=_MARKET_TIMEZONES[market],
            )
            bar = Bar(
                session_date=session_date,
                open=adjusted["open"],
                high=adjusted["high"],
                low=adjusted["low"],
                close=adjusted["close"],
                volume=volume,
                known_at=known_at,
            )
            canonical = {
                "adjustment_factor": adjustment,
                "adjusted_close_vendor": raw_values["adjusted_close"],
                "close": adjusted["close"],
                "date": session_date.isoformat(),
                "high": adjusted["high"],
                "low": adjusted["low"],
                "open": adjusted["open"],
                "raw_close": raw_values["close"],
                "volume": volume,
            }
            parsed.append((bar, canonical))
    except (TypeError, ValueError, OverflowError):
        raise ProviderFailure(
            "EODHD returned invalid daily-bar values",
            code="INVALID_SOURCE_DATA",
            retryable=False,
            fallback_allowed=True,
        ) from None
    original_dates = [bar.session_date for bar, _ in parsed]
    parsed.sort(key=lambda item: item[0].session_date)
    sorted_dates = [bar.session_date for bar, _ in parsed]
    if len(sorted_dates) != len(set(sorted_dates)):
        raise ProviderFailure(
            "EODHD returned duplicate daily-bar dates",
            code="INVALID_SOURCE_DATA",
            retryable=False,
            fallback_allowed=True,
        )
    return (
        tuple(bar for bar, _ in parsed),
        [canonical for _, canonical in parsed],
        original_dates != sorted_dates,
    )


def _transport_failure(error: EodhdTransportError) -> ProviderFailure:
    messages = {
        "UPSTREAM_REDIRECT_REJECTED": "EODHD attempted an unsafe redirect",
        "UPSTREAM_RATE_LIMITED": "EODHD rate-limited the request",
        "UPSTREAM_AUTHORIZATION_FAILED": "EODHD rejected API authorization",
        "UPSTREAM_PERMISSION_DENIED": "EODHD denied access to the requested data",
        "UPSTREAM_NOT_FOUND": "EODHD did not recognize the requested instrument",
        "UPSTREAM_RESPONSE_TOO_LARGE": "EODHD returned an oversized response",
        "UPSTREAM_RESPONSE_INVALID": "EODHD returned an invalid response",
        "UPSTREAM_UNAVAILABLE": "EODHD is temporarily unavailable",
        "UPSTREAM_HTTP_ERROR": "EODHD returned an HTTP error",
    }
    return ProviderFailure(
        messages.get(error.code, "EODHD transport failed"),
        code=error.code,
        retryable=error.retryable,
        fallback_allowed=True,
    )


@dataclass(frozen=True, slots=True)
class EodhdDailyProvider:
    assurance_mode: ClassVar[DataAssuranceMode] = DataAssuranceMode.PROVIDER_VERIFIED
    source_label: ClassVar[str] = "EODHD EOD and splits"
    provider_id: ClassVar[str] = "eodhd"
    credential_resolver: EnvironmentCredentialResolver = field(
        default_factory=EnvironmentCredentialResolver
    )
    transport: EodhdTransport = field(default_factory=HttpsEodhdTransport)
    clock: Callable[[], datetime] = field(default=_utc_now, repr=False)

    def supports(self, request: DataRequest) -> bool:
        return (
            request.market in {Market.CN, Market.US}
            and request.price_basis is PriceBasis.SPLIT_ADJUSTED
            and request.interval == "1d"
            and request.security_type == "COMMON_STOCK"
        )

    def _fetch_payload(
        self,
        *,
        endpoint: str,
        symbol: str,
        token: SecretValue,
        params: Mapping[str, str],
    ) -> object:
        response: object | None = None
        failure: ProviderFailure | None = None
        try:
            response = self.transport.fetch(
                endpoint=endpoint,
                symbol=symbol,
                token=token,
                params=params,
            )
        except EodhdTransportError as error:
            failure = _transport_failure(error)
        except Exception:
            failure = ProviderFailure(
                "EODHD transport failed without a public detail",
                code="UPSTREAM_HTTP_ERROR",
                retryable=False,
                fallback_allowed=True,
            )
        if failure is not None:
            raise failure
        if response is None:
            raise ProviderFailure(
                "EODHD returned no response",
                code="UPSTREAM_RESPONSE_INVALID",
                retryable=False,
                fallback_allowed=True,
            )
        return response

    def _load_role(
        self,
        *,
        role: str,
        symbol: str,
        market: Market,
        venue: str | None,
        segment: str | None,
        start_date: date,
        as_of: date,
        token: SecretValue,
        benchmark: bool,
        retrieved_at: datetime,
    ) -> tuple[
        tuple[Bar, ...],
        SourceArtifact,
        bool,
        _ListingIdentity,
    ]:
        identity = _listing_identity(
            symbol,
            market=market,
            venue=venue,
            segment=segment,
            benchmark=benchmark,
        )
        params = {
            "fmt": "json",
            "from": start_date.isoformat(),
            "to": as_of.isoformat(),
        }
        eod_params = {**params, "order": "a", "period": "d"}
        eod_response = self._fetch_payload(
            endpoint="eod",
            symbol=identity.upstream_symbol,
            token=token,
            params=eod_params,
        )
        splits_response = self._fetch_payload(
            endpoint="splits",
            symbol=identity.upstream_symbol,
            token=token,
            params=params,
        )
        splits, canonical_splits = _normalize_splits(
            splits_response,
            start_date=start_date,
            as_of=as_of,
        )
        bars, canonical_bars, reordered = _normalize_bars(
            eod_response,
            splits=splits,
            start_date=start_date,
            as_of=as_of,
            market=market,
        )
        snapshot = _canonical_digest(
            {
                "eod_params": eod_params,
                "normalized_bars": canonical_bars,
                "normalized_splits": canonical_splits,
                "role": role,
                "symbol": identity.upstream_symbol,
            }
        )
        artifact_name = (
            f"eodhd-{role}-{identity.upstream_symbol}-"
            f"{start_date.isoformat()}-{as_of.isoformat()}.json"
        )
        artifact = SourceArtifact(
            role=role,
            provider_id=self.provider_id,
            source_label=self.source_label,
            artifact_name=artifact_name,
            snapshot_id=snapshot,
            price_basis=PriceBasis.SPLIT_ADJUSTED,
            market_data_scope="full_listing",
            volume_scope="vendor_reported_unverified",
            volume_basis="unknown",
            zero_volume_policy="unknown",
            timestamp_policy="session_date_known_after_close",
            retrieved_at=retrieved_at,
        )
        return bars, artifact, reordered, identity

    def load(self, request: DataRequest) -> ProviderLoadResult:
        if not self.supports(request):
            raise ProviderFailure(
                "EODHD supports split-adjusted daily CN/US common-stock research",
                code="UNSUPPORTED_REQUEST",
                retryable=False,
                fallback_allowed=True,
            )
        _listing_identity(
            request.symbol,
            market=request.market,
            venue=request.venue,
            segment=request.segment,
            benchmark=False,
        )
        if request.benchmark_symbol is not None:
            _listing_identity(
                request.benchmark_symbol,
                market=request.market,
                venue=None,
                segment=None,
                benchmark=True,
            )
        try:
            token = self.credential_resolver.resolve(EODHD_TOKEN_SPEC)
        except CredentialUnavailableError:
            raise ProviderFailure(
                "The required EODHD credential environment variable is unavailable",
                code="CREDENTIAL_ENV_MISSING",
                retryable=False,
                fallback_allowed=True,
            ) from None

        retrieved_at = self.clock()
        try:
            query_as_of = _finalized_daily_cutoff(
                request.as_of,
                market=request.market,
                observed_at=retrieved_at,
            )
            start_date = query_as_of - timedelta(days=HISTORY_CALENDAR_DAYS)
        except (OverflowError, ValueError):
            raise ProviderFailure(
                "The remote daily-bar cutoff could not be established safely",
                code="INVALID_AS_OF",
                retryable=False,
                fallback_allowed=True,
            ) from None
        bars, instrument_artifact, instrument_reordered, identity = self._load_role(
            role="instrument",
            symbol=request.symbol,
            market=request.market,
            venue=request.venue,
            segment=request.segment,
            start_date=start_date,
            as_of=query_as_of,
            token=token,
            benchmark=False,
            retrieved_at=retrieved_at,
        )
        benchmark_bars: tuple[Bar, ...] = ()
        artifacts = [instrument_artifact]
        benchmark_reordered = False
        if request.benchmark_symbol is not None:
            (
                benchmark_bars,
                benchmark_artifact,
                benchmark_reordered,
                _,
            ) = self._load_role(
                role="benchmark",
                symbol=request.benchmark_symbol,
                market=request.market,
                venue=None,
                segment=None,
                start_date=start_date,
                as_of=query_as_of,
                token=token,
                benchmark=True,
                retrieved_at=retrieved_at,
            )
            artifacts.append(benchmark_artifact)

        dataset = DataSet(
            instrument_id=request.instrument_id
            or f"{request.market.value}:{request.symbol}",
            symbol=request.symbol,
            market=request.market,
            as_of=request.as_of,
            source=self.source_label,
            price_basis=request.price_basis,
            bars=bars,
            venue=identity.venue,
            segment=identity.segment,
            security_type=request.security_type,
            benchmark_symbol=request.benchmark_symbol,
            benchmark_bars=benchmark_bars,
            volume_evidence_eligible=False,
            instrument_identity_assurance="symbol_route_inferred_not_master_verified",
        )
        diagnostics: dict[str, object] = {
            "input_rows": len(bars),
            "usable_rows": len(bars),
            "excluded_after_as_of": 0,
            "excluded_not_yet_known": 0,
            "input_reordered": instrument_reordered,
            "instrument_id_is_fallback": request.instrument_id is None,
            "benchmark_supplied": request.benchmark_symbol is not None,
            "benchmark_rows": len(benchmark_bars),
            "benchmark_input_rows": len(benchmark_bars),
            "benchmark_usable_rows": len(benchmark_bars),
            "benchmark_excluded_after_as_of": 0,
            "benchmark_excluded_not_yet_known": 0,
            "benchmark_input_reordered": benchmark_reordered,
            "timestamp_policy": dataset.timestamp_policy,
        }
        aggregate_snapshot = _canonical_digest(
            {
                "artifact_snapshots": [item.snapshot_id for item in artifacts],
                "as_of": request.as_of.isoformat(),
                "instrument_id": dataset.instrument_id,
                "market": request.market.value,
                "price_basis": request.price_basis.value,
                "security_type": request.security_type,
                "symbol": request.symbol,
            }
        )
        return ProviderLoadResult(
            provider_id=self.provider_id,
            assurance_mode=self.assurance_mode,
            dataset=dataset,
            diagnostics=diagnostics,
            snapshot_id=aggregate_snapshot,
            artifact_name=instrument_artifact.artifact_name,
            artifacts=tuple(artifacts),
            market_data_scope="full_listing",
            volume_scope="vendor_reported_unverified",
            volume_basis="unknown",
            volume_completeness=1.0,
            zero_volume_policy="unknown",
            price_basis_assertion="provider_verified",
        )
