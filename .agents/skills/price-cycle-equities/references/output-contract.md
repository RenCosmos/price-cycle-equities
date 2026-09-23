# 输出契约

默认先给人类可读摘要；用户要求程序化结果时再附 JSON。所有输出是研究结果，不是订单，
也不承诺收益。

## Markdown 顺序

1. **范围**：标的、市场、as_of、周期、数据来源。
2. **一句话结论**：主候选阶段与最大不确定性。
3. **候选阶段**：每个候选的支持证据、反证和置信度。
4. **CAN SLIM 证据**：C/A/N/S/L/I/M 分别为 TRUE、FALSE 或 UNKNOWN。
5. **市场环境**：指数、行业、相对强度和周线状态。
6. **条件式计划**：仅在用户要求时给出触发、失效、风险和不可交易情形。
7. **数据质量与未知项**。
8. **规则来源与参数**：列出重要 provenance 和用户覆盖。

## 程序化字段

    schema_version
    generated_at
    as_of
    instrument
      identity_assurance
    market_context
      benchmark_symbol
      technical_snapshot
      weekly_structure
        status
        reason
      market_rules_status
      market_rules
      execution_ready
    data_quality
      status
      rows_read
      rows_used
      first_bar_date
      latest_bar_date
      future_rows_ignored
      not_yet_known_rows_ignored
      benchmark_rows_read
      benchmark_rows_used
      benchmark_future_rows_ignored
      benchmark_not_yet_known_rows_ignored
      calendar_days_stale
      evidence_mode
      warnings[]
      missing_capabilities[]
    data_lineage
      selected_provider_id
      source_label
      assurance_mode
      fallback_used
      attempts[]
      artifacts[]
      price_basis_assertion
      market_data_scope
      volume_scope
      volume_basis
      volume_completeness
      zero_volume_policy
      artifact_name
      data_snapshot_id
    phase_taxonomy
    candidate_phases[]
      phase
      phase_family
      directional_variant
      score
      confidence
      evidence_for[]
      evidence_against[]
      unknowns[]
    observed_events[]
    canslim
    trade_plan
    provenance[]
    versions

confidence 表达相对证据强弱，不是假装精确的成功概率。除非经过校准研究，不输出
诸如“上涨概率 73%”的数字。


当前 EODHD 只完成代码与供应商路由推断，不具备证券主数据验证。输出必须设置
`instrument.identity_assurance=symbol_route_inferred_not_master_verified`，
`warnings` 包含 `INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED`，并在
`missing_capabilities` 保留
`provider_verified_instrument_master_identity`。不得据此断言发行人、股份类别、
挂牌状态或历史 venue 已获验证。

## 数据质量解释

`data_quality.evidence_mode` 明确当前判断能使用什么证据：

- `price_and_volume`：provider 契约允许使用价格和成交量证据；
- `price_structure_only_volume_unconfirmed`：只使用价格结构，所有量能确认保持
  UNKNOWN，不能写成“放量突破已确认”。

当远程 EODHD 数据的供应商成交量语义未验证时，输出至少应体现：

- `warnings` 包含 `VOLUME_CONFIRMATION_DISABLED`，并可包含
  `VOLUME_QUALITY_NOT_PROVIDER_VERIFIED`；
- `missing_capabilities` 包含 `verified_complete_volume_semantics`；
- `volume_sma20`、`volume_ratio` 和量能证据为 null/UNKNOWN；
- price-only 事件 payload 可用
  `confirmation=price_structure_only_volume_unknown` 明确其性质；
- 由于量能未确认，候选置信度最高封顶为 MEDIUM。

`volume_completeness=1.0` 只说明 bar 中 volume 字段覆盖完整，不证明其为完整市场成交量，
也不能改变 `volume_scope=vendor_reported_unverified` 的含义。

当前引擎只分析日线，所以
`market_context.weekly_structure.status=UNKNOWN`，原因字段必须说明尚未计算周线结构。
报告的 `missing_capabilities` 同时保留 `weekly_structure_confirmation`。不能用
日线 EMA 代替 Oliver Kell 框架中的周线背景。

非 raw 价格口径会产生 `ADJUSTED_PRICE_POINT_IN_TIME_RISK`。如果没有逐历史决策时点的
复权版本，`missing_capabilities` 包含 `point_in_time_adjusted_price_vintage`；
当前供应商返回的历史视图不能自动宣称是严格 point-in-time 数据。

CAN SLIM 的 C/A/N/S/L/I/M 不能从日线 OHLCV 自动推断。当前单股自动取数路径没有接入
点时财务、机构持仓、新闻催化剂和完整市场状态，所以七因子保持 UNKNOWN。默认基准的
技术相对强度也不等于 CAN SLIM 的 M 已经通过。

## 血缘与回退

`data_lineage.attempts` 必须按优先级记录 SUCCESS、跳过或失败原因，并分别保存
retryable 与 fallback_allowed。错误文本不得包含 token、完整本机路径或带凭证的 URL。
来源工件分别记录主标的和基准，不能只保留一个模糊的 source 字符串。旧式直接调用若
没有基准工件标识，必须输出 UNKNOWN 基准工件并给出
`BENCHMARK_LINEAGE_NOT_SUPPLIED`，不能伪造文件名或哈希。

`fallback_used=false` 只表示本次运行未切换来源，不证明存在备用源。dev.3 当前只有
EODHD 一个可运行远程来源，尚无真实远程故障切换。

## 阶段与计划语义

候选阶段字段使用由六个来源阶段家族展开的八个工程名称：Reversal Extension、
Wedge Pop、Upside EMA Crossback、Upside Base n' Break、Exhaustion Extension、
Wedge Drop、Downside EMA Crossback 或 Downside Base n' Break。方向展开属于
author_interpretation；不要把它称为 Oliver Kell 原始“八阶段”，也不要用
“阶段 1/2/3”代替，除非同时给出明确映射来源。

价格结构已满足但量能为 UNKNOWN 时，允许输出 price-only 候选。这遵循“价格为主、
成交量确认”的边界：UNKNOWN 不是 FALSE，但该候选也不是完整量价确认。若量能条件明确
为 FALSE，则不能把它改写成 UNKNOWN 来保留事件。

如果没有置信度为 LOW、MEDIUM 或 HIGH 且净证据分为正的候选，一句话结论必须为
UNKNOWN，不得从 NOT_SUPPORTED 或 UNKNOWN 项中强选“最支持阶段”。

不要默认加入 +1R、+2R、固定止盈百分比或固定分批比例。这些如被采用，必须显示为
research_parameter 或 user_override，并同时给出不用该参数时的结构化管理方案。

trade_plan 若存在，必须包含 `status=conditional` 与 `is_order=false`，并区分
signal_time、decision_time、order_time、eligible_time 和可能的 fill_time。
