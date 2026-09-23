# Price Cycle Equities

这是一个面向 A 股和美股的 Codex Skill 项目。它把 Oliver Kell 的
**Cycle of Price Action**，与 William O'Neil/IBD 的 CAN SLIM 选股证据作为
项目级集成，并把市场交易规则和可复现研究流程分开管理。

项目正在按“小步可验收”的方式建设。你不需要会 Python、Git 或命令行：
Codex 负责创建、测试和排错，你只需要在关键节点确认策略含义和产品选择。

当前开发版本：**v0.2.0-alpha.2-dev.3**。

## 当前能做什么

- 解释完整的价格行为循环及其证据与反证。
- 区分原作者规则、我们的解释、A/美股适配和待回测参数。
- 基于带日期的数据或图表生成结构化分析与条件式交易计划。
- 明确 A 股与美股在交易规则、数据口径和执行假设上的差异。
- 读取日线 OHLCV CSV，确定性计算 EMA、SMA、ATR、相对强度和价格循环事件。
- 接收“分析茅台最近收盘”等单股自然语言请求：由 AI 提取市场、代码和截止日期，
  再调用结构化远程分析流程。命令行本身不解析自然语言。
- 同时生成便于阅读的 Markdown 报告与便于程序处理的 JSON 报告。
- 通过统一 provider 接口加载数据，记录可信类别、来源尝试、回退路径、逐工件快照和
  成交量质量，并在审计错误前清除 token、URL 与完整本机路径。
- 使用显式 TOML 路由从 EODHD 获取 A 股或美股的已完成日线和拆股事件；配置不保存
  密钥，也不自动发现文件。
- 已加入 Tushare A 股 raw 日线的离线适配器骨架：严格校验代码、日期、OHLCV、
  错误码和无 token 快照；默认 transport 明确阻断网络。

当前版本不接实盘、不自动下单，也不提供收益保证。盘中实时行情、全市场或多股扫描、
点时财务数据和严格点时回测仍在后续里程碑中。确定性分析器当前只消费日线，因此
周线结构保持 UNKNOWN；仅有 OHLCV 时，CAN SLIM 的 C/A/N/S/L/I/M 基本面和市场证据
也保持 UNKNOWN。

EODHD 是当前唯一可运行的远程来源，尚无第二个来源自动接替。该远程路线只接受
`COMMON_STOCK` 请求；代码和后缀映射不等于证券主数据核验，因此报告会给出
`INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED`。这是 EODHD 远程路线的限制，不影响
用户在身份元数据明确时通过 CSV 研究 ADR。

EODHD 返回的成交量字段虽可逐行校验，但 `volume_basis` 与
`zero_volume_policy` 均为 UNKNOWN，完整市场/时段语义也未经独立验证。远程报告
完全禁用量能证据，只识别“价格结构候选，量能未确认”，并把置信度上限设为 MEDIUM。
CSV 仍是可审计的离线回退方式。数据源目录和后续接入顺序见
[数据提供器与来源策略](.agents/skills/price-cycle-equities/references/data-providers.md)。

## 最简单的使用方式

首次使用远程取数时，先在本机账户环境变量中保存
`PRICE_CYCLE_EODHD_TOKEN`；不要把 token 发到聊天、命令参数、TOML 或 GitHub。
重启 Codex 后，可以直接说：

> 使用 $price-cycle-equities，分析 A 股 600519 最近一个已完成交易日。
> 自动取数，列出候选阶段、证据、反证、未知项和失效条件，不要代替我下单。

AI 会把自然语言转换为一只股票的结构化请求。“最近收盘”指截止日期之前最后一根
**已经完成的日线**，不是盘中价格。未指定基准时，A 股默认使用 `510300`，美股默认
使用 `VTI`。远程自定义基准只接受代码内批准的 ETF 代理白名单；任意股票或指数代码
不会被当作基准。这些代理只提供相对强度背景，不等于 CAN SLIM 的 M。

