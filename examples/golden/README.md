# 合成黄金样例

这里的证券、价格和基准全部为程序生成的虚构数据，不对应真实公司，也不代表策略收益。
它们只用于锁定计算行为：

- `cn_wedge_pop.csv` 在最后一日产生 Wedge Pop；
- `us_wedge_drop.csv` 先产生 Wedge Pop，最后一日产生 Wedge Drop；
- 两个 benchmark 文件提供完全对齐的相对强度日期；
- `expected.json` 保存必须稳定的事件序列、主候选阶段和规则解析状态。

重新生成：

```powershell
python examples/generate_golden_data.py
```

生成器只使用 Python 标准库。日期是用于测试的工作日序列，并非交易所正式日历，
因此不可用来验证节假日或成交可用性。
