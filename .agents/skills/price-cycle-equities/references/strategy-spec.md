---
title: Price Cycle Equities Strategy Fact Specification
spec_version: 1.0.0-draft
scope: CN and US equities
last_verified: 2026-09-21
---

# 策略事实规范

本文件定义策略语义，不规定数据供应商、券商接口或未经验证的固定阈值。

## 核心原则

| ID | 规则 | Provenance |
|---|---|---|
| CORE-01 | 价格行为是首要依据，成交量用于确认，均线用于观察趋势和管理风险。 | source_rule |
| CORE-02 | 单独穿越均线不构成完整形态；必须结合价格结构、枢轴和成交量。 | source_rule |
| CORE-03 | 10/20 日 EMA 用于中期趋势，50/200 日 SMA 用于更长期背景。资料中也会出现 10/21 的表达，不应把一天差异神化。 | source_rule / author_interpretation |
| CORE-04 | 周线理解大结构，日线管理交易，低周期只用于优化执行且服从高周期。 | source_rule |
| CORE-05 | 个股阶段应结合市场指数、行业和相对强度背景。 | source_rule |
| CORE-06 | 固定百分比、ATR 倍数、量比或评分门槛，若没有明确出处，均为 research_parameter。 | author_interpretation |

## 完整循环

    Reversal Extension
      → Wedge Pop
      → Upside EMA Crossback
      → Upside Base n' Break（可重复）
      → Exhaustion Extension（可能不出现）
      → Wedge Drop
      → Downside EMA Crossback
      → Downside Base n' Break（可重复）
      → Reversal Extension

这是观察框架，不是刚性状态机。阶段可以重复、跳过、失败或暂时含混；下跌侧通常
更快、更不规则。Wedge Drop 不要求之前一定出现 Exhaustion Extension；底部也可能
是圆弧形，而非典型恐慌式 Reversal Extension。以上为 source_rule；允许多个候选
阶段并存是 author_interpretation。

## 阶段定义

### Reversal Extension

- RE-01：下跌末段价格显著远离短期均线，随后快速反弹至均线附近，常伴随高成交量。source_rule
- RE-02：它表示潜在见底和心理变化，不是已经确认的底部。source_rule
- RE-03：新低后强收盘、反转柱、低位放量和高周期支撑是支持证据。source_rule
- RE-04：若没有形成枢轴或跟随，且继续跌破低点，则反转证据失败。source_rule
- RE-05：该阶段并非绝对不可交易，但日线波动常较大；较低风险的中期位置通常在后续 Wedge Pop 或 EMA Crossback。source_rule

### Wedge Pop

- WP-01：底部反弹后横向或略向下整理，波动收缩，10/20 EMA 靠拢。source_rule
- WP-02：首个有效枢轴向上突破并重新站上收紧的短期均线，形成趋势转变证据。source_rule
- WP-03：需要积极价格行为和累积性成交量支持，不等于均线金叉。source_rule
- WP-04：突破后迅速失守枢轴是失败证据；跳空和放量可以增强，但不是所有案例的硬条件。source_rule

### Upside EMA Crossback

- ECB-U-01：Wedge Pop 或低点强反弹后，第一次回测上升中的 10/20 EMA。source_rule
- ECB-U-02：窄幅价格柱、回撤收敛、均线或近端结构获得支持以及买盘重现是证据。source_rule
- ECB-U-03：第一次必须由事件历史判断，不能只看当前一根 K 线。author_interpretation

### Upside Base n' Break

- BNB-U-01：已确认上升趋势中横向整理，让均线追上，并形成新的紧凑枢轴。source_rule
- BNB-U-02：突破枢轴、积极价格行为和累积量支持延续。source_rule
- BNB-U-03：同一趋势可以出现多次；序号描述成熟度，不机械等同早期、中期或晚期。source_rule
- BNB-U-04：越靠后的 Base n' Break 通常越需谨慎；具体天数、收缩幅度和量比是 research_parameter。source_rule / research_parameter

### Exhaustion Extension

- EE-01：快速上涨后价格明显远离短期均线；日线和周线同时延伸时防御意义更强。source_rule
- EE-02：它是卖强、分批兑现和收紧风险的信号，不等于长期顶部已经确认。source_rule
- EE-03：高位拒绝、向下跳空、反转柱和卖出量增加会加强警告。source_rule
- EE-04：距离均线多远取决于个股性格和环境，固定百分比或 ATR 阈值是 research_parameter。source_rule / research_parameter

