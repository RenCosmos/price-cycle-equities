# 可切换数据提供器与来源策略

本文件定义 v0.2 数据获取层的选择、回退和质量边界。它不改变 Cycle 或 CAN SLIM
规则，也不授权自动联网、购买数据或保存用户密钥。

## 当前实现状态

- v0.2.0-alpha.2-dev.1 已实现 provider 契约、注册表、顺序回退、来源审计、
  `manual_csv` 适配器，以及显式、离线、失败关闭的 TOML 配置校验骨架。
- 现有 CLI 参数保持不变，但内部已经通过 `DataRequest → ProviderRouter →
  DataSet` 加载。
- 尚未启用任何远程 provider。CSV 仍是唯一默认来源；下表远程来源均为规划候选。
- 配置不会自动发现，也不接受 token 值或任意环境变量名；凭证引用、市场能力和可信
  类别由代码目录拥有。详见 [Provider 配置与凭证边界](provider-config.md)。
- 首版 provider 必须原子满足主标的和可选基准请求，不做跨来源拼接。

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
6. 主标的与基准进入标准 DataSet 后，都必须通过 `session_date <= as_of` 和
   `known_at <= 截止时间` 检查。原始导出文件可含截止日后的行，但必须先排除并
   记录排除数量，不能让它们进入指标计算。
7. 原始价格、复权分析价格和可成交价格保持分离；不得把 adjusted close 与 raw
   OHLC 混合成一组 K 线。
8. API key 只从环境变量或本机私密配置读取；仓库不保存 key、授权数据缓存或
   带 token 的 URL。
9. Router 在写入尝试链前统一清除 URL、token 和完整本机路径；provider 仍只应
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

`retryable` 与 `fallback_allowed` 是两个不同维度。例如认证失败
通常不值得立刻重试同一来源，但在用户配置了独立备用源时可以换源。

## 回退规则

| 情形 | 行为 |
|---|---|
| 未注册 provider、重复链、无效请求、无效 provider 配置 | 立即停止 |
| Provider 不支持市场或口径 | 记录 SKIPPED，尝试下一源 |
| 超时、限流、连接失败、上游暂时不可用 | 记录失败，允许回退 |
| 内容损坏、身份/日期/价格口径不符，或标准化结果仍含未来数据 | 拒绝该结果并回退 |
| 局部场所行情、成交量覆盖不足、缺失量填零 | 拒绝该结果并回退 |
| 全部来源失败 | 不生成 DataSet，不运行策略，不输出半成品报告 |

少于 200 根 K 线、数据稍旧或没有基准属于软质量警告；它们不应在 Router 中被写死
为 provider 失败。

## 来源组合原则

不存在能够保证永远不受政策、网络、授权或商业变化影响的数据源。目标是把来源分为：

1. 大陆运营、通常便于大陆网络访问的来源；
2. 境外独立运营的备份来源；
3. 交易所或监管机构的一手校验来源。

选择顺序不能压过数据等价性。大陆优先源若只有局部成交量、错误复权或缺少点时字段，
必须回退，不能为了“可访问”而改变策略含义。

## 已核验的规划目录

| 来源 | 覆盖与用途 | 约束 | 规划定位 |
|---|---|---|---|
| [Tushare Pro](https://tushare.pro/document/2) | A/美行情、财务、公司行动、日历和主数据 | 用户 token；权限和频次随积分或单独授权变化，见[权限说明](https://tushare.pro/document/1?doc_id=108)。美股财务不宜作为点时主源 | 大陆优先的首批 opt-in 候选；美股行情必须先通过全市场成交量验收 |
| [Wind Client API](https://www.wind.com.cn/portal/zh/ClientApi/index.html) | 中美及全球多类数据 | 商业终端、本机客户端和许可；不得随 Skill 分发数据 | 仅规划用户自带许可的商业适配器 |
| [JQData](https://www.joinquant.com/help/api/doc?id=9845&name=JQDatadoc) | 主要为 A 股行情、财务和主数据 | 账号及购买权限；默认复权和停牌填充行为必须显式关闭或规范化 | 仅规划可选适配器 |
| [AKShare](https://akshare.akfamily.xyz/data/stock/stock.html) | A/美网页接口聚合 | 上游网页易变，存在登录、封禁和复权失效风险 | 实验性手动适配器；不得进入自动回退链 |
| [上交所](https://www.sse.com.cn/market/publicdata/)、[深交所](https://www.szse.cn/disclosure/listed/fixed/index.html)、[巨潮资讯](https://www.cninfo.com.cn/) | A 股公告、财务披露、公司行动和主数据的一手校验 | 未发现适合默认使用且承诺稳定的统一公共批量 API；自动抓取需另核条款 | 权威校验与人工证据源，不默认抓网页 |
| [EODHD](https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis) | A/美行情、财务、公司行动和日历 | 用户 token、套餐和许可限制；应取 raw OHLC 与公司行动，本地生成统一分析口径 | A/美境外独立备份首选 |
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 美股申报、财务和发行人身份 | 无 key；需明确 User-Agent，并遵守[不超过 10 请求/秒](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits)；回测按 filed/as_of 截断 | 美股 CAN SLIM 财务权威主源 |
| [Alpaca Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api) | 美股行情、公司行动、主数据和日历 | 用户 API key；Basic 实时 IEX 是局部场所，只有 SIP 或经验证的全市场历史量可参与评分 | 美股境外行情备份 |
| [Massive](https://massive.com/docs/rest/stocks/overview) | 美股行情、公司行动和分层财务 | API key、套餐限制及严格市场数据许可 | 仅规划；用户确认适当许可后再启用 |
| [Nasdaq Symbol Directory](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs)、[NYSE 日历](https://www.nyse.com/trade/hours-calendars) | 美股官方主数据和日历校验 | 公共目录偏当前状态；完整历史 Daily List 需要订阅和许可 | 官方校验源 |

## 推荐的后续连接顺序

- A 股行情：Tushare → EODHD；Wind/JQData 仅在用户已有许可时插入。
- 美股行情：通过完整度验收的 Tushare → EODHD → Alpaca SIP。
- A 股财务与公司行动：Tushare → EODHD，再以交易所或巨潮公告核验。
- 美股财务：SEC EDGAR → EODHD；Tushare 美股财务仅作交叉核对。
- AKShare、Massive 和需商业许可的官方历史文件均不默认启用。

## 新增 provider 的验收清单

1. 用官方文档确认授权、限频、市场覆盖和复权语义。
2. 明确证券身份映射、时区、交易日、常规交易时段及成交量单位。
3. 输出完整 SourceArtifact；任何 unknown 不得伪装成通过。
4. 通过 raw/复权、未来数据、局部成交量、缺失量填零和 fallback 回归测试。
5. 相同标准化 DataSet 必须产生与 provider 名称无关的相同策略结果。
6. 只有用户显式选择并提供凭证后，才能启用远程 provider。
7. ProviderFailure 只能包含可公开的简短错误说明；上游异常中的敏感内容仍需在
   adapter 内先清除，Router 的统一脱敏是第二道防线。
