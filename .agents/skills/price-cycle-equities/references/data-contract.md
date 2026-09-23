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

DataSet 通过 `instrument_identity_assurance` 保存身份保证；报告对应字段为
`instrument.identity_assurance`。当前 EODHD adapter 只验证有限的 provider-neutral
代码与后缀映射，不拥有完整历史证券主数据，因此固定为
`symbol_route_inferred_not_master_verified`。报告必须加入
`INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED`，并在 `missing_capabilities` 保留
`provider_verified_instrument_master_identity`。不能把代码映射成功写成发行人、
股份类别或历史挂牌身份已经由 provider 主数据验证。当前 EODHD 远程主标的仅支持
`COMMON_STOCK`；ADR 若由用户 CSV 提供，可继续作为未验证研究范围。

## 时间语义

所有时间存 UTC，并保留交易所时区：

    event_time    经济事件或行情实际发生时间
    available_at 原始来源最早公开时间
    ingested_at  本系统收到该版本的时间
    known_at     策略最早允许使用的时间

必须满足 known_at 不早于 available_at 和 ingested_at。回测只允许使用
known_at <= decision_time 的观察值。只有日期、没有时刻时，采用保守的收盘后可知策略，
并记录 timestamp_policy。当前 EODHD“最近收盘”以市场当地时间 23:00 为保守 finalized
cutoff：23:00 前排除当日日线，避免把尚未稳定的 bar 当作已完成数据；这不是供应商发布
时刻的保证。

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

供应商按当前请求返回的历史拆股和调整结果，不自动等于每个历史决策时点当时可见的
版本。若缺少逐时点的公司行动版本与 `known_at`，必须报告
`ADJUSTED_PRICE_POINT_IN_TIME_RISK`，并在 `missing_capabilities` 中保留
`point_in_time_adjusted_price_vintage`。这类数据可以用于当前结构研究，不能直接
宣称是无前视偏差的 point-in-time 回测数据。

## UNKNOWN 与三值逻辑

缺失值表示为：

    value: null
    status: UNKNOWN
    reason: not_reported | source_missing | not_yet_available |
            stale | conflicted | unsupported

布尔条件为 TRUE、FALSE 或 UNKNOWN。任何插值或替代指标必须记录 imputed、方法与来源。
UNKNOWN 不等于 FALSE：例如价格结构已满足而供应商成交量语义未验证时，可以保留
“价格结构候选”，但量能确认与量能反证都必须为 UNKNOWN，不能据此声称已经完成量价验证。

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

`snapshot_id` 必须是内容或规范化请求快照的 64 位小写 SHA-256 摘要。上游版本号、
ETag 或修订号应单独放入经过公开标签校验的 `revision_id`，不能把 URL、路径或凭证
放进快照字段。`dataset.source` 必须是简短公开标签，并与 instrument 工件的
`source_label` 一致。

Provider 还必须在注册时声明 `assurance_mode`。只有
`user_supplied_unverified` 类型可使用整组 `user_supplied_not_verified`
质量值并保留 `volume_completeness=null`；`provider_verified` 类型不能借用这一
豁免，且结果的价格口径必须由 provider 验证。`provider_verified` 只表示 adapter
通过了它声明的硬契约，不表示身份、价格、成交量、市场规则和历史版本等每个维度都已
完全验证；各维度仍由 lineage 字段、warnings 和 missing_capabilities 分别说明。

DataSet 必须显式携带 `volume_evidence_eligible`。当它为 true 时，
`vendor_reported_unverified`、`partial_venue`、`volume_basis=unknown`、
`zero_volume_policy=unknown` 或其他无法验证的成交量语义必须硬失败；当且仅当它为
false 时，才可保留这些 bar 用于价格结构研究，同时关闭所有 volume-derived 指标与
证据。当前 EODHD 正是这一例外：`volume_scope=vendor_reported_unverified`、
`volume_basis=unknown`、`zero_volume_policy=unknown` 且
`volume_evidence_eligible=false`。此时：

- `volume_sma20`、`volume_ratio` 和量能条件为 UNKNOWN；
- 报告 `data_quality.evidence_mode` 为
  `price_structure_only_volume_unconfirmed`；
- warnings 至少包含 `VOLUME_CONFIRMATION_DISABLED`，并可补充供应商量能质量警告；
- missing_capabilities 包含 `verified_complete_volume_semantics`；
- 价格结构候选可以存在，但不能描述为已经获得成交量确认。

`volume_completeness` 只计算返回 bar 中 volume 字段是否存在，是字段覆盖率，不是
“完整市场成交量”的证明。它不能覆盖 `volume_scope`、`volume_basis` 或
`volume_evidence_eligible` 的结论；`volume_completeness=1.0` 仍可能伴随全部
量能证据 UNKNOWN。

Provider 不得计算或覆写策略指标。局部场所行情、成交量覆盖不足、缺失量填零、
身份或价格口径不一致，以及标准化结果仍含未来数据，都属于硬失败；可以换用下一
等价来源，但不得把不等价字段拼接后继续评分。唯一例外是上述明确关闭量能证据的
价格结构研究模式。原始导出中截止日后的行可以先排除并记录数量。少于 200 根历史、
稍旧或无基准是软警告。

`retryable` 表示是否适合同源重试；`fallback_allowed` 表示是否可换到
独立来源，两者不得混为一个开关。只有一个远程 adapter 时，即使尝试对象包含
`fallback_allowed`，也不能宣称已经存在实际远程备援。