### Wedge Drop

- WD-01：上涨后价格收紧，随后在卖压增加时跌破短期均线，是较明确的趋势恶化证据。source_rule
- WD-02：可用于退出或保护多头利润；能否做空取决于市场、账户和可借条件。source_rule / market_adaptation
- WD-03：它可能只是重新筑底，也可能是更长期顶部；单一事件不能断言长期熊市。source_rule

### Downside EMA Crossback

- ECB-D-01：跌破均线后第一次反弹至下降中的短期均线并遇阻。source_rule
- ECB-D-02：阻力出现、卖方重新占优并向下脱离，是下跌延续证据。source_rule
- ECB-D-03：第一次必须由事件历史判断。author_interpretation

### Downside Base n' Break

- BNB-D-01：下跌趋势中形成小型横向整理并靠近下降均线。source_rule
- BNB-D-02：均线继续形成阻力，价格跌破整理区，是下跌延续证据。source_rule
- BNB-D-03：可重复发生，直至出现新的底部过程。source_rule

## CAN SLIM 的位置

Cycle 与 CAN SLIM 不是两个互不相关的机械模块。Kell 的方法根植于成长股、领导股
和相对强度思想，再用价格行为循环处理时机和风险。

| 因素 | 原始含义 | 本策略用途 | Provenance |
|---|---|---|---|
| C | 当前季度 EPS 与销售增长 | 近期成长加速证据 | source_rule |
| A | 年度盈利增长与质量 | 长期成长记录 | source_rule |
| N | 新产品、服务、管理层、产业变化或价格新高 | 催化和新趋势 | source_rule |
| S | 供给与需求 | 流通供给、价格和成交量证据 | source_rule |
| L | 领导股而非落后股 | 相对强度与同业比较 | source_rule |
| I | 机构赞助 | 需求质量证据之一 | source_rule |
| M | 市场方向 | 暴露和信号环境 | source_rule |

实施约束：

- CAN SLIM 提供候选股质量和背景，价格循环提供时机与风险边界。author_interpretation
- 优秀基本面不能替代有效枢轴和结构失效点。source_rule
- 原始 C/A 主要关注 EPS 与销售；A 股扣非归母利润等属于 market_adaptation。
- 财务硬阈值或综合分数如无明确出处，属于 research_parameter。

## 风险管理

| ID | 规则 | Provenance |
|---|---|---|
| RISK-01 | 建仓前先定义交易逻辑失效位置；初始止损决定风险并约束仓位。 | source_rule |
| RISK-02 | 止损可参考枢轴、近期摆动或整理低点、突破日低点或前一交易日低点。 | source_rule |
| RISK-03 | 突破失败且原风险参照失去时，应减仓或退出。 | source_rule |
| RISK-04 | 多头止损只随趋势向上收紧，不为容忍亏损而下移。 | source_rule |
| RISK-05 | 趋势早期可给予领导股更多空间；后期更积极卖强和锁定利润。 | source_rule |
| RISK-06 | 可以分批建立或退出，但批次数量和比例不是通用原规则。 | source_rule / research_parameter |
| RISK-07 | 无有效失效点或每股风险不为正时，不生成精确仓位。 | author_interpretation |
| RISK-08 | 涨跌停、停牌、T+1、LULD、做空和无法成交由市场执行层处理。 | market_adaptation |

仓位研究公式：

    planned_risk_amount = account_equity × selected_risk_fraction
    risk_per_share = abs(planned_entry - initial_stop)
    raw_quantity = planned_risk_amount / risk_per_share

该公式是 author_interpretation。风险比例、最大仓位和取整分别由 user_override、
research_parameter 或 market_adaptation 决定。

## 必须保持为研究参数

- 0.3%、0.5% 或任何固定单笔风险；
- 固定三等份建仓或减仓；
- 单股最大仓位 10%；
- 相对强度前 20%；
- 突破量比 1.3 倍；
- 延伸为 2.5 ATR 或历史第 95 百分位；
- 用 1 至 3 天机械定义突破失败；
- 统一的 EPS、销售或扣非利润阈值；
- 单一阶段分数及其确认门槛。
- 固定 +1R、+2R 或其他 R 倍数止盈规则。
