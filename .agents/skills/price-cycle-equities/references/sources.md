# 主要来源

## 来源等级

- A：Oliver Kell 原课件、工作簿或个人网站。
- B：TraderLion 发布的 Oliver Kell 策略文章和交易复盘。
- C：IBD 的 CAN SLIM 官方材料。
- D：本项目的工程解释、市场适配和研究参数；不得冒充 A 至 C。

## 策略资料

- [Cycle of Price Action](https://traderlion.com/technical-analysis/chart-patterns/cycle-of-price-action-by-oliver-kell/)
- [Reversal Extension](https://traderlion.com/technical-analysis/chart-patterns/reversal-extension-how-stocks-bottom/)
- [Wedge Pop](https://traderlion.com/technical-analysis/chart-patterns/wedge-pop-the-money-pattern/)
- [EMA Crossback](https://traderlion.com/technical-analysis/trading-the-ema-crossback/)
- [Base n' Break](https://traderlion.com/technical-analysis/chart-patterns/base-n-break-how-to-catch-breakouts/)
- [Exhaustion Extension](https://traderlion.com/technical-analysis/chart-patterns/exhaustion-extension-sell-into-strength/)
- [Wedge Drop](https://traderlion.com/technical-analysis/chart-patterns/wedge-drop-how-to-sell-short/)
- [Oliver Kell Risk Management and Sell Criteria](https://traderlion.com/wp-content/uploads/sites/2/2021/12/STM-Webinar4-RiskManagementSellCriteria.pdf)
- [Oliver Kell personal site](https://kelltrading.com/)
- [IBD CAN SLIM infographic](https://get.investors.com/wp-content/uploads/2024/08/IBDD-How-to-buy-Stocks-infographic.pdf)

链接用于出处核查；本项目不复制或重新分发课程正文。来源内容发生变化时，更新
strategy-spec 的 last_verified 和版本记录。

Oliver Kell 当前个人网站将框架概括为六个 phase families；TraderLion 的完整循环
资料另行描述上下行 EMA Crossback 与 Base n' Break。公开 Kell/TraderLion 资料支持
成长股、盈利销售增长和相对强度思想，但本项目不据此宣称完整 CAN SLIM 七因子是
Cycle 的原生组成部分。

## 数据提供器资料

### EODHD

- [Quick Start](https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis)
- [Historical End-of-Day Data API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
- [Splits and Dividends API](https://eodhd.com/financial-apis/stock-splits-and-dividends-api)
- [Exchanges, Tickers and Trading Hours API](https://eodhd.com/financial-apis/exchanges-api-list-of-tickers-and-trading-hours)

这些官方页面支持当前 adapter 对 HTTPS 端点、历史 EOD、拆股以及交易所代码格式的
实现依据。它们没有替本项目证明 A 股和美股日线 volume 在所有场所、时段及历史版本上
具有可用于策略量能确认的完整统一语义。因此当前 EODHD 路径仍标为
`vendor_reported_unverified`、`volume_basis=unknown` 与
`zero_volume_policy=unknown`，并设置 `volume_evidence_eligible=false`。官方
文档也不提供本项目所需的逐历史决策时点复权版本或证券主数据完整验证保证，所以报告
保留点时调整风险与身份未验证警告。

### Tushare

- [Tushare HTTP API](https://tushare.pro/document/2?doc_id=130)
- [Tushare A 股日线 daily](https://tushare.pro/document/2?doc_id=27)
- [Tushare 股票代码格式](https://tushare.pro/document/2?doc_id=14)
- [Tushare 权限与更新时间](https://tushare.pro/document/1?doc_id=108)
- [Tushare 官方 Python client](https://github.com/waditu/tushare/blob/master/tushare/pro/client.py)

这些链接用于核验接口契约，不构成启用授权。只观察到 HTTPS 主机可达，不能替代官方
对鉴权 POST、重定向和长期兼容性的书面契约；成交量字段的完整覆盖也必须单独确认。
因此 Tushare 在 v0.2.0-alpha.2-dev.3 仍只有固定响应解析 scaffold，真实联网未实现。
