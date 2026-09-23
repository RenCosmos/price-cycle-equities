# 可切换数据提供器与来源策略

本文件定义 v0.2 数据获取层的选择、回退和质量边界。它不改变 Cycle 或 CAN SLIM
规则，也不授权自动购买数据、保存用户密钥或执行交易。

## 当前实现状态

- v0.2.0-alpha.2-dev.3 已实现 provider 契约、注册表、顺序回退、来源审计、
  `manual_csv` 适配器、失败关闭的 TOML 配置，以及 EODHD 联网日线适配器。
- EODHD 是当前唯一可运行的远程来源：支持 A 股和美股 COMMON_STOCK 主标的、
  白名单基准及拆股调整日线研究请求；不支持 ADR 远程请求，主标的与基准必须由同一
  provider 原子满足。
- Tushare 只有单标的 A 股 `daily` 请求与严格响应标准化 scaffold，可用固定响应
  测试；默认 transport 不发起请求，catalog 仍为 planned-only。
- CLI 现在可在 `--input` CSV 和 `--provider-config` 联网模式之间二选一，内部均
  通过 `DataRequest → ProviderRouter → DataSet` 加载。
- 配置不会自动发现，也不接受 token 值或任意环境变量名；凭证引用、市场能力和可信
  类别由代码目录拥有。详见 [Provider 配置与凭证边界](provider-config.md)。
- 虽然 Router 已支持顺序回退，当前远程链只有 EODHD，**没有真实的独立远程备用源**。
  EODHD 失败时会失败关闭，不得声称已经实现多源容灾。

## 不可破坏的边界

1. Provider 只提供和标准化事实；EMA、ATR、相对强度、Cycle 阶段及 CAN SLIM
   派生判断始终由本地引擎计算。
2. 请求必须显式包含市场、代码、截止日期和价格口径；provider 不得自行改用另一
   价格口径、代码或日期。
3. 第一份通过硬契约和质量门的数据即停止；所有尝试按优先级记录。
4. 不完整的单交易场所行情或成交量不能参与正式量价评分。已知为
   `partial_venue` 的结果必须回退或失败关闭。
5. 缺失成交量不得填成 0。Provider 必须声明成交量覆盖、调整口径、完整度和
   零成交量策略。
6. `vendor_reported_unverified` 只允许在 DataSet 明确设置
   `volume_evidence_eligible=false` 时通过。此时全部量能派生指标与量能证据为
   UNKNOWN，不能靠 `volume_completeness=1.0` 重新启用。
7. 主标的与基准进入标准 DataSet 后，都必须通过 `session_date <= as_of` 和
   `known_at <= 截止时间` 检查。原始导出文件可含截止日后的行，但必须先排除并
   记录排除数量，不能让它们进入指标计算。
8. 原始价格、复权分析价格和可成交价格保持分离；不得把 adjusted close 与 raw
   OHLC 混合成一组 K 线。
9. API key 只从环境变量或本机私密配置读取；仓库不保存 key、授权数据缓存或
   带 token 的 URL。
10. Router 在写入尝试链前统一清除 URL、token 和完整本机路径；provider 仍只应
    提交简短、可公开的错误说明。

## 标准对象

- `DataRequest`：统一的市场、证券、as_of、价格口径及基准请求。
- `ProviderLoadResult`：标准化 DataSet、聚合快照、质量声明及来源工件。
- `DataAssuranceMode`：在注册时把 provider 绑定为用户手工未验证数据或
  provider 已验证数据，防止远程适配器借用手工 CSV 豁免。
- `SourceArtifact`：分别记录 instrument/benchmark 的来源标签、快照、
  价格口径、成交量语义、时间政策和可选修订号。
- `ProviderAttempt`：记录优先级、结果、错误码、是否适合同源重试及是否
  允许换源。

`retryable` 与 `fallback_allowed` 是两个不同维度。例如认证失败通常不值得立刻
重试同一来源，但只有在用户实际配置了另一独立且等价的 provider 时，才可能换源。

`volume_completeness` 只是已返回行中 volume 字段的覆盖率，不证明这些数字包含
所有场所、所有常规时段或供应商定义下的完整市场成交量。成交量的经济语义必须由
`volume_scope`、`volume_basis` 与 `volume_evidence_eligible` 共同解释。

## 回退规则

