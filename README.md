# Price Cycle Equities

这是一个面向 A 股和美股的 Codex Skill 项目。它把 Oliver Kell 的
**Cycle of Price Action**，与 William O'Neil/IBD 的 CAN SLIM 选股证据作为
项目级集成，并把市场交易规则和可复现研究流程分开管理。

项目正在按“小步可验收”的方式建设。你不需要会 Python、Git 或命令行：
Codex 负责创建、测试和排错，你只需要在关键节点确认策略含义和产品选择。

当前开发版本：**v0.2.0-alpha.1**。

## 当前能做什么

- 解释完整的价格行为循环及其证据与反证。
- 区分原作者规则、我们的解释、A/美股适配和待回测参数。
- 基于带日期的数据或图表生成结构化分析与条件式交易计划。
- 明确 A 股与美股在交易规则、数据口径和执行假设上的差异。
- 读取日线 OHLCV CSV，确定性计算 EMA、SMA、ATR、相对强度和价格循环事件。
- 同时生成便于阅读的 Markdown 报告与便于程序处理的 JSON 报告。
- 通过统一 provider 接口加载数据，记录可信类别、来源尝试、回退路径、逐工件快照和
  成交量质量，并在审计错误前清除 token、URL 与完整本机路径。

当前版本不接实盘、不自动下单，也不提供收益保证。实时行情、全市场扫描、
点时财务数据和回测仍在后续里程碑中。

当前确定性分析器只接受日线 CSV，尚未生成或消费周线数据；周线在策略规范中
保留为后续多周期能力。

当前远程 provider 尚未启用：原 CSV 命令无需改变，也不会自行连接网站。数据源
目录和后续接入顺序见
[数据提供器与来源策略](.agents/skills/price-cycle-equities/references/data-providers.md)。

## 最简单的使用方式

在本仓库中对 Codex 说：

> 使用 $price-cycle-equities，按 2026-09-18 收盘后的可得信息分析这只股票。
> 请列出候选阶段、证据、反证、未知项和失效条件，不要代替我下单。

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

完全合成的 A 股与美股黄金样例见 [examples/golden](examples/golden/README.md)。

## 目录

    .agents/skills/price-cycle-equities/
    ├─ SKILL.md
    ├─ agents/openai.yaml
    ├─ scripts/
    │  ├─ analyze.py
    │  └─ price_cycle/
    │     └─ providers/
    └─ references/
       ├─ strategy-spec.md
       ├─ provenance-policy.md
       ├─ operating-modes.md
       ├─ output-contract.md
       ├─ data-contract.md
       ├─ data-providers.md
       ├─ csv-analysis.md
       ├─ market-rules.md
       ├─ sources.md
       └─ markets/
          ├─ cn-equities.md
          ├─ us-equities.md
          └─ adding-market.md

## 建设路线

详细里程碑见 [docs/ROADMAP.md](docs/ROADMAP.md)。策略规范、确定性计算核心、
带生效日期的双市场规则层、A/美股黄金样例，以及可切换数据层骨架均已完成；
下一小步将实现首个需要用户显式配置的远程 provider。

## 重要边界

- 本项目用于学习和研究，不构成投资建议。
- 不内置或转售受版权保护的课程内容，只保存必要的规则摘要和来源链接。
- 任何真实交易都需要用户在券商端自行核验并明确决定。
- 市场规则会变化，涉及当下规则时必须核对有生效日期的一手资料。

## 官方 Skill 规范

本项目采用 OpenAI 当前的 Skill 目录格式。参见
[OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills)。
