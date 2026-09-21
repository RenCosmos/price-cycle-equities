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
- For A-shares, read [references/markets/cn-equities.md](references/markets/cn-equities.md).
- For U.S. equities, read [references/markets/us-equities.md](references/markets/us-equities.md).
- When evaluating dated trading constraints, read
  [references/market-rules.md](references/market-rules.md) and use `rules_at`.
- When adding another market, read [references/markets/adding-market.md](references/markets/adding-market.md).
- When checking attribution, read [references/sources.md](references/sources.md).
- When the user supplies daily OHLCV CSV data, read
  [references/csv-analysis.md](references/csv-analysis.md) and use the deterministic
  `scripts/analyze.py` workflow before interpreting the result.

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

## Deterministic CSV workflow

Use the bundled analyzer for a dated daily-bar CSV instead of recomputing indicators
manually. Require market, symbol, as-of date, source, and price basis. A benchmark is
optional, but its file and symbol must be supplied together.

The analyzer loads CSV through the provider-neutral data router, then produces JSON
and Markdown research reports. Treat its event rules and
thresholds as experimental research parameters, not validated trading edges. It does
not retrieve live data, evaluate current exchange rules, size a position, or create an
order. Review all UNKNOWN fields and warnings before explaining the result.

Do not enable a remote provider without an explicit user choice and any required
credentials or license. Reject partial-venue price or volume data, future-known rows,
and silent price-basis changes before running Cycle evidence scoring.

The report keeps Oliver Kell's six public phase families distinct from the eight
directional candidates used by this project's deterministic output. Do not describe
the eight candidates as eight original Kell phases.

Market-rule resolution is fail-closed. A resolved exchange snapshot still does not
make a report execution-ready because the live calendar, instrument state, account,
broker, borrow, price-band, and fill information can remain unknown. If the requested
date is later than the rulebook's verification date, refresh primary sources first.