| 情形 | 行为 |
|---|---|
| 未注册 provider、重复链、无效请求、无效 provider 配置 | 立即停止 |
| Provider 不支持市场或口径 | 记录 SKIPPED，尝试下一源 |
| 超时、限流、连接失败、上游暂时不可用 | 记录失败；有独立备用源时才允许回退 |
| 内容损坏、身份/日期/价格口径不符，或标准化结果仍含未来数据 | 拒绝该结果并回退 |
| 局部场所行情、缺失量填零，或启用了未经验证的量能证据 | 拒绝该结果并回退 |
| 供应商成交量语义未验证，但量能证据已明确禁用 | 可作价格结构研究；量能全部 UNKNOWN |
| 全部来源失败 | 不生成 DataSet，不运行策略，不输出半成品报告 |

少于 200 根 K 线、数据稍旧或没有基准属于软质量警告；它们不应在 Router 中被写死
为 provider 失败。

## 来源组合原则

不存在能够保证永远不受政策、网络、授权或商业变化影响的数据源。目标是把来源分为：

1. 大陆运营、通常便于大陆网络访问的来源；
2. 境外独立运营的备份来源；
3. 交易所或监管机构的一手校验来源。

选择顺序不能压过数据等价性。大陆优先源若只有局部成交量、错误复权或缺少点时字段，
必须回退，不能为了“可访问”而改变策略含义。当前 dev.3 尚未完成这种多来源组合；
它只提供可运行的 EODHD 起点和以后插入等价 adapter 的接口。

## 已核验目录

