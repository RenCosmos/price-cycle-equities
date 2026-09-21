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
    candidate_phases[]
      phase
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

候选阶段必须使用 strategy-spec 中的规范名称：Reversal Extension、Wedge Pop、
Upside EMA Crossback、Upside Base n' Break、Exhaustion Extension、Wedge Drop、
Downside EMA Crossback 或 Downside Base n' Break。不要用“阶段 1/2/3”代替，
除非同时给出明确映射来源。

不要默认加入 +1R、+2R、固定止盈百分比或固定分批比例。这些如被采用，必须显示为
research_parameter 或 user_override，并同时给出不用该参数时的结构化管理方案。

trade_plan 若存在，必须包含 status=conditional，并区分 signal_time、decision_time、
order_time、eligible_time 和可能的 fill_time。
