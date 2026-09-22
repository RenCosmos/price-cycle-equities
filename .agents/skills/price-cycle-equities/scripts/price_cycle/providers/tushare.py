from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
import re
from typing import ClassVar, Mapping, Protocol
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
    EnvironmentCredentialResolver,
    SecretValue,
    TUSHARE_TOKEN_SPEC,
)


TUSHARE_DAILY_FIELDS = (
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
)
HISTORY_CALENDAR_DAYS = 550
MAX_RESPONSE_ROWS = 6000
_TUSHARE_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(?:SH|SZ|BJ)$")
_VENUE_BY_SUFFIX = {
    "SH": "SSE",
    "SZ": "SZSE",
    "BJ": "BSE",
}
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_TRANSPORT_ERROR_CODES = frozenset(
    {
        "SECURE_TRANSPORT_NOT_VERIFIED",
        "UPSTREAM_AUTHORIZATION_FAILED",
        "UPSTREAM_HTTP_ERROR",
        "UPSTREAM_RATE_LIMITED",
        "UPSTREAM_REDIRECT_REJECTED",
        "UPSTREAM_RESPONSE_INVALID",
        "UPSTREAM_RESPONSE_TOO_LARGE",
        "UPSTREAM_UNAVAILABLE",
    }
)


class TushareTransport(Protocol):
    def query(
        self,
        *,
        api_name: str,
        token: SecretValue,
        params: Mapping[str, str],
        fields: tuple[str, ...],
    ) -> object:
        ...


