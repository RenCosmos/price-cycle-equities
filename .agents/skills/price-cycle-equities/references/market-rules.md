# 带生效日期的市场规则层

市场规则与 Cycle 阶段判断分开。策略核心只判断价格结构；`rules_at` 根据市场、日期、
交易所、板块和证券类型选择规则快照。规则无法完整解析时返回 `PARTIAL` 或 `UNKNOWN`，
并始终保持 `execution_ready=false`。

## 当前覆盖

规则资料最后核验日为 **2026-09-21**。请求晚于该日期时必须重新核对一手来源，内置
规则会 fail closed，不会自动假定旧规则继续有效。

### A 股

内置快照从 2026-07-06 起覆盖普通人民币股票：

| venue | segment | 买入最低量 | 递增单位 | 标准涨跌幅 |
|---|---|---:|---:|---:|
| SSE | MAIN | 100 股 | 100 股 | 10% |
| SSE | STAR | 200 股 | 1 股 | 20% |
| SZSE | MAIN | 100 股 | 100 股 | 10% |
| SZSE | CHINEXT | 100 股 | 100 股 | 20% |
| BSE | BSE | 100 股 | 1 股 | 30% |

表中是普通股票的标准值，不等于任意日期任意证券的可执行限制。新股上市初期、风险
警示、退市整理、停复牌、临时状态和交易所特别规定都可能改变或取消标准涨跌幅。
仅有日线时无法判断涨跌停队列或保证成交。

普通 A 股买入证券在交收前不得卖出；这不是美股结算周期的同义词。规则层默认
long-only，只有账户资格、实时融券标的、券源、保证金和价格限制均可得时才可评估做空。

一手来源：

- [上交所交易规则（2026 年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)
- [深交所交易规则（2026 年修订）](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)
- [北交所交易规则](https://www.bse.cn/jygl_list/200028217.html)

### 美股

当前覆盖普通股和 ADR 的 NMS 常规研究时段，交易所代码为 `XNYS` 或 `XNAS`：

- America/New_York 时区；常规时段 09:30–16:00 ET。
- 2024-05-28 起，多数券商证券交易的标准结算周期为 T+1。
- T+1 结算不等于禁止同日卖出；现金、保证金、已结算资金和券商控制仍需解析。
- 2026-06-04 起的日内保证金制度带有券商过渡期，必须保存 broker transition state。
- 整股交易以 1 股递增；碎股属于券商服务。
- 价格保护使用实时 NBBO、LULD、停牌和交易场所规则，不能从日线 OHLC 精确重建。

一手来源：

- [SEC：T+1 实施](https://www.sec.gov/newsroom/press-releases/2024-62)
- [SEC：Regulation NMS 常规时段](https://www.sec.gov/divisions/marketreg/nmsfaq610-11.htm)
- [NYSE Trading Information](https://www.nyse.com/trade/trading-information)
- [Nasdaq Market Schedule](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule)
- [LULD Plan](https://www.luldplan.com/plans)
- [FINRA：日内保证金要求](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements)

## 解析状态

- `RESOLVED`：找到与日期、交易所、板块和证券类型匹配的核心规则快照。
- `PARTIAL`：可确定部分共通规则，但 venue、segment 或证券类型不完整。
- `UNKNOWN`：日期不在已覆盖区间、组合不受支持，或请求晚于最后核验日。

即使为 `RESOLVED`，仍必须单独取得实际交易日历、证券当日状态、实时价格带、账户、
券商和成交信息。此层提供审计上下文，不生成订单。

## 扩展方式

新增市场或规则版本时：

1. 添加新的有效期快照，不覆盖历史版本。
2. 保存 `rule_version`、`valid_from`、`valid_to`、来源 URL 与 `verified_at`。
3. 为生效日前一天、生效日、缺字段和不支持组合添加测试。
4. 不完整数据必须返回 UNKNOWN 或 PARTIAL；不得借用另一个市场的默认值。
5. 只有执行所需的所有动态信息可得时，才能在未来单独的执行模块中改变
   `execution_ready`；研究报告本身永不下单。
