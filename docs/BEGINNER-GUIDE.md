# 零基础使用指南

你不需要学习编程才能使用这个 Skill。最推荐的方式是直接用自然语言指定一只
A 股或美股，让 AI 把市场、代码和截止日期转换成结构化请求，再自动获取日线数据。
CSV 仍然保留，适合远程来源不可用或你希望完全离线复核时使用。

## 第 1 步：只在首次使用时设置远程凭证

当前唯一可运行的远程来源是 EODHD，尚无第二个来源自动接替。你需要自行取得适合
自身用途和许可的数据 token，然后在 Windows“编辑账户的环境变量”中新增：

    PRICE_CYCLE_EODHD_TOKEN

只填写变量值并保存在本机。不要把 token 发到聊天、TOML、命令行、报告或 GitHub。
保存后重启 Codex，让新环境变量进入当前进程。仓库已经提供不含凭证的配置文件
`examples/provider-config.remote.toml.example`。

“最近收盘”指请求截止日期之前最后一根**已经完成的日线**，不是盘中报价。
未指定 benchmark 时，A 股默认使用 `510300`，美股默认使用 `VTI`。远程自定义
benchmark 只接受代码内批准的 ETF 代理白名单；任意股票或指数代码不会被当作基准。
这些代理只提供相对强度背景，并不自动代表 CAN SLIM 的 M。

EODHD 远程路线只接受 `COMMON_STOCK` 请求。代码和后缀路由不能证明证券的主数据
身份，所以报告会提示 `INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED`。这只是远程
EODHD 的限制；身份元数据明确时，CSV 模式仍可用于美股 ADR 研究。

## 第 2 步：用自然语言指定一只股票

A 股示例：

> 使用 $price-cycle-equities，自动取数分析 A 股 600519 最近一个已完成交易日。
> 请用中文解释候选阶段、支持证据、反证、UNKNOWN 和数据警告，不要替我下单。

美股示例：

> 使用 $price-cycle-equities，自动取数分析美股 AAPL，截至 2026-09-23。
> 请使用默认基准，给出条件式失效规则，但不要替我下单。

当前一次只分析一只股票，多股选股和全市场扫描尚未完成。公司名称、市场或代码有
歧义时，AI 应只追问缺少的市场或代码，不能猜测。

### 如果改用离线 CSV

日线 CSV 至少需要六列：

    date,open,high,low,close,volume

建议准备 200 个以上交易日。数据太短会显示预热不足和 UNKNOWN，而不是编造结果。
如果数据是前复权、后复权或总回报口径，不能写成 raw。你可以说：

> 使用 $price-cycle-equities 分析这个日线 CSV。代码 600000，市场 CN，交易所 SSE，
> 板块 MAIN，截止 2026-09-18，数据来自我的券商导出，价格口径 raw。运行确定性
> 分析器后，用中文解释候选阶段、支持证据、反证、UNKNOWN 和数据警告。不要下单。

若不知道 venue 或 segment，直接说不知道；系统会返回 PARTIAL，而不是猜测。

## 第 3 步：先看警告

报告生成后按以下顺序阅读：

1. `数据质量`：是否缺 200 日历史、基准、稳定证券 ID 或市场规则身份。
2. `一句话结论`：有正证据时显示最支持的候选阶段；没有时保持 UNKNOWN，
   不会为了给答案而强选一个阶段。阶段分数不是涨跌概率。
3. `候选阶段证据明细`：同时看支持、反证与未知项。
4. `CAN SLIM`：仅有 OHLCV 时，C/A/N/S/L/I/M 仍保持 UNKNOWN。
5. `周线结构`：当前引擎只消费日线，所以周线确认保持 UNKNOWN。
6. `条件式计划`：当前版本不计算实盘仓位，也不会创建订单。

常见警告：

- `SMA200_WARMUP_INCOMPLETE`：数据少于 200 行。
- `BENCHMARK_NOT_SUPPLIED`：没有相对强度基准。
- `FALLBACK_INSTRUMENT_ID`：只用了市场加代码的临时身份。
- `INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED`：EODHD 的代码/后缀路由不能替代
  证券主数据核验；它只表示远程请求通过了受支持的代码路线。
- `ADJUSTED_PRICE_POINT_IN_TIME_RISK`：复权数据可能含后来才知道的公司行动。
- `MARKET_RULES_PARTIAL/UNKNOWN`：交易所、板块、日期覆盖或规则核验不完整。
- `PRICE_BASIS_NOT_PROVIDER_VERIFIED`：手工 CSV 的复权口径是用户声明，系统无法自动证明。
- `MARKET_DATA_SCOPE_NOT_PROVIDER_VERIFIED`：手工 CSV 无法证明是完整市场覆盖。
- `VOLUME_QUALITY_NOT_PROVIDER_VERIFIED`：远程 `volume_basis` 与
  `zero_volume_policy` 均为 UNKNOWN，完整市场/时段语义尚未独立验证。
- `VOLUME_CONFIRMATION_DISABLED`：量能证据完全禁用并保持 UNKNOWN；价格结构候选
  仍可显示，但必须标为“量能未确认”，置信度最高为 MEDIUM。
- `DATA_PROVIDER_FALLBACK_USED`：首选来源失败后使用了备用来源，应查看 data_lineage。
- `BENCHMARK_LINEAGE_NOT_SUPPLIED`：旧式调用使用了基准数据，但没有提供可核验的
  基准文件名或快照；报告会明确写 UNKNOWN，不会猜测。

## 第 4 步：需要时再补数据

最小补充原则：CSV 模式缺基准就补同日期基准 CSV；远程模式已有默认基准，不要把它
误当作 CAN SLIM 的 M。缺市场身份就补 venue/segment；缺 CAN SLIM 就补带公告时间或
known_at 的点时财务与催化剂数据。不要为了得到 TRUE/FALSE 而把未知值填成 0。

## 第 5 步：本地验证（可选）

只有想亲自运行时才需要安装 Python 3.11+。在仓库根目录执行：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

看到最后一行 `OK` 表示自动检查通过。远程单股流程见
[单股自然语言自动取数](../.agents/skills/price-cycle-equities/references/remote-analysis.md)；
离线字段和退出码见
[CSV 分析说明](../.agents/skills/price-cycle-equities/references/csv-analysis.md)。

如果只想确认远程配置和本机凭证状态，可以运行：

```powershell
python .agents/skills/price-cycle-equities/scripts/validate_provider_config.py --config examples/provider-config.remote.toml.example --check-credentials
```

这条校验命令不联网，也不会显示 token 值。真正运行
`analyze.py --provider-config ...` 时才允许 EODHD 联网。EODHD 是当前唯一可运行的
远程来源；Tushare 仍只是默认断网的解析测试骨架。详细说明见
[Provider 配置与凭证边界](../.agents/skills/price-cycle-equities/references/provider-config.md)。

## 安全边界

- 不要把券商密码、验证码、API 密钥、身份证件或完整账户流水放进仓库。
- GitHub 上传阶段不要在聊天中发送访问令牌；使用浏览器或官方凭据管理器登录。
- 本项目是研究工具，不构成投资建议，不保证收益，也不替你下单。
