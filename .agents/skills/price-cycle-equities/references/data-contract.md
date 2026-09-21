# 跨市场数据契约

本契约确保证券身份稳定、回测只使用当时可见数据、分析价与成交价不混用，
并让市场规则可以随日期变化。

## 永久证券身份

股票代码不是永久主键。至少区分：

    issuer_id      法律发行主体
    security_id    某一证券或股份类别
    listing_id     某证券在某交易场所的挂牌
    instrument_id  引擎内部不可变主键，默认对应 listing

Ticker、简称和外部标识通过 SymbolAlias 映射，并带 valid_from 与 valid_to。
同时保存 venue、segment、currency、timezone、security_type 和 listing_status。
改名或换代码不应自动切断历史；新股份类别、ADR 与普通股分别建模。

## 时间语义

所有时间存 UTC，并保留交易所时区：

    event_time    经济事件或行情实际发生时间
    available_at 原始来源最早公开时间
    ingested_at  本系统收到该版本的时间
    known_at     策略最早允许使用的时间

必须满足 known_at 不早于 available_at 和 ingested_at。回测只允许使用
known_at <= decision_time 的观察值。只有日期、没有时刻时，采用保守的收盘后可知策略，
并记录 timestamp_policy。

## Bar

建议字段：

    instrument_id, interval, session_type
    start_time, end_time, event_time
    available_at, ingested_at, known_at
    open_raw, high_raw, low_raw, close_raw
    volume_raw, turnover_raw, trade_count
    currency, adjustment_factor, adjustment_basis
    source_id, revision_id, supersedes_revision_id
    quality_status

日线收盘价只能在收盘并由数据源发布后使用。用完整当日日线生成的信号，最早在下一
可交易时点成交，除非另有明确的收盘竞价模型。历史更正必须新增 revision_id，
不能覆盖旧版本。

## FundamentalFact

采用一个事实一行，至少包含：

    issuer_id, security_id, metric_id, source_metric
    value, unit, currency
    fiscal_period_start, fiscal_period_end, fiscal_period_type
    accounting_standard, consolidation_scope, is_gaap
    filing_type, published_at, available_at, ingested_at, known_at
    revision_id, supersedes_revision_id, source_document_id
    quality_status

财报期末日不是市场可知日。修订或重述形成新版本。A 股累计值转单季值时标记
derived、公式和输入版本。GAAP、Non-GAAP、归母净利润与扣非归母净利润不得
映射为一个无来源指标。

## CorporateAction

公司行动是有版本的事件源，至少包含 action_type、announced_at、known_at、
ex_time、effective_at、ratio、cash_amount、currency、source_id 和 revision_id。
拆并股、分红、配股、分拆、合并、改代码、转板与退市分别记录。

## 三种价格

- raw_price：交易所实际报价；订单、价格限制和成交仿真使用它。
- adjusted_price：由原始价格和公司行动推导；仅用于连续指标、收益和图表，声明复权口径。
- tradable_price：某订单在具体时间、账户、券商和规则下允许申报或可能成交的价格。

禁止用复权价模拟真实订单；禁止用未来才知道的公司行动修正过去实时信号；
禁止把触及涨跌停或价格带等同于一定可以成交。

## UNKNOWN 与三值逻辑

缺失值表示为：

    value: null
    status: UNKNOWN
    reason: not_reported | source_missing | not_yet_available |
            stale | conflicted | unsupported

布尔条件为 TRUE、FALSE 或 UNKNOWN。任何插值或替代指标必须记录 imputed、方法与来源。

## 有效日期化市场规则

统一入口概念：

    rules_at(instrument_id, timestamp, account_profile,
             broker_profile, session_type)

返回日历、交易时段、最小价位、数量规则、价格限制、停复牌、最早可卖时间、结算、
做空资格、账户适当性、券商规则，以及 source_url、rule_version、valid_from 和
valid_to。关键规则无法解析时 fail_closed：拒绝生成可执行订单并说明缺口。

## 可复现运行

每次分析或回测保存：

    skill_version
    strategy_spec_version
    engine_version
    data_schema_version
    rulebook_version
    execution_model_version
    config_hash
    data_snapshot_id

## Provider 获取边界

数据提供器与策略引擎必须隔离。统一调用链为：

    DataRequest
      → ProviderRegistry / ProviderRouter
      → ProviderLoadResult
      → DataSet
      → 指标、事件与阶段判断

每个结果必须记录 provider 尝试链和一个或多个 SourceArtifact。工件至少包含：

    role, provider_id, source_label, artifact_name
    snapshot_id, price_basis, market_data_scope
    volume_scope, volume_basis, zero_volume_policy
    timestamp_policy, retrieved_at, revision_id

Provider 还必须在注册时声明 `assurance_mode`。只有
`user_supplied_unverified` 类型可使用整组 `user_supplied_not_verified`
质量值并保留 `volume_completeness=null`；`provider_verified` 类型不能借用这一
豁免，且结果的价格口径必须由 provider 验证。

Provider 不得计算或覆写策略指标。局部场所行情、成交量覆盖不足、缺失量填零、
身份或价格口径不一致，以及标准化结果仍含未来数据，都属于硬失败；可以换用下一
等价来源，但不得把不等价字段拼接后继续评分。原始导出中截止日后的行可以先排除并
记录数量。少于 200 根历史、稍旧或无基准是软警告。

`retryable` 表示是否适合同源重试；`fallback_allowed` 表示是否可换到
独立来源，两者不得混为一个开关。
