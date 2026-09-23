# Provider 配置与凭证边界

本文件说明 v0.2.0-alpha.2-dev.3 的数据源配置。分析器支持两条互斥路径：
`manual_csv` 离线导入，或用户显式指定配置后通过 EODHD 联网取日线。Tushare 只有
固定响应测试覆盖的解析 scaffold，真实 transport 和 catalog 路由仍然阻断。

当前只有 **一个** 可运行的远程来源（EODHD），因此配置系统虽然已支持按优先级路由，
但还没有真实的远程故障切换能力。不能把单源重试称为多源备份。

## 配置解决什么问题

配置只回答三件事：

1. 哪些已实现的 provider 可用；
2. A 股或美股的某类数据按什么顺序尝试；
3. 是否明确允许远程 provider 访问网络。

它不包含 Cycle、CAN SLIM、指标阈值或评分参数。更换数据源不能改变策略规则；
provider 的结果仍需通过统一的身份、截止日期、价格口径、成交量和来源血缘门禁。

## 当前 TOML 格式

离线 CSV 可从[离线示例配置](../../../../examples/provider-config.toml.example)复制。
联网单股分析使用[远程示例配置](../../../../examples/provider-config.remote.toml.example)。
当前 schema 为 1：

```toml
schema_version = 1
allow_network = false

[providers.manual_csv]
enabled = true

[providers.tushare]
enabled = false

[providers.eodhd]
enabled = false

[routes.daily_bars]
CN = ["manual_csv"]
US = ["manual_csv"]
```

远程示例的关键变化是：

```toml
schema_version = 1
allow_network = true

[providers.manual_csv]
enabled = false

[providers.tushare]
enabled = false

[providers.eodhd]
enabled = true

[routes.daily_bars]
CN = ["eodhd"]
US = ["eodhd"]
```

配置文件必须由用户显式指定，不会自动搜索工作目录、用户目录或 `.env`。未知字段、
未知 provider、重复路由、禁用 provider 被路由、市场能力不匹配，以及
`allow_network=false` 时路由远程来源，都会失败关闭。远程示例只允许分析器调用
已实现的 EODHD adapter，不会在文件中保存 token，也不会启用 Tushare。

## 离线检查

在仓库根目录运行：

```powershell
python .agents/skills/price-cycle-equities/scripts/validate_provider_config.py --config examples/provider-config.toml.example
```

可加 `--check-credentials`，仅检查代码规定的环境变量是否存在：

```powershell
python .agents/skills/price-cycle-equities/scripts/validate_provider_config.py --config examples/provider-config.remote.toml.example --check-credentials
```

这两个校验命令都不会连接网络；`--check-credentials` 只报告固定环境变量是
`available`、`missing` 还是 `disabled`。与之不同，
`analyze.py --provider-config examples/provider-config.remote.toml.example ...`
会实际联网，因此必须显式设置 `allow_network=true` 并在本机提供 EODHD token。
旧的 `analyze.py --input ...` CSV 用法不变；`--input` 与 `--provider-config`
必须二选一。

## 凭证安全

凭证值不得写入 TOML、命令行、报告、日志或 Git 仓库。环境变量名由代码固定，用户
配置不能指定任意变量名：

| Provider | 固定环境变量 | 当前状态 |
|---|---|---|
| Tushare | `PRICE_CYCLE_TUSHARE_TOKEN` | 离线 adapter scaffold；真实联网未启用 |
| EODHD | `PRICE_CYCLE_EODHD_TOKEN` | 已实现 A/美 COMMON_STOCK 日线远程适配器；不支持 ADR 远程请求 |

校验器最多显示环境变量的名称和 `available/missing/disabled` 状态，不读取或输出值。
Adapter 只应在市场、口径、标的身份和基准请求全部通过后解析凭证，并把它包在默认
脱敏、不可直接序列化的 `SecretValue` 中。EODHD token 只在构造 HTTPS 请求的边界
进入请求，不能进入配置、快照、错误、报告或 Git。当前 Tushare 默认 transport
即使本机已有该环境变量也不会联网。不要把真实 token 发到聊天中。

EODHD 当前只提供拆股调整日线研究路径，并把供应商成交量标为
`vendor_reported_unverified`，同时声明 `volume_basis=unknown` 与
`zero_volume_policy=unknown`。只有在 `volume_evidence_eligible=false`、全部量能
证据关闭时，这组未知语义才允许通过；字段覆盖完整不代表量能语义完整。该限制由代码
固定，不能通过 TOML 改写。

远程代码路由只做推断，不等于 provider 主数据验证。报告的
`instrument.identity_assurance` 为 `symbol_route_inferred_not_master_verified`，
并输出 `INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED` 警告与
`provider_verified_instrument_master_identity` 能力缺口。远程代理基准仅接受 CN
`510050/510300/510500/588000/159915/159919` 或 US `VTI/SPY/QQQ/IWM`；默认仍为
`510300` 与 `VTI`。“最近收盘”按市场当地时间保守处理：23:00 前排除当日日线。

## 扩展约束

新增 provider 时，先在代码拥有的 catalog 中声明市场、数据类型、访问模式、可信类别
和固定凭证引用，再实现 adapter 和契约测试。不能让 TOML 自行声明“已验证”“完整
市场成交量”或“支持某市场”，否则配置可能绕过数据质量门。完整验收清单见
[数据提供器与来源策略](data-providers.md)。
