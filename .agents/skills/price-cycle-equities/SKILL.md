---
name: price-cycle-equities
description: "Analyze, explain, screen, and review A-share and U.S. equities with the Cycle of Price Action and CAN SLIM evidence. Use for phase assessment, conditional trade plans, cross-market adaptation, and research design; do not use for automatic order execution or guaranteed-return claims."
---

# Price Cycle Equities

Use an evidence chain instead of a single indicator. Answer in the user's language.

## Select a mode

Classify the request before acting:

- Explain: teach the strategy, a term, or a market difference.
- Analyze: assess one or more phase candidates from dated data or charts.
- Plan: add conditional entry, invalidation, and position-risk logic.
- Screen: compare a universe at one as-of time; ranking is research priority, not a buy instruction.
- Review: audit a past trade using only information that was available then.
- Research: design or run backtests, sensitivity tests, and cross-market validation.

Always read [references/strategy-spec.md](references/strategy-spec.md) and
[references/provenance-policy.md](references/provenance-policy.md).

- For analysis workflows, read [references/operating-modes.md](references/operating-modes.md).
- For reports, read [references/output-contract.md](references/output-contract.md).
- When consuming market, fundamental, or backtest data, read [references/data-contract.md](references/data-contract.md).
- When selecting, adding, or falling back between data sources, read
  [references/data-providers.md](references/data-providers.md).
- When validating provider routes or credential references, also read
  [references/provider-config.md](references/provider-config.md).
- For A-shares, read [references/markets/cn-equities.md](references/markets/cn-equities.md).
- For U.S. equities, read [references/markets/us-equities.md](references/markets/us-equities.md).
- When evaluating dated trading constraints, read
  [references/market-rules.md](references/market-rules.md) and use `rules_at`.
- When adding another market, read [references/markets/adding-market.md](references/markets/adding-market.md).
- When checking attribution, read [references/sources.md](references/sources.md).
- When the user supplies daily OHLCV CSV data, read
  [references/csv-analysis.md](references/csv-analysis.md) and use the deterministic
  `scripts/analyze.py` workflow before interpreting the result.
- When the user asks to fetch and analyze one named stock automatically, read
  [references/remote-analysis.md](references/remote-analysis.md) and use the
  explicit remote-provider workflow.

## Non-negotiable rules

1. State the as-of time, market, instrument, timeframe, and data source. Retrieve and timestamp any claim about current conditions.
2. Treat missing data as UNKNOWN, never as zero, failure, or success.
3. Treat the cycle as a repeatable, skippable, and sometimes ambiguous evidence model, not a rigid state machine. Return candidate phases, supporting evidence, contradictory evidence, and confidence.
4. Treat price as primary, volume as confirmation, and moving averages as trend and risk references. In this project, CAN SLIM supplies selection evidence; it does not replace price action or become a native Cycle phase.
5. Separate source rules, author interpretation, market adaptation, research parameters, and user overrides.
6. Never mix raw, adjusted, and tradable prices. Evaluate fundamentals by when they became known, not by period end.
7. A TradePlan is conditional research output, not an order. Do not send or represent a live order without explicit authorization.
8. Never promise returns. If evidence is insufficient, state the gap and the smallest useful data request.

## Standard workflow

1. Define scope and as-of time.
2. Audit data completeness, point-in-time validity, and market constraints.
3. Assess market regime and relative-strength context.
4. Summarize CAN SLIM fundamental and catalyst evidence.
5. List evidence for and against each plausible Cycle phase.
6. If a plan is requested, define structural invalidation before sizing risk. Do not invent precise values for unknown parameters.
7. Follow the output contract and include provenance and data-quality notes.

## Deterministic remote single-symbol workflow

For a natural-language request about one stock, extract `market`, a provider-neutral
`symbol`, and `as_of`, then call the structured analyzer. Natural language is the Skill
orchestration layer; the CLI does not parse prose. Use a six-digit listing code such as
`600519` for A-shares and a ticker such as `AAPL` for U.S. equities. If a company name,
market, or code is ambiguous, ask only for the missing market/code and never guess.

When the user says “latest close” or equivalent, use the current date in the requested
market as `as_of`; the provider must still return only the latest finalized daily bar no
later than that date. Describe this as end-of-day research, not live or intraday data.

