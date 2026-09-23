# Changelog

## 0.2.0-alpha.2-dev.3 - 2026-09-23

- 新增单股自然语言自动取数流程：Skill 将市场、代码、截止日期和基准转换为结构化
  `DataRequest`；命令行继续保持确定性，不自行解析自然语言。
- EODHD 成为首个可运行远程 provider，可获取 A 股和美股的已完成日线与拆股事件，
  并在本地生成 `split_adjusted` OHLC；“最近收盘”只表示截止日期前最后一根已完成
  日线，不是盘中或实时行情。
- EODHD 远程请求仅支持 `COMMON_STOCK`。代码和后缀路由不等于证券主数据核验，
  报告新增 `INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED`；该限制不影响身份元数据明确的
  CSV ADR 研究。
- 新增可复用单股 pipeline 和显式远程配置示例；默认相对强度代理为 CN `510300`
  与 US `VTI`，远程自定义基准仅接受代码内批准的 ETF 代理白名单。主标的和基准必须
  由同一 provider 原子成功，失败时不生成半成品报告。
- 远程 `volume_basis` 与 `zero_volume_policy` 均为 UNKNOWN，完整市场/时段语义
  尚未独立验证，因此所有量能指标与确认完全禁用并保持 UNKNOWN；价格结构候选可继续
  识别，但明确标为“量能未确认”，整体置信度最高为 MEDIUM。
- 修正缺失量能被误当成 FALSE 的 Cycle 语义：UNKNOWN 不再错误压制仅由价格结构支持的
  Wedge Pop/Base n’ Break 候选，明确为 FALSE 的量能反证仍会阻止确认。
- 增强远程安全边界：固定 HTTPS 主机、拒绝重定向、响应大小与超时限制、请求前身份
  校验、重复拆股日期拒绝，以及异常链、URL、token 与本机路径脱敏。
- 继续保持周线结构 UNKNOWN，CAN SLIM 的 C/A/N/S/L/I/M 点时证据 UNKNOWN；
  CSV 作为离线回退不变。当前只有 EODHD 一个可运行远程源，尚无自动冗余，多股自然
  语言筛选也尚未完成。

## 0.2.0-alpha.2-dev.2 - 2026-09-22

- 新增 Tushare A 股未复权日线 adapter scaffold 与可注入 transport；只标准化事实，
  不计算或改变 EMA、ATR、Cycle 和 CAN SLIM 规则。
- 严格限定 `CN + raw + 1d + COMMON_STOCK + 无 benchmark`，要求完整的
  `.SH/.SZ/.BJ` TS code，并校验交易所、日期、OHLCV、重复行和上游错误码。
- 规范化快照不含 token、URL、上游消息或抓取时间；凭证只使用固定环境变量，
  不支持的请求和身份冲突在读取凭证前停止。
- 默认 Tushare transport 明确失败关闭，catalog 继续保持 planned-only。官方文档和
  SDK 仍使用明文 HTTP，且 2026 年新增 `ah_vol` 后未说明 `vol` 是否包含盘后量；
  两项未决前不会发送真实 token，也不会把未知成交量送入策略评分。
- 忽略项目内 `.tmp/` 临时验证目录，降低报告或临时依赖被误提交的风险。
- 原 CSV CLI、离线 provider 配置格式和策略计算保持不变。

## 0.2.0-alpha.2-dev.1 - 2026-09-22

- 新增显式 TOML provider 配置与独立离线校验器；现有 CSV CLI 保持不变且不会联网。
- Provider、市场能力、可信类别和凭证环境变量映射由代码拥有，用户配置不能自称已
  验证或注入任意凭证引用。
- 凭证值不进入配置、参数、摘要或配置指纹；缺失检查只显示固定环境变量名。
- 远程候选仍是 planned-only，启用未实现来源会失败关闭。
- 加强 provider 错误脱敏、错误码校验、公开来源标签检查、SHA-256 快照约束，以及
  诊断字段的名称与类型白名单；URL、路径或凭证形态的 `--source` 会安全停止且不回显。

## 0.2.0-alpha.1 - 2026-09-21

- 新增 provider-neutral 数据契约、注册表和确定性顺序回退；现有 CLI 参数保持兼容。
- 将手工 CSV 包装为首个 `manual_csv` provider，远程来源仍全部默认关闭。
- 报告新增 data_lineage、来源尝试、逐工件快照、价格口径声明和成交量质量字段。
- 新增注册级数据可信类别；只有明确的用户手工输入可使用未验证质量值，远程
  provider 不能借此绕过完整度与价格口径门禁。
- 增加 provider 身份、as-of/known_at、价格口径、基准、局部场所成交量和缺失量
  语义的硬质量门；不等价来源失败关闭或回退，不进入策略引擎。
- Provider 公开错误在写入审计前统一清除 URL、token 与完整本机路径；基准 CSV
  的未来行、尚不可知行、重排及工件血缘分别进入诊断。
- 加入 provider 优先级、fallback 停止条件、全源失败、未来数据和策略不变性测试。
- 新增大陆运营源、境外独立源及交易所/监管机构校验源的规划目录；不保存凭证或授权数据。

## 0.1.1 - 2026-09-21

- 区分 Oliver Kell 公开框架的六个阶段家族与本项目的八个方向化候选，并澄清
  CAN SLIM 是基于 William O'Neil/IBD 的项目级集成。
- 修正失败或混合的 EMA Crossback 被当作正事件证据的问题；缺失信息继续保持 UNKNOWN。
- 允许数据窗口从既有上升趋势中途开始时，以因果性的前一根价格与 EMA 背景识别
  Wedge Drop，不再强制要求窗口内先出现 Wedge Pop。
- 没有正证据支持的候选时，报告明确返回 UNKNOWN，不再强行选择排序第一项。
- 为 JSON 增加阶段家族、方向变体和分类说明，补充对应回归测试并修正文档能力边界。

## 0.1.0 - 2026-09-21

- 建立 Cycle of Price Action 六个来源阶段家族及八个方向化候选的证据规范，
  并加入 CAN SLIM 三值输出。
- 加入无第三方运行依赖的日线 CSV 分析器、结构化 JSON 和中文 Markdown 报告。
- 支持 A 股与美股的带生效日期核心规则快照，并在信息不足或核验过期时 fail closed。
- 加入 A 股 Wedge Pop、美股 Wedge Drop 合成黄金样例。
- 覆盖指标预热、因果滚动窗口、事件账本、无未来数据、价格缩放、隐私路径和 CLI 错误处理测试。

这是实验性研究版本，不提供实盘执行、收益保证或经校准的成功概率。
