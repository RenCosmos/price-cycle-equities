# 确定性 CSV 分析

此流程用于用户已有的日线 OHLCV 文件。它会以同一输入、同一参数计算指标、事件账本，
以及由六个来源阶段家族展开的八个方向化候选，再输出 JSON 与 Markdown。检测规则仍
属于实验性研究参数，不代表已经验证的交易优势。

v0.2.0-alpha.2-dev.3 中，CSV 不是唯一数据入口。命令支持两条互斥路径：

- `--input`：离线 CSV，通过 `manual_csv` provider 和统一 Router 加载；
- `--provider-config`：显式配置远程 provider，当前可运行的是 EODHD。

两者都进入同一分析 pipeline，但不能同时使用。远程单股流程见
[单股自然语言自动取数分析](remote-analysis.md)。

## 输入字段

CSV 必须采用 UTF-8，并包含：

    date,open,high,low,close,volume

- `date` 使用 `YYYY-MM-DD`。
- OHLC 必须为正数且满足 high/low 约束；volume 不得为负。
- 可选列 `known_at` 必须带时区，例如 `2026-09-18T16:30:00+08:00`。
- 行可以正序或倒序；倒序会自动排序并在报告中警告。
- 建议至少提供 200 个交易日；不足时 SMA200 等字段会保持 UNKNOWN，并产生预热警告。
- 输入中的 `as_of` 之后数据和当时尚不可知的数据会被排除并计数。

若提供基准指数 CSV，格式相同；`--benchmark` 与 `--benchmark-symbol` 必须同时出现。
相对强度只使用股票与基准都存在的完全相同日期，不向前填充。远程模式不使用
`--benchmark` 文件；可用 `--benchmark-symbol` 覆盖默认远程代理基准。

## 必须明确的元数据

- `market`：`CN` 或 `US`。
- `symbol`：报告展示代码。
- `as_of`：分析截止日。
- `source`：仅 CSV 模式必填，例如 `broker-export`。它必须是简短公开标签；不要填写
  URL、本机路径、token 或认证头，否则分析会安全停止，避免把敏感内容写进报告。
- `price_basis`：`raw`、`split_adjusted` 或 `total_return`。当前 EODHD 远程
  adapter 只接受 `split_adjusted`。
- `instrument_id`：最好是稳定的挂牌标识；省略时使用 `MARKET:symbol`，报告会警告。
- `venue`：交易所，例如 `SSE`、`SZSE`、`BSE`、`XNYS` 或 `XNAS`。
- `segment`：A 股板块，例如 `MAIN`、`STAR`、`CHINEXT` 或 `BSE`。
- `security_type`：默认 `COMMON_STOCK`；CSV 可声明美股 `ADR` 研究范围，但
  当前 EODHD 远程路线只接受 `COMMON_STOCK`，且不会把声明当成证券主数据验证。

复权数据可用于连续指标研究，但不能冒充真实可成交价格。报告会对非 raw 口径标记
`ADJUSTED_PRICE_POINT_IN_TIME_RISK`。供应商当前返回的复权历史若没有逐时点版本，
也不能直接作为严格 point-in-time 回测数据。

手工 CSV 无法自动证明文件在经济意义上确实是 raw、复权或完整成交量。因此报告会
把价格口径与行情/成交量覆盖标为用户声明且未由 provider 验证；这不是自动识别结果。

## CSV 命令

从仓库根目录执行：

    python .agents/skills/price-cycle-equities/scripts/analyze.py \
      --input examples/input-template.csv \
      --market CN \
      --symbol 600000 \
      --as-of 2026-09-18 \
      --source broker-export \
      --price-basis raw \
      --venue SSE \
      --segment MAIN

Windows PowerShell 可写成一行。输出默认位于：

    reports/<market>/<symbol>/<as_of>/report.json
    reports/<market>/<symbol>/<as_of>/report.md

已有同路径报告时默认拒绝覆盖；只有明确使用 `--overwrite` 才替换。

退出码：`0` 成功，`2` 参数错误，`3` 数据错误，`4` 分析或写入错误。默认不打印
Python traceback；开发排错时可添加 `--debug`。

## 解释输出

1. 先读 `data_quality.warnings`、`data_quality.evidence_mode` 和 UNKNOWN 项。
2. `candidate_phases[].score` 是相对证据分，不是上涨概率。
3. 远程 EODHD 路径的成交量语义尚未验证，因此量能指标/证据为 UNKNOWN；价格结构
   事件若出现，只是 `price_structure_only_volume_unconfirmed` 候选。
4. 当前引擎只分析日线，`market_context.weekly_structure.status` 固定为 UNKNOWN。
5. CAN SLIM 财务、催化剂、机构持仓和市场环境不会从 OHLCV 推断，七因子保持 UNKNOWN。
6. `trade_plan.status` 固定为 `conditional`，`is_order` 固定为 false；该流程不下单。
7. 当前市场规则和可交易性需要另行核验有生效日期的一手来源。
