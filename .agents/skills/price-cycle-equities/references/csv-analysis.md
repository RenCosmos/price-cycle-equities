# 确定性 CSV 分析

此流程用于日线 OHLCV 数据。它会以同一输入、同一参数计算指标、事件账本和八个候选
阶段，再输出 JSON 与 Markdown。检测规则仍属于实验性研究参数，不代表已经验证的交易优势。

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
相对强度只使用股票与基准都存在的完全相同日期，不向前填充。

## 必须明确的元数据

- `market`：`CN` 或 `US`。
- `symbol`：报告展示代码。
- `as_of`：分析截止日。
- `source`：数据来自哪里，例如 `broker-export`。
- `price_basis`：`raw`、`split_adjusted` 或 `total_return`。
- `instrument_id`：最好是稳定的挂牌标识；省略时使用 `MARKET:symbol`，报告会警告。
- `venue`：交易所，例如 `SSE`、`SZSE`、`BSE`、`XNYS` 或 `XNAS`。
- `segment`：A 股板块，例如 `MAIN`、`STAR`、`CHINEXT` 或 `BSE`。
- `security_type`：默认 `COMMON_STOCK`；美股还支持 `ADR` 研究范围。

复权数据可用于连续指标研究，但不能冒充真实可成交价格。报告会对非 raw 口径标记
`ADJUSTED_PRICE_POINT_IN_TIME_RISK`。

## 命令

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

1. 先读 `data_quality.warnings` 与 UNKNOWN 项。
2. `candidate_phases[].score` 是相对证据分，不是上涨概率。
3. CAN SLIM 财务、催化剂、机构持仓和市场环境在仅有 OHLCV 时保持 UNKNOWN。
4. `trade_plan.status` 固定为 `conditional`，`is_order` 固定为 false；该流程不下单。
5. 当前市场规则和可交易性需要另行核验有生效日期的一手来源。
