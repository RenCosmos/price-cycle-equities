# 美股市场适配

## 范围

首版覆盖美国上市普通股和 ADR。ETF、优先股、OTC 和期权不自动继承普通股规则。

## 时间和交易时段

- 使用 America/New_York，并正确处理夏令时。
- 常规时段通常为 09:30–16:00 ET。
- 盘前、盘后及更长时段因交易所、券商、证券和日期而异，不写死所有股票都支持同一时段。
- 首版 Cycle/CAN SLIM 日线仅使用 regular session；其他 session 分开保存。

## T+1 结算不是 A 股式 T+1 卖出限制

美国多数证券交易自 2024-05-28 起采用 T+1 标准结算，但股票一般可以同日买入后卖出。
实际限制取决于现金或保证金账户、已结算资金、日内保证金制度和券商规则。分别建模：

    settlement_date
    settled_cash
    can_resell_same_day
    margin_regime
    broker_transition_state

日内交易规则正在过渡，不能把固定 PDT 门槛永久硬编码。

## 数量、碎股与价格带

- 整股通常按 1 股递增；碎股是券商服务，不是所有交易所的统一标准订单。
- 碎股最小量、时段、撮合方式和转仓能力属于 broker rule。
- 执行层必须消费 LULD price bands、limit_state、trading_pause、reopening 和各类 halt。
- 只有 OHLC 时不能声称精确重建 LULD 状态或保证成交。

## 做空

做空能力是动态属性。下达意图前检查账户权限、security_shortable、locate、
borrow_available、borrow_rate、hard_to_borrow、Rule 201 状态和券商限制。
首版默认 long_only=true，但保留接口。

## 财务数据

使用 SEC filing 或 acceptance timestamp 作为公开时间基础，不用 fiscal period end
冒充可知日。10-Q、10-K、8-K 和修订文件分别版本化；公司财年未必等于自然年；
GAAP 与 Non-GAAP 分开；ADR 的发行人、上市证券和报告币种分开。

## 规则一手来源

- [SEC：T+1 settlement cycle](https://www.sec.gov/compliance/risk-alerts/shortening-securities-transaction-settlement-cycle)
- [FINRA：new intraday margin requirements](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements)
- [NYSE trading information](https://www.nyse.com/trade/trading-information)
- [LULD Plan](https://www.luldplan.com/plans)
- [FINRA fractional shares](https://www.finra.org/investors/insights/investing-fractional-shares)
- [SEC Regulation SHO FAQ](https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions-8)

实际分析必须按 as_of 检查对应版本和券商规则。
