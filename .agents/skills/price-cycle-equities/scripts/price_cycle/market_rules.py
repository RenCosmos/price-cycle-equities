from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum

from .models import Market, TriState


class RuleResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class TradingSession:
    name: str
    start_local: str
    end_local: str


@dataclass(frozen=True, slots=True)
class QuantityRule:
    buy_minimum_shares: int | None
    buy_increment_shares: int | None
    odd_lot_sell_policy: str
    scope_note: str


@dataclass(frozen=True, slots=True)
class PriceRule:
    base_tick: float | None
    standard_daily_limit_pct: float | None
    dynamic_guard: str
    scope_note: str


@dataclass(frozen=True, slots=True)
class RuleSource:
    title: str
    url: str
    verified_at: date


@dataclass(frozen=True, slots=True)
class MarketRuleSnapshot:
    rule_version: str
    market: Market
    venue: str | None
    segment: str | None
    security_type: str
    valid_from: date
    valid_to: date | None
    timezone: str
    regular_sessions: tuple[TradingSession, ...]
    settlement_cycle: str
    same_day_resale: TriState
    quantity_rule: QuantityRule
    price_rule: PriceRule
    shorting_default: str
    margin_policy: str
    sources: tuple[RuleSource, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleResolution:
    status: RuleResolutionStatus
    as_of: date
    snapshot: MarketRuleSnapshot | None
    unknowns: tuple[str, ...]
    execution_ready: bool = False

    @property
    def rule_version(self) -> str:
        return self.snapshot.rule_version if self.snapshot else "not_loaded"


VERIFIED_AT = date(2026, 9, 21)
CN_RULES_VALID_FROM = date(2026, 7, 6)
US_T1_VALID_FROM = date(2024, 5, 28)
US_INTRADAY_MARGIN_VALID_FROM = date(2026, 6, 4)

SSE_SOURCE = RuleSource(
    title="Shanghai Stock Exchange Trading Rules (2026 Revision)",
    url=(
        "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/"
        "exchange/c/c_20260424_10816482.shtml"
    ),
    verified_at=VERIFIED_AT,
)
SZSE_SOURCE = RuleSource(
    title="Shenzhen Stock Exchange Trading Rules (2026 Revision)",
    url=(
        "https://docs.static.szse.cn/www/lawrules/rule/trade/current/"
        "W020260424690713155663.pdf"
    ),
    verified_at=VERIFIED_AT,
)
BSE_SOURCE = RuleSource(
    title="Beijing Stock Exchange Trading Rules (2026)",
    url="https://www.bse.cn/jygl_list/200028217.html",
    verified_at=VERIFIED_AT,
)
SEC_T1_SOURCE = RuleSource(
    title="SEC T+1 settlement implementation",
    url="https://www.sec.gov/newsroom/press-releases/2024-62",
    verified_at=VERIFIED_AT,
)
SEC_HOURS_SOURCE = RuleSource(
    title="SEC Regulation NMS regular trading hours FAQ",
    url="https://www.sec.gov/divisions/marketreg/nmsfaq610-11.htm",
    verified_at=VERIFIED_AT,
)
NYSE_SOURCE = RuleSource(
    title="NYSE trading information",
    url="https://www.nyse.com/trade/trading-information",
    verified_at=VERIFIED_AT,
)
NASDAQ_SOURCE = RuleSource(
    title="Nasdaq U.S. stock market schedule",
    url="https://www.nasdaq.com/market-activity/stock-market-holiday-schedule",
    verified_at=VERIFIED_AT,
)
LULD_SOURCE = RuleSource(
    title="Limit Up-Limit Down Plan",
    url="https://www.luldplan.com/plans",
    verified_at=VERIFIED_AT,
)
FINRA_MARGIN_SOURCE = RuleSource(
    title="FINRA intraday margin requirements",
    url=(
        "https://syndication.finra.org/content/"
        "understanding-new-intraday-margin-requirements"
    ),
    verified_at=VERIFIED_AT,
)

CN_REGULAR_SESSIONS = (
    TradingSession("OPEN_AUCTION", "09:15", "09:25"),
    TradingSession("CONTINUOUS_AM", "09:30", "11:30"),
    TradingSession("CONTINUOUS_PM", "13:00", "14:57"),
    TradingSession("CLOSE_AUCTION", "14:57", "15:00"),
)
US_REGULAR_SESSIONS = (
    TradingSession("REGULAR", "09:30", "16:00"),
)

VENUE_ALIASES = {
    "SH": "SSE",
    "XSHG": "SSE",
    "SSE": "SSE",
    "SZ": "SZSE",
    "XSHE": "SZSE",
    "SZSE": "SZSE",
    "BJ": "BSE",
    "XBSE": "BSE",
    "BSE": "BSE",
    "NYSE": "XNYS",
    "XNYS": "XNYS",
    "NASDAQ": "XNAS",
    "XNAS": "XNAS",
}


def _normalized(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return VENUE_ALIASES.get(normalized, normalized)


def _cn_snapshot(venue: str, segment: str) -> MarketRuleSnapshot | None:
    configurations: dict[tuple[str, str], tuple[int, int, float, RuleSource]] = {
        ("SSE", "MAIN"): (100, 100, 0.10, SSE_SOURCE),
        ("SSE", "STAR"): (200, 1, 0.20, SSE_SOURCE),
        ("SZSE", "MAIN"): (100, 100, 0.10, SZSE_SOURCE),
        ("SZSE", "CHINEXT"): (100, 100, 0.20, SZSE_SOURCE),
        ("BSE", "BSE"): (100, 1, 0.30, BSE_SOURCE),
    }
    configuration = configurations.get((venue, segment))
    if configuration is None:
        return None
    minimum, increment, price_limit, source = configuration
    return MarketRuleSnapshot(
        rule_version=f"CN-{venue}-{segment}-2026-07-06",
        market=Market.CN,
        venue=venue,
        segment=segment,
        security_type="COMMON_STOCK",
        valid_from=CN_RULES_VALID_FROM,
        valid_to=None,
        timezone="Asia/Shanghai",
        regular_sessions=CN_REGULAR_SESSIONS,
        settlement_cycle="SECURITIES_NOT_RESELLABLE_BEFORE_DELIVERY",
        same_day_resale=TriState.FALSE,
        quantity_rule=QuantityRule(
            buy_minimum_shares=minimum,
            buy_increment_shares=increment,
            odd_lot_sell_policy="REMAINDER_BELOW_MINIMUM_MUST_BE_SOLD_IN_ONE_ORDER",
            scope_note="Ordinary auction orders; order type and instrument status can override maxima.",
        ),
        price_rule=PriceRule(
            base_tick=0.01,
            standard_daily_limit_pct=price_limit,
            dynamic_guard="LIVE_INSTRUMENT_STATUS_AND_EFFECTIVE_LIMIT_REQUIRED",
            scope_note=(
                "Standard ordinary-stock value only; IPO windows, risk warnings, delisting, "
                "halts, and special rules can change or remove the limit."
            ),
        ),
        shorting_default="LONG_ONLY_UNLESS_ACCOUNT_ELIGIBILITY_AND_LIVE_BORROW_RESOLVE",
        margin_policy="ACCOUNT_AND_BROKER_RULES_REQUIRED",
        sources=(source,),
        notes=(
            "Daily-bar research cannot establish queue priority or fill availability at a price limit.",
            "The exchange calendar and instrument status must be retrieved for the specific session.",
        ),
    )


def _cn_generic_snapshot() -> MarketRuleSnapshot:
    return MarketRuleSnapshot(
        rule_version="CN-GENERIC-2026-07-06",
        market=Market.CN,
        venue=None,
        segment=None,
        security_type="COMMON_STOCK",
        valid_from=CN_RULES_VALID_FROM,
        valid_to=None,
        timezone="Asia/Shanghai",
        regular_sessions=CN_REGULAR_SESSIONS,
        settlement_cycle="SECURITIES_NOT_RESELLABLE_BEFORE_DELIVERY",
        same_day_resale=TriState.FALSE,
        quantity_rule=QuantityRule(None, None, "VENUE_AND_SEGMENT_REQUIRED", "Fail closed."),
        price_rule=PriceRule(
            None,
            None,
            "VENUE_SEGMENT_AND_LIVE_INSTRUMENT_STATUS_REQUIRED",
            "Do not apply one A-share limit or lot rule to every board.",
        ),
        shorting_default="LONG_ONLY_UNLESS_ACCOUNT_ELIGIBILITY_AND_LIVE_BORROW_RESOLVE",
        margin_policy="ACCOUNT_AND_BROKER_RULES_REQUIRED",
        sources=(SSE_SOURCE, SZSE_SOURCE, BSE_SOURCE),
        notes=("Venue and segment were not fully resolved.",),
    )


def _us_snapshot(venue: str | None, security_type: str, as_of: date) -> MarketRuleSnapshot:
    venue_source = NYSE_SOURCE if venue == "XNYS" else NASDAQ_SOURCE if venue == "XNAS" else SEC_HOURS_SOURCE
    transition = as_of >= US_INTRADAY_MARGIN_VALID_FROM
    margin_policy = (
        "BROKER_TRANSITION_STATE_REQUIRED; FIRMS_MAY_TRANSITION_THROUGH_2027-10-20"
        if transition
        else "ACCOUNT_TYPE_AND_BROKER_DAY_TRADING_RULES_REQUIRED"
    )
    version_date = "2026-06-04" if transition else "2024-05-28"
    return MarketRuleSnapshot(
        rule_version=f"US-{venue or 'NMS'}-{version_date}",
        market=Market.US,
        venue=venue,
        segment="NMS",
        security_type=security_type,
        valid_from=(
            US_INTRADAY_MARGIN_VALID_FROM if transition else US_T1_VALID_FROM
        ),
        valid_to=None,
        timezone="America/New_York",
        regular_sessions=US_REGULAR_SESSIONS,
        settlement_cycle="T+1_STANDARD_FOR_MOST_BROKER_DEALER_SECURITIES_TRANSACTIONS",
        same_day_resale=TriState.UNKNOWN,
        quantity_rule=QuantityRule(
            buy_minimum_shares=1,
            buy_increment_shares=1,
            odd_lot_sell_policy="WHOLE_SHARE_EXCHANGE_ORDER; FRACTIONAL_TRADING_IS_BROKER_SPECIFIC",
            scope_note="Broker fractional-share services are outside the exchange-order rule.",
        ),
        price_rule=PriceRule(
            base_tick=None,
            standard_daily_limit_pct=None,
            dynamic_guard="LIVE_NBBO_LULD_HALT_AND_VENUE_RULES_REQUIRED",
            scope_note="U.S. NMS stocks use dynamic protections; daily OHLC cannot reconstruct LULD.",
        ),
        shorting_default="LONG_ONLY_UNLESS_LOCATE_BORROW_RULE201_AND_BROKER_PERMISSION_RESOLVE",
        margin_policy=margin_policy,
        sources=(
            SEC_T1_SOURCE,
            SEC_HOURS_SOURCE,
            venue_source,
            LULD_SOURCE,
            FINRA_MARGIN_SOURCE,
        ),
        notes=(
            "Same-day resale depends on cash or margin account state and broker controls.",
            "Extended-hours eligibility and fractional trading are broker and venue specific.",
        ),
    )


def rules_at(
    *,
    market: Market,
    as_of: date,
    venue: str | None = None,
    segment: str | None = None,
    security_type: str = "COMMON_STOCK",
) -> RuleResolution:
    if as_of > VERIFIED_AT:
        return RuleResolution(
            status=RuleResolutionStatus.UNKNOWN,
            as_of=as_of,
            snapshot=None,
            unknowns=(
                "The requested date is later than the bundled rulebook verification date; refresh from primary sources.",
            ),
        )
    normalized_venue = _normalized(venue)
    normalized_segment = _normalized(segment)
    normalized_security_type = _normalized(security_type) or "COMMON_STOCK"

    if market is Market.CN:
        if as_of < CN_RULES_VALID_FROM:
            return RuleResolution(
                status=RuleResolutionStatus.UNKNOWN,
                as_of=as_of,
                snapshot=None,
                unknowns=(
                    "No bundled CN rule snapshot covers this historical as-of date.",
                ),
            )
        if normalized_venue == "BSE" and normalized_segment is None:
            normalized_segment = "BSE"
        if normalized_venue is None or normalized_segment is None:
            return RuleResolution(
                status=RuleResolutionStatus.PARTIAL,
                as_of=as_of,
                snapshot=_cn_generic_snapshot(),
                unknowns=(
                    "venue",
                    "segment",
                    "live_trading_calendar",
                    "live_instrument_status",
                    "broker_account_rules",
                ),
            )
        snapshot = _cn_snapshot(normalized_venue, normalized_segment)
        if snapshot is None:
            return RuleResolution(
                status=RuleResolutionStatus.UNKNOWN,
                as_of=as_of,
                snapshot=None,
                unknowns=(
                    f"Unsupported CN venue/segment: {normalized_venue}/{normalized_segment}",
                ),
            )
        if normalized_security_type != "COMMON_STOCK":
            return RuleResolution(
                status=RuleResolutionStatus.PARTIAL,
                as_of=as_of,
                snapshot=replace(snapshot, security_type=normalized_security_type),
                unknowns=(
                    "The bundled quantity and price rules are scoped to ordinary common stock.",
                    "live_trading_calendar",
                    "live_instrument_status",
                    "broker_account_rules",
                ),
            )
        return RuleResolution(
            status=RuleResolutionStatus.RESOLVED,
            as_of=as_of,
            snapshot=snapshot,
            unknowns=(
                "live_trading_calendar",
                "live_instrument_status",
                "broker_account_rules",
            ),
        )

    if market is Market.US:
        if as_of < US_T1_VALID_FROM:
            return RuleResolution(
                status=RuleResolutionStatus.UNKNOWN,
                as_of=as_of,
                snapshot=None,
                unknowns=(
                    "No bundled US rule snapshot covers this historical as-of date.",
                ),
            )
        if normalized_venue not in (None, "XNYS", "XNAS"):
            return RuleResolution(
                status=RuleResolutionStatus.UNKNOWN,
                as_of=as_of,
                snapshot=None,
                unknowns=(f"Unsupported US venue: {normalized_venue}",),
            )
        snapshot = _us_snapshot(
            normalized_venue,
            normalized_security_type,
            as_of,
        )
        status = (
            RuleResolutionStatus.RESOLVED
            if normalized_venue is not None
            and normalized_security_type in ("COMMON_STOCK", "ADR")
            else RuleResolutionStatus.PARTIAL
        )
        unknowns = [
            "live_trading_calendar",
            "live_luld_and_halt_state",
            "account_and_broker_rules",
        ]
        if normalized_venue is None:
            unknowns.insert(0, "venue")
        if normalized_security_type not in ("COMMON_STOCK", "ADR"):
            unknowns.insert(0, "security_type_rule_scope")
        return RuleResolution(
            status=status,
            as_of=as_of,
            snapshot=snapshot,
            unknowns=tuple(unknowns),
        )

    return RuleResolution(
        status=RuleResolutionStatus.UNKNOWN,
        as_of=as_of,
        snapshot=None,
        unknowns=(f"Unsupported market: {market}",),
    )
