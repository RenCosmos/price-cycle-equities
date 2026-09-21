# 输出契约

默认先给人类可读摘要；用户要求程序化结果时再附 JSON。

## Markdown 顺序

1. **范围**：标的、市场、as_of、周期、数据来源。
2. **一句话结论**：主候选阶段与最大不确定性。
3. **候选阶段**：每个候选的支持证据、反证和置信度。
4. **CAN SLIM 证据**：C/A/N/S/L/I/M 分别为 TRUE、FALSE 或 UNKNOWN。
5. **市场环境**：指数、行业和相对强度背景。
6. **条件式计划**：仅在用户要求时给出触发、失效、风险和不可交易情形。
7. **数据质量与未知项**。
8. **规则来源与参数**：列出重要 provenance 和用户覆盖。

## 程序化字段

    schema_version
    generated_at
    as_of
    instrument
    market_context
    data_quality
      benchmark_rows_read
      benchmark_rows_used
      benchmark_future_rows_ignored
      benchmark_not_yet_known_rows_ignored
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

`data_lineage.attempts` 必须按优先级记录 SUCCESS、跳过或失败原因，
并分别保存 retryable 与 fallback_allowed。错误文本不得包含 token、完整本机路径或
带凭证的 URL。来源工件分别记录主标的和基准，不能只保留一个模糊的 source 字符串。
旧式直接调用若没有基准工件标识，必须输出 UNKNOWN 基准工件并给出
`BENCHMARK_LINEAGE_NOT_SUPPLIED`，不能伪造文件名或哈希。

候选阶段字段使用由六个来源阶段家族展开的八个工程名称：Reversal Extension、
Wedge Pop、Upside EMA Crossback、Upside Base n' Break、Exhaustion Extension、
Wedge Drop、Downside EMA Crossback 或 Downside Base n' Break。方向展开属于
author_interpretation；不要把它称为 Oliver Kell 原始“八阶段”，也不要用
“阶段 1/2/3”代替，除非同时给出明确映射来源。

如果没有置信度为 LOW、MEDIUM 或 HIGH 且净证据分为正的候选，一句话结论必须为
UNKNOWN，不得从 NOT_SUPPORTED 或 UNKNOWN 项中强选“最支持阶段”。

不要默认加入 +1R、+2R、固定止盈百分比或固定分批比例。这些如被采用，必须显示为
research_parameter 或 user_override，并同时给出不用该参数时的结构化管理方案。

trade_plan 若存在，必须包含 status=conditional，并区分 signal_time、decision_time、
order_time、eligible_time 和可能的 fill_time。