class TushareTransportError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        if code not in _TRANSPORT_ERROR_CODES:
            raise ValueError("Unsupported Tushare transport error code")
        if type(retryable) is not bool:
            raise ValueError("Tushare transport retryable must be boolean")
        super().__init__("Tushare transport failed")
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class BlockedTushareTransport:
    """Fail closed until Tushare documents secure POST and volume semantics."""

    def query(
        self,
        *,
        api_name: str,
        token: SecretValue,
        params: Mapping[str, str],
        fields: tuple[str, ...],
    ) -> object:
        del api_name, token, params, fields
        raise TushareTransportError(
            "SECURE_TRANSPORT_NOT_VERIFIED",
            retryable=False,
        )


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _numeric(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Daily bar value is not numeric")
    try:
        normalized = float(value)
    except OverflowError:
        raise ValueError("Daily bar value is too large") from None
    if not math.isfinite(normalized):
        raise ValueError("Daily bar value is not finite")
    return normalized


def _upstream_failure(code: int) -> ProviderFailure:
    if code == 2002:
        return ProviderFailure(
            "Tushare rejected the request because the account lacks permission",
            code="UPSTREAM_PERMISSION_DENIED",
            retryable=False,
            fallback_allowed=True,
        )
    return ProviderFailure(
        "Tushare rejected the daily-bar request",
        code="UPSTREAM_REQUEST_REJECTED",
        retryable=False,
        fallback_allowed=True,
    )


@dataclass(frozen=True, slots=True)
class TushareDailyProvider:
    assurance_mode: ClassVar[DataAssuranceMode] = DataAssuranceMode.PROVIDER_VERIFIED
    source_label: ClassVar[str] = "Tushare Pro daily"
    provider_id: ClassVar[str] = "tushare"
    credential_resolver: EnvironmentCredentialResolver = field(
        default_factory=EnvironmentCredentialResolver
    )
    transport: TushareTransport = field(default_factory=BlockedTushareTransport)

    def supports(self, request: DataRequest) -> bool:
        return (
            request.market is Market.CN
            and request.price_basis is PriceBasis.RAW
            and request.interval == "1d"
            and request.security_type == "COMMON_STOCK"
            and request.benchmark_symbol is None
        )

    def load(self, request: DataRequest) -> ProviderLoadResult:
        if not self.supports(request):
            raise ProviderFailure(
                "Tushare scaffold supports only unadjusted CN common-stock daily bars without a benchmark",
                code="UNSUPPORTED_REQUEST",
                retryable=False,
                fallback_allowed=True,
            )
        symbol = request.symbol
        if not _TUSHARE_SYMBOL_PATTERN.fullmatch(symbol):
            raise ProviderFailure(
                "Tushare requires an exact six-digit A-share TS code with .SH, .SZ, or .BJ",
                code="INVALID_SYMBOL",
                retryable=False,
                fallback_allowed=True,
            )
        suffix = symbol.rsplit(".", 1)[1]
        inferred_venue = _VENUE_BY_SUFFIX[suffix]
        if request.venue is not None and request.venue != inferred_venue:
            raise ProviderFailure(
                "The requested venue conflicts with the Tushare symbol suffix",
                code="INSTRUMENT_IDENTITY_MISMATCH",
                retryable=False,
                fallback_allowed=True,
            )

        credential_failure: ProviderFailure | None = None
        try:
            token = self.credential_resolver.resolve(TUSHARE_TOKEN_SPEC)
        except CredentialUnavailableError:
            credential_failure = ProviderFailure(
                "The required Tushare credential environment variable is unavailable",
                code="CREDENTIAL_ENV_MISSING",
                retryable=False,
                fallback_allowed=True,
            )
        if credential_failure is not None:
            raise credential_failure

        start_date = request.as_of - timedelta(days=HISTORY_CALENDAR_DAYS)
        params = {
            "ts_code": symbol,
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": request.as_of.strftime("%Y%m%d"),
        }
        transport_failure: ProviderFailure | None = None
        response: object | None = None
        try:
            response = self.transport.query(
                api_name="daily",
                token=token,
                params=params,
                fields=TUSHARE_DAILY_FIELDS,
            )
        except TushareTransportError as error:
            public_messages = {
                "SECURE_TRANSPORT_NOT_VERIFIED": (
                    "Tushare live access is disabled because its secure POST "
                    "contract is not verified"
                ),
                "UPSTREAM_REDIRECT_REJECTED": "Tushare attempted an unsafe redirect",
                "UPSTREAM_RATE_LIMITED": "Tushare rate-limited the request",
                "UPSTREAM_AUTHORIZATION_FAILED": "Tushare rejected HTTP authorization",
                "UPSTREAM_RESPONSE_TOO_LARGE": "Tushare returned an oversized response",
                "UPSTREAM_RESPONSE_INVALID": "Tushare returned an invalid response",
                "UPSTREAM_UNAVAILABLE": "Tushare is temporarily unavailable",
                "UPSTREAM_HTTP_ERROR": "Tushare returned an HTTP error",
            }
            transport_failure = ProviderFailure(
                public_messages.get(error.code, "Tushare transport failed"),
                code=(
                    error.code
                    if error.code in public_messages
                    else "UPSTREAM_TRANSPORT_ERROR"
                ),
                retryable=error.retryable,
                fallback_allowed=True,
            )
        except Exception:
            transport_failure = ProviderFailure(
                "Tushare transport failed without a public detail",
                code="UPSTREAM_TRANSPORT_ERROR",
                retryable=False,
                fallback_allowed=True,
            )
        if transport_failure is not None:
            raise transport_failure
        if response is None:
            raise ProviderFailure(
                "Tushare returned no response envelope",
                code="UPSTREAM_RESPONSE_INVALID",
                retryable=False,
                fallback_allowed=True,
            )

        bars, canonical_rows, input_reordered = self._normalize_response(
            response,
            symbol=symbol,
            start_date=start_date,
            as_of=request.as_of,
        )
        retrieved_at = datetime.now(timezone.utc)
        artifact_payload = {
            "api_name": "daily",
            "fields": list(TUSHARE_DAILY_FIELDS),
            "params": params,
            "items": canonical_rows,
        }
        artifact_snapshot_id = _canonical_digest(artifact_payload)
        artifact_name = (
            f"tushare-daily-{symbol}-{params['start_date']}-{params['end_date']}.json"
        )
        aggregate_snapshot_id = _canonical_digest(
            {
                "artifact_snapshot_id": artifact_snapshot_id,
                "as_of": request.as_of.isoformat(),
                "instrument_id": request.instrument_id,
                "market": request.market.value,
                "price_basis": request.price_basis.value,
                "security_type": request.security_type,
                "segment": request.segment,
                "symbol": request.symbol,
                "venue": request.venue,
            }
        )
        dataset = DataSet(
            instrument_id=request.instrument_id or f"CN:{symbol}",
            symbol=request.symbol,
            market=request.market,
            as_of=request.as_of,
            source=self.source_label,
            price_basis=request.price_basis,
            bars=bars,
            venue=request.venue or inferred_venue,
            segment=request.segment,
            security_type=request.security_type,
        )
        diagnostics: dict[str, object] = {
            "input_rows": len(bars),
            "usable_rows": len(bars),
            "excluded_after_as_of": 0,
            "excluded_not_yet_known": 0,
            "input_reordered": input_reordered,
            "instrument_id_is_fallback": request.instrument_id is None,
            "benchmark_supplied": False,
            "benchmark_rows": 0,
            "benchmark_input_rows": 0,
            "benchmark_usable_rows": 0,
            "benchmark_excluded_after_as_of": 0,
            "benchmark_excluded_not_yet_known": 0,
            "benchmark_input_reordered": False,
            "timestamp_policy": dataset.timestamp_policy,
        }
        artifact = SourceArtifact(
            role="instrument",
            provider_id=self.provider_id,
            source_label=self.source_label,
            artifact_name=artifact_name,
            snapshot_id=artifact_snapshot_id,
            price_basis=request.price_basis,
            market_data_scope="full_listing",
            volume_scope="unknown",
            volume_basis="raw",
            zero_volume_policy="reported_zero_only",
            timestamp_policy=dataset.timestamp_policy,
            retrieved_at=retrieved_at,
        )
        return ProviderLoadResult(
            provider_id=self.provider_id,
            assurance_mode=self.assurance_mode,
            dataset=dataset,
            diagnostics=diagnostics,
            snapshot_id=aggregate_snapshot_id,
            artifact_name=artifact_name,
            artifacts=(artifact,),
            market_data_scope="full_listing",
            volume_scope="unknown",
            volume_basis="raw",
            volume_completeness=None,
            zero_volume_policy="reported_zero_only",
            price_basis_assertion="provider_verified",
        )

    @staticmethod
    def _normalize_response(
        response: object,
        *,
        symbol: str,
        start_date: date,
        as_of: date,
    ) -> tuple[tuple[Bar, ...], list[list[object]], bool]:
        if not isinstance(response, dict):
            raise ProviderFailure(
                "Tushare returned an invalid response envelope",
                code="UPSTREAM_RESPONSE_INVALID",
                retryable=False,
                fallback_allowed=True,
            )
        code = response.get("code")
        if type(code) is not int:
            raise ProviderFailure(
                "Tushare returned an invalid response code",
                code="UPSTREAM_RESPONSE_INVALID",
                retryable=False,
                fallback_allowed=True,
            )
        if code != 0:
            raise _upstream_failure(code)
        data = response.get("data")
        if not isinstance(data, dict):
            raise ProviderFailure(
                "Tushare returned an invalid daily-bar payload",
                code="UPSTREAM_RESPONSE_INVALID",
                retryable=False,
                fallback_allowed=True,
            )
        fields = data.get("fields")
        items = data.get("items")
        if (
            not isinstance(fields, list)
            or any(not isinstance(item, str) for item in fields)
            or len(fields) != len(set(fields))
            or set(fields) != set(TUSHARE_DAILY_FIELDS)
            or not isinstance(items, list)
            or len(items) > MAX_RESPONSE_ROWS
        ):
            raise ProviderFailure(
                "Tushare returned an invalid daily-bar schema",
                code="UPSTREAM_RESPONSE_INVALID",
                retryable=False,
                fallback_allowed=True,
            )
        field_index = {name: index for index, name in enumerate(fields)}
        parsed: list[tuple[Bar, list[object]]] = []
        invalid_values = False
        try:
            for item in items:
                if not isinstance(item, list) or len(item) != len(fields):
                    raise ValueError("Daily row shape is invalid")
                row_symbol = item[field_index["ts_code"]]
                trade_date = item[field_index["trade_date"]]
                if not isinstance(row_symbol, str) or row_symbol != symbol:
                    raise ValueError("Daily row symbol does not match")
                if (
                    not isinstance(trade_date, str)
                    or len(trade_date) != 8
                    or not trade_date.isascii()
                    or not trade_date.isdigit()
                ):
                    raise ValueError("Daily row date is invalid")
                session_date = datetime.strptime(trade_date, "%Y%m%d").date()
                if session_date < start_date or session_date > as_of:
                    raise ValueError("Daily row date is outside the request")
                normalized_values = {
                    name: _numeric(item[field_index[name]])
                    for name in ("open", "high", "low", "close", "vol")
                }
                bar = Bar(
                    session_date=session_date,
                    open=normalized_values["open"],
                    high=normalized_values["high"],
                    low=normalized_values["low"],
                    close=normalized_values["close"],
                    volume=normalized_values["vol"],
                    known_at=datetime.combine(
                        session_date,
                        time(17, 0),
                        tzinfo=_SHANGHAI,
                    ),
                )
                canonical_row: list[object] = [
                    symbol,
                    trade_date,
                    normalized_values["open"],
                    normalized_values["high"],
                    normalized_values["low"],
                    normalized_values["close"],
                    normalized_values["vol"],
                ]
                parsed.append((bar, canonical_row))
        except (TypeError, ValueError):
            invalid_values = True
        if invalid_values:
            raise ProviderFailure(
                "Tushare returned invalid daily-bar values",
                code="INVALID_SOURCE_DATA",
                retryable=False,
                fallback_allowed=True,
            )
        if not parsed:
            raise ProviderFailure(
                "Tushare returned no daily bars for the requested instrument and dates",
                code="NO_SOURCE_DATA",
                retryable=False,
                fallback_allowed=True,
            )
        original_dates = [bar.session_date for bar, _ in parsed]
        parsed.sort(key=lambda item: item[0].session_date)
        sorted_dates = [bar.session_date for bar, _ in parsed]
        if len(sorted_dates) != len(set(sorted_dates)):
            raise ProviderFailure(
                "Tushare returned duplicate daily-bar dates",
                code="INVALID_SOURCE_DATA",
                retryable=False,
                fallback_allowed=True,
            )
        return (
            tuple(bar for bar, _ in parsed),
            [row for _, row in parsed],
            original_dates != sorted_dates,
        )