远程配置和首次设置见
[单股自然语言自动取数](.agents/skills/price-cycle-equities/references/remote-analysis.md)。
如果你想亲自运行，PowerShell 可使用一行命令：

```powershell
python .agents/skills/price-cycle-equities/scripts/analyze.py --provider-config examples/provider-config.remote.toml.example --market US --symbol AAPL --as-of 2026-09-23 --price-basis split_adjusted
```

若远程来源不可用，或你希望完全离线复核，可以继续使用 CSV：

如果你有 CSV，可以直接说：

> 使用 $price-cycle-equities 分析这个日线 CSV。市场是 A 股，代码 600000，
> 上交所主板，截止 2026-09-18，数据来自券商导出，价格口径是 raw。请运行确定性分析器，
> 再用中文解释报告里的证据、反证和 UNKNOWN。

你不需要自己敲命令。Codex 会运行分析器并把报告交给你。CSV 至少要有
`date,open,high,low,close,volume` 六列；建议提供 200 个以上交易日。
字段细节见
[CSV 分析说明](.agents/skills/price-cycle-equities/references/csv-analysis.md)，可复制的表头见
[输入模板](examples/input-template.csv)。
从完全零基础开始请看 [小白使用指南](docs/BEGINNER-GUIDE.md)。

如果你想亲自验证，安装 Python 3.11+ 后可在仓库根目录运行：

```powershell
python .agents/skills/price-cycle-equities/scripts/analyze.py --input examples/input-template.csv --market CN --symbol 600000 --as-of 2026-09-18 --source manual-template --price-basis raw --venue SSE --segment MAIN
```

这个模板只有 5 行，所以会诚实地产生预热不足与 UNKNOWN；正式分析建议使用 200 行以上。

验证整个项目只需一条命令：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

还可以单独检查数据源配置。此命令不联网，也不会改变 CSV 分析方式：

```powershell
python .agents/skills/price-cycle-equities/scripts/validate_provider_config.py --config examples/provider-config.remote.toml.example --check-credentials
```

格式和凭证边界见
[Provider 配置说明](.agents/skills/price-cycle-equities/references/provider-config.md)。

完全合成的 A 股与美股黄金样例见 [examples/golden](examples/golden/README.md)。

## 目录

    .agents/skills/price-cycle-equities/
    ├─ SKILL.md
    ├─ agents/openai.yaml
    ├─ scripts/
    │  ├─ analyze.py
    │  ├─ validate_provider_config.py
    │  └─ price_cycle/
    │     ├─ pipeline.py
    │     └─ providers/
    └─ references/
       ├─ strategy-spec.md
       ├─ provenance-policy.md
       ├─ operating-modes.md
       ├─ output-contract.md
       ├─ data-contract.md
       ├─ data-providers.md
       ├─ provider-config.md
       ├─ csv-analysis.md
       ├─ remote-analysis.md
       ├─ market-rules.md
       ├─ sources.md
       └─ markets/
          ├─ cn-equities.md
          ├─ us-equities.md
          └─ adding-market.md

## 建设路线

详细里程碑见 [docs/ROADMAP.md](docs/ROADMAP.md)。策略规范、确定性计算核心、
带生效日期的双市场规则层、A/美股黄金样例、可切换数据层、安全配置，以及
EODHD 单股自动取数均已完成。下一步重点是增加第二个独立来源并验证等价回退，
然后再建设多股编排；在这些完成前不会宣称多源容灾或自然语言多股选股已经可用。

## 重要边界

- 本项目用于学习和研究，不构成投资建议。
- 不内置或转售受版权保护的课程内容，只保存必要的规则摘要和来源链接。
- 任何真实交易都需要用户在券商端自行核验并明确决定。
- 市场规则会变化，涉及当下规则时必须核对有生效日期的一手资料。

## 官方 Skill 规范

本项目采用 OpenAI 当前的 Skill 目录格式。参见
[OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills)。
