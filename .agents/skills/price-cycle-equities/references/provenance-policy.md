# 规则来源与覆盖政策

每条重要规则或参数必须标注以下一种 provenance。目的不是增加术语，而是避免把
工程假设说成 Oliver Kell 或 CAN SLIM 的原始规则。

| 类型 | 含义 | 示例 |
|---|---|---|
| source_rule | 可直接追溯到原作者、一手课件或 CAN SLIM 原始资料 | Wedge Pop 不是简单均线金叉 |
| author_interpretation | 为消除歧义而做的保守解释 | 同时输出候选阶段和反证 |
| market_adaptation | 因市场制度或数据口径增加 | A 股买入后当日通常不可卖 |
| research_parameter | 必须通过回测和敏感性分析检验 | 量比阈值、ATR 倍数 |
| user_override | 用户主动选择 | 单笔账户风险、最大仓位 |

## 规则

1. source_rule 的含义改变时必须提升策略规范版本并记录来源。
2. market_adaptation 中的法定交易约束优先于策略信号和用户设置。
3. user_override 必须保留默认值、覆盖值、适用范围和理由。
4. UNKNOWN 不得因缺省值而变成 FALSE、0 或通过。
5. 同一结论若混合多种来源，在每个子结论后分别标注，不用一个标签掩盖差异。
6. 报告至少在“关键结论”和“参数”部分显示 provenance；普通叙述可以引用规则 ID。

## 参数登记

每个可调参数至少保存：

    parameter_id
    value
    unit
    provenance
    valid_scope
    valid_from
    source_or_rationale
    overridden_from

未经登记的精确阈值不能进入可复现分析或回测。