Remote access requires an explicitly named provider config and a credential already
stored in the fixed local environment variable. Never ask the user to paste a token into
chat, TOML, a CLI flag, a report, or Git. The current runnable remote route is EODHD
daily EOD plus splits, with `split_adjusted` analysis prices. The CLI automatically uses
the default ETF proxies `510300` for CN and `VTI` for US. Remote overrides must be in
the adapter's approved ETF-proxy list: CN `510050/510300/510500/588000/159915/159919`;
US `VTI/SPY/QQQ/IWM`. State that these proxies support relative-strength context; they
do not by themselves determine CAN SLIM factor M.

The EODHD remote route currently accepts `COMMON_STOCK` requests only. Its code and
vendor-suffix mapping does not prove issuer, share class, security type, listing status,
or historical venue identity. Preserve
`INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED` and
`provider_verified_instrument_master_identity` in the report; do not describe a
successful route as verified security master data.

Run one `DataRequest` and one report per instrument. Keep each request, lineage,
failure, and output independent so a later batch orchestrator can loop over the same
pipeline. Do not claim that multi-stock screening is implemented in this milestone.

The current EODHD volume field has not been independently verified for the complete
market/session semantics required by this strategy. Its `volume_basis` and
`zero_volume_policy` are therefore UNKNOWN and `volume_evidence_eligible=false`.
The adapter sets every volume-derived feature and confirmation to UNKNOWN. Price
structure candidates may still be detected, but label them “price structure only;
volume unconfirmed” and cap confidence at MEDIUM. Never turn missing volume into FALSE,
zero, or a confirmed event.

The deterministic engine currently consumes daily bars only, so weekly structure is
UNKNOWN. Daily OHLCV also does not supply point-in-time C/A/N/S/L/I/M evidence; keep
those CAN SLIM factors UNKNOWN. Adjusted EOD history is a current vendor snapshot and
is not a strict point-in-time backtest archive. The report remains a conditional
research plan, not an instruction or order.

The current CN remote route supports inferable SSE/SZSE common-stock codes and only the
explicit ETF proxies listed above; it does not verify BSE, arbitrary `5`/`1` codes,
or bare index codes such as `000300`. The U.S. `.US` route does not independently
verify the listing venue, so do not provide or infer `XNAS`/`XNYS` in remote mode.
Before local market time 23:00, the current local date is conservatively excluded from
the remote EOD query, so “latest close” cannot treat a possibly unfinished current-day
row as finalized data.

## Deterministic CSV workflow

Use the bundled analyzer for a dated daily-bar CSV instead of recomputing indicators
manually. Require market, symbol, as-of date, source, and price basis. A benchmark is
optional, but its file and symbol must be supplied together.

The analyzer loads CSV through the provider-neutral data router, then produces JSON
and Markdown research reports. Treat its event rules and
thresholds as experimental research parameters, not validated trading edges. It does
not retrieve remote data in CSV mode, evaluate current exchange rules, size a position,
or create an order. Review all UNKNOWN fields and warnings before explaining the result.

Do not enable a remote provider without an explicit user choice and any required
credentials or license. Reject partial-venue price or volume data, future-known rows,
and silent price-basis changes before running Cycle evidence scoring.

Provider configuration is explicit and fail-closed. Never auto-discover a config or
`.env` file, accept a credential value in TOML or a CLI flag, or treat user configuration
as proof of data coverage. The config validator is always offline. Only
`analyze.py --provider-config ...` with `allow_network=true` may invoke the selected
remote route. EODHD is the first runnable route; Tushare remains blocked until its secure
POST and complete-volume semantics are verified from primary sources. There is not yet
a second runnable remote fallback, so never claim multi-source resilience.

The report keeps Oliver Kell's six public phase families distinct from the eight
directional candidates used by this project's deterministic output. Do not describe
the eight candidates as eight original Kell phases.

Market-rule resolution is fail-closed. A resolved exchange snapshot still does not
make a report execution-ready because the live calendar, instrument state, account,
broker, borrow, price-band, and fill information can remain unknown. If the requested
date is later than the rulebook's verification date, refresh primary sources first.
