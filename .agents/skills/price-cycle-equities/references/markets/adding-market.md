# 新增市场检查单

新增国家、交易所或资产类型时，不复制 A 股或美股配置。实现并测试以下接口：

1. InstrumentResolver：永久证券身份、代码历史、板块和币种。
2. Calendar：交易日、时区、夏令时、集合竞价、午休和扩展时段。
3. QuantityRules：最小数量、递增单位、零股和碎股。
4. PriceRules：最小价位、静态涨跌幅、动态价格带和停牌。
5. Sellability：买入后的最早可卖时间、已结算资金和账户限制。
6. ShortRules：做空资格、借券、价格测试和保证金。
7. FeesAndTaxes：按日期、方向、账户和交易所计算。
8. FundamentalMapper：会计准则、财年、公告时点和修订。
9. CorporateActions：原始价、调整因子和实际可成交价。
10. BenchmarkResolver：市场与行业基准，不在策略核心硬编码指数。

所有规则必须带 source_url、valid_from、valid_to 和 rule_version。新增市场完成标准是：

- 通过统一适配器契约测试；
- 至少一个正常日和一个边界日黄金样例；
- 无未来数据测试通过；
- 价格等比例缩放后，结构性阶段判断保持合理不变；
- 数据缺失时返回 UNKNOWN 或 fail_closed，而不是沿用其他市场默认值。
