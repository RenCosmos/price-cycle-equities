# 单股自然语言自动取数分析

本流程把自然语言编排与确定性分析器分开：

    用户自然语言
      → Skill 提取 market / symbol / as_of / benchmark
      → DataRequest
      → 显式 ProviderRouter
      → 本地确定性 Cycle 引擎
      → JSON + Markdown

CLI 本身不理解中文，也不做模糊公司名搜索。当前每次只分析一个标的；统一 pipeline
保留了未来逐标的批处理的扩展点，但多股筛选器尚未交付。

## 自然语言映射

- `market`：A 股使用 `CN`，美股使用 `US`。
- `symbol`：使用 provider-neutral 代码。A 股示例 `600519`；美股示例 `AAPL`。
  不要添加 `.SHG`、`.SHE` 或 `.US`。
- `as_of`：明确日期使用 `YYYY-MM-DD`。“最近收盘”使用该市场当地当前日期作为请求
  截止日；当地时间 23:00 前保守排除当日，只取前一日或更早的已完成日线。23:00
  之后才允许查询当日，但供应商实际没有该日 bar 时仍以其最后返回的已完成日线为准。
- `benchmark_symbol`：省略时 CN 自动使用 `510300`，US 自动使用 `VTI`。
  它们是相对强度 ETF 代理，不自动等于 CAN SLIM 的 M。

如果用户只给公司名称、同名证券、未知市场或可能歧义的代码，先最小追问市场与代码；
不得猜测。当前远程 EODHD 主标的只接受 `COMMON_STOCK`；ADR 仅可在另行提供 CSV
证据时作为研究范围，不进入当前远程路线。当前不支持 BSE 自动路线。

远程代理基准采用精确白名单，而不是“以某个数字开头”：

- CN：`510050`、`510300`、`510500`、`588000`、`159915`、`159919`；
- US：`VTI`、`SPY`、`QQQ`、`IWM`。

`000300`、`000001` 以及白名单外代码不会被自动当作指数或基准映射。

## 首次本机设置

1. 用户自行向 EODHD 获取适合其用途和许可的数据 token。
2. 在 Windows“编辑账户的环境变量”中新增：

       PRICE_CYCLE_EODHD_TOKEN

   值只保存在本机环境变量中。不要把值发到聊天、TOML、命令行参数、报告或 GitHub。
3. 使用仓库中的
   `examples/provider-config.remote.toml.example`。它只包含 provider 开关和路由，
   不含凭证。
4. 可先离线检查配置：

       python .agents/skills/price-cycle-equities/scripts/validate_provider_config.py --config examples/provider-config.remote.toml.example --check-credentials

   校验器只报告固定环境变量名的 `available/missing`，不会联网或输出值。新设置的
   用户环境变量通常需要重启 Codex/终端后才会进入当前进程。

## 结构化命令

A 股：

    python .agents/skills/price-cycle-equities/scripts/analyze.py \
      --provider-config examples/provider-config.remote.toml.example \
      --market CN \
      --symbol 600519 \
      --as-of 2026-09-23 \
      --price-basis split_adjusted

美股：

    python .agents/skills/price-cycle-equities/scripts/analyze.py \
      --provider-config examples/provider-config.remote.toml.example \
      --market US \
      --symbol AAPL \
      --as-of 2026-09-23 \
      --price-basis split_adjusted

Windows PowerShell 可写成一行。输出仍位于：

    reports/<market>/<symbol>/<as_of>/report.json
    reports/<market>/<symbol>/<as_of>/report.md

`--input` 与 `--provider-config` 互斥。`--source` 和本地 `--benchmark` 文件只属于
CSV 模式。远程模式可用 `--benchmark-symbol` 从上述白名单中覆盖默认代理。

## 当前 EODHD 适配边界

- 固定 HTTPS 主机，拒绝重定向，设置超时与响应大小上限。
- 获取约 550 个自然日范围内的 EOD 与 splits；主标的和基准必须由同一 provider
  原子成功，否则整次请求失败且不生成半成品报告。
- 本地使用不晚于 finalized cutoff 的拆股事件生成 `split_adjusted` OHLC；不会把
  adjusted close 与 raw OHLC 混在一起。
- “最近收盘”按市场当地时间执行保守 cutoff：23:00 前不使用当日日线；这只是防止
  把尚未稳定的日线当成 finalized bar，不等于供应商发布时刻的外部保证。
- A 股主标的按可安全推断的 SSE/SZSE 主板、科创板和创业板前缀映射；BSE 暂不支持。
- 美股使用 EODHD 组合 `.US` 路线，但不能独立证明具体 `XNAS/XNYS` venue；
  远程模式因此拒绝显式 venue，市场规则与执行信息保持 PARTIAL/UNKNOWN。
- 远程主标的只支持 `COMMON_STOCK`。代码和路线推断不是 provider 主数据验证：
  `instrument.identity_assurance=symbol_route_inferred_not_master_verified`，
  warnings 包含 `INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED`，
  missing_capabilities 包含 `provider_verified_instrument_master_identity`。

EODHD 提供的是当前所见历史快照，不是带 vintage 的严格 point-in-time 档案。复权
历史会标记 `ADJUSTED_PRICE_POINT_IN_TIME_RISK`，不能直接用于声称无未来信息的回测。

## 策略证据边界

价格仍是 Cycle 的主证据，成交量只做确认。EODHD 返回行的 volume 字段覆盖可以逐行
校验，但其 A 股常规/盘后以及完整市场语义尚未得到独立证明。因此：

- `volume_completeness=1.0` 只表示每个返回行都有合法 volume 字段；
- `volume_scope=vendor_reported_unverified`；
- `volume_basis=unknown`；
- `zero_volume_policy=unknown`；
- `volume_evidence_eligible=false`；
- 只有因为量能证据被禁用，上述未知语义才允许通过 provider 门禁；
- 所有 volume SMA、volume ratio 和量能确认保持 UNKNOWN；
- 价格结构候选仍可识别，但报告明确写“价格结构候选，量能未确认”，最高置信度
  不超过 MEDIUM。

当前只获取日线，所以周线结构保持 UNKNOWN。OHLCV 不会补齐 CAN SLIM 的点时财务、
催化剂、供需、行业领导力、机构持仓或市场方向证据，C/A/N/S/L/I/M 继续逐项 UNKNOWN。
输出是条件式人工研究计划，不是买卖指令、精确止损、仓位计算或订单。

当前只有 EODHD 一个可运行远程源。Router 已支持顺序回退，但在第二个等价 provider
完成前，不能宣称多源自动容灾；EODHD 失败时必须停止。