| 来源 | 覆盖与用途 | 约束 | 当前定位 |
|---|---|---|---|
| [Tushare Pro](https://tushare.pro/document/2) | A/美行情、财务、公司行动、日历和主数据 | 用户 token；官方 [HTTP 调用文档](https://tushare.pro/document/2?doc_id=130)与当前 SDK 仍使用明文 HTTP；A 股 `daily` 自 2026-07-06 增加 `ah_vol` 后未说明 `vol` 是否已含盘后量 | 大陆优先候选；已有离线 A 股解析 scaffold，但安全传输和成交量完整度明确前不得启用 |
| [Wind Client API](https://www.wind.com.cn/portal/zh/ClientApi/index.html) | 中美及全球多类数据 | 商业终端、本机客户端和许可；不得随 Skill 分发数据 | 仅规划用户自带许可的商业适配器 |
| [JQData](https://www.joinquant.com/help/api/doc?id=9845&name=JQDatadoc) | 主要为 A 股行情、财务和主数据 | 账号及购买权限；默认复权和停牌填充行为必须显式关闭或规范化 | 仅规划可选适配器 |
| [AKShare](https://akshare.akfamily.xyz/data/stock/stock.html) | A/美网页接口聚合 | 上游网页易变，存在登录、封禁和复权失效风险 | 实验性手动适配器；不得进入自动回退链 |
| [上交所](https://www.sse.com.cn/market/publicdata/)、[深交所](https://www.szse.cn/disclosure/listed/fixed/index.html)、[巨潮资讯](https://www.cninfo.com.cn/) | A 股公告、财务披露、公司行动和主数据的一手校验 | 未发现适合默认使用且承诺稳定的统一公共批量 API；自动抓取需另核条款 | 权威校验与人工证据源，不默认抓网页 |
| [EODHD](https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis) | A/美历史日线与拆股，公司还提供其他数据产品 | 用户 token、套餐和许可限制；当前 adapter 只取日线与拆股，在本地生成拆股调整 OHLC | **当前唯一可运行远程 adapter**；成交量语义未验证，量能证据关闭 |
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 美股申报、财务和发行人身份 | 无 key；需明确 User-Agent，并遵守[不超过 10 请求/秒](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits)；回测按 filed/as_of 截断 | 美股 CAN SLIM 财务权威主源规划 |
| [Alpaca Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api) | 美股行情、公司行动、主数据和日历 | 用户 API key；Basic 实时 IEX 是局部场所，只有 SIP 或经验证的全市场历史量可参与评分 | 美股境外行情备份规划 |
| [Massive](https://massive.com/docs/rest/stocks/overview) | 美股行情、公司行动和分层财务 | API key、套餐限制及严格市场数据许可 | 仅规划；用户确认适当许可后再启用 |
| [Nasdaq Symbol Directory](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs)、[NYSE 日历](https://www.nyse.com/trade/hours-calendars) | 美股官方主数据和日历校验 | 公共目录偏当前状态；完整历史 Daily List 需要订阅和许可 | 官方校验源 |

## 当前 EODHD 路径的边界

当前 adapter 使用固定 HTTPS 基址，分别请求历史 EOD 与拆股数据，然后在本地生成
`split_adjusted` OHLC。远程主标的只支持 `COMMON_STOCK`，不支持 ADR。A 股使用
provider-neutral 的六位代码并按代码规则映射到 EODHD 交易所后缀；美股使用
provider-neutral ticker。显式美股 venue 当前会被拒绝，因为组合路由不能独立证明
具体 XNAS/XNYS 挂牌身份。北交所当前不支持。

代码和路线映射只是推断，不是 provider 主数据验证。EODHD DataSet 声明
`instrument.identity_assurance=symbol_route_inferred_not_master_verified`；报告输出
`INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED` 警告，并在 `missing_capabilities`
列出 `provider_verified_instrument_master_identity`。

主标的和基准在一次加载中原子完成；任一失败则整次失败。远程代理基准采用精确白名单：
CN 仅 `510050`、`510300`、`510500`、`588000`、`159915`、`159919`；
US 仅 `VTI`、`SPY`、`QQQ`、`IWM`。默认仍为 CN `510300` 与 US `VTI`。
这些 ETF 是技术相对强度代理，不等于 CAN SLIM 的 M 因子结论；A 股裸指数代码如
`000300` 会被拒绝。

EODHD 返回的成交量记录为 `vendor_reported_unverified`，并明确声明
`volume_basis=unknown`、`zero_volume_policy=unknown`。即使每一根 bar 都有 volume，
`volume_completeness=1.0` 也只说明字段覆盖率；当前没有足够证据证明跨市场语义完整。
只有因为 DataSet 固定 `volume_evidence_eligible=false`、全部量能证据关闭，这组未知
语义才允许通过门禁。volume SMA、量比、量能确认和反证保持 UNKNOWN。价格结构仍可
产生候选，但报告必须明确它是 `price_structure_only_volume_unconfirmed`，并且最高
置信度封顶为 MEDIUM。

远程“最近收盘”使用市场当地时间的保守 finalized cutoff：当地 23:00 前排除当日日线，
只查询前一日或更早；23:00 后才允许查询当日。这是本项目的安全边界，不是对供应商
实际发布时间的外部保证。

历史拆股调整值是请求时供应商当前返回的历史视图，不带每个历史决策时点的调整版本。
因此报告会标记 `ADJUSTED_PRICE_POINT_IN_TIME_RISK`；它适合当前研究，不应被直接
宣称为严格 point-in-time 回测输入。

## 推荐的后续连接顺序（目标架构，不是当前能力）

- A 股行情：通过安全与量能验收的大陆源 → EODHD；Wind/JQData 仅在用户已有许可时插入。
- 美股行情：大陆可访问且通过完整度验收的来源 → EODHD → Alpaca SIP。
- A 股财务与公司行动：Tushare → EODHD，再以交易所或巨潮公告核验。
- 美股财务：SEC EDGAR → EODHD；其他来源只作交叉核对。
- AKShare、Massive 和需商业许可的官方历史文件均不默认启用。

## Tushare 当前失败关闭原因

官方 [A 股日线说明](https://tushare.pro/document/2?doc_id=27)确认 `daily` 是未复权行情、
停牌日不返回行、`vol` 单位为手，且数据在收盘后入库。当前 scaffold 因此只接受 raw
OHLCV、单一完整 TS code，并把 `known_at` 保守设为交易日 17:00（Asia/Shanghai）。
它固定向 `as_of` 前取 550 个日历日作为指标预热范围；这是数据提取边界，不是 Cycle
交易规则，起止日会进入无密钥快照。

但官方 HTTP 文档和官方 Python SDK 公开源码仍把 token 放入发往
`http://api.tushare.pro` 的 POST JSON。HTTPS 主机可达不等于官方承诺其鉴权 POST
契约稳定，因此不能猜测上线，更不能在失败后降级 HTTP。与此同时，日线接口新增
`ah_vol/ah_amount` 后，官方未说明原 `vol` 是否已包含盘后成交，不能据此声明
`volume_completeness=1.0`。本项目把这两点视为硬门：安全端点和成交量语义任一未知，
就不生成可进入策略引擎的 DataSet。该接口也没有历史版本号，因此未来即使启用，
抓取的旧 K 线只能标为“当前所见历史”，不能自动宣称是严格的 point-in-time 回测数据。

## 新增 provider 的验收清单

1. 用官方文档确认授权、限频、市场覆盖和复权语义。
2. 明确证券身份映射、时区、交易日、常规交易时段及成交量单位。
3. 输出完整 SourceArtifact；任何 unknown 不得伪装成通过。
4. 通过 raw/复权、未来数据、局部成交量、缺失量填零和 fallback 回归测试。
5. 相同标准化 DataSet 必须产生与 provider 名称无关的相同策略结果。
6. 只有用户显式选择并提供凭证后，才能启用远程 provider。
7. ProviderFailure 只能包含可公开的简短错误说明；上游异常中的敏感内容仍需在
   adapter 内先清除，Router 的统一脱敏是第二道防线。
