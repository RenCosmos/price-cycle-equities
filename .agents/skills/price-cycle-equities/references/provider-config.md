# Provider 配置与凭证边界

本文件说明 v0.2.0-alpha.2-dev.1 的离线配置骨架。当前分析器仍只使用
`manual_csv`；Tushare 和 EODHD 只是登记在代码目录中的后续候选，尚不能启用，
也不会发起网络请求。

## 配置解决什么问题

配置只回答三件事：

1. 哪些已实现的 provider 可用；
2. A 股或美股的某类数据按什么顺序尝试；
3. 是否明确允许远程 provider 访问网络。

它不包含 Cycle、CAN SLIM、指标阈值或评分参数。更换数据源不能改变策略规则；
provider 的结果仍需通过统一的身份、截止日期、价格口径、成交量和来源血缘门禁。

## 当前 TOML 格式

从 [示例配置](../../../../examples/provider-config.toml.example) 复制即可。当前 schema 为 1：

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

配置文件必须由用户显式指定，不会自动搜索工作目录、用户目录或 `.env`。未知字段、
未知 provider、重复路由、禁用 provider 被路由、市场能力不匹配，以及
`allow_network=false` 时路由远程来源，都会失败关闭。

## 离线检查

在仓库根目录运行：

```powershell
python .agents/skills/price-cycle-equities/scripts/validate_provider_config.py --config examples/provider-config.toml.example
```

可加 `--check-credentials`，仅检查代码规定的环境变量是否存在：

```powershell
python .agents/skills/price-cycle-equities/scripts/validate_provider_config.py --config examples/provider-config.toml.example --check-credentials
```

这两个命令都不会连接网络。当前示例中的远程 provider 处于禁用状态，因此不会要求
凭证。这个校验器与现有 `analyze.py --input ...` 相互独立，旧的 CSV 用法不变。

## 凭证安全

凭证值不得写入 TOML、命令行、报告、日志或 Git 仓库。环境变量名由代码固定，用户
配置不能指定任意变量名：

| Provider | 计划使用的环境变量 | 当前状态 |
|---|---|---|
| Tushare | `PRICE_CYCLE_TUSHARE_TOKEN` | 仅登记，适配器未实现 |
| EODHD | `PRICE_CYCLE_EODHD_TOKEN` | 仅登记，适配器未实现 |

校验器最多显示环境变量的名称和 `available/missing/disabled` 状态，不读取或输出值。
未来 adapter 只应在真正尝试对应 provider 的请求边界解析凭证，并把它包在默认脱敏、
不可直接序列化的 `SecretValue` 中。不要把真实 token 发到聊天中。

## 扩展约束

新增 provider 时，先在代码拥有的 catalog 中声明市场、数据类型、访问模式、可信类别
和固定凭证引用，再实现 adapter 和契约测试。不能让 TOML 自行声明“已验证”“完整
市场成交量”或“支持某市场”，否则配置可能绕过数据质量门。完整验收清单见
[数据提供器与来源策略](data-providers.md)。
