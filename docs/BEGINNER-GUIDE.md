# 零基础使用指南

你不需要学习编程才能使用这个 Skill。最推荐的方法是在 Codex 中上传或指定 CSV，
再用自然语言告诉它必要的元数据。

## 第 1 步：准备数据

日线 CSV 至少需要六列：

    date,open,high,low,close,volume

建议准备 200 个以上交易日。数据太短不会报假结果，而会显示预热不足和 UNKNOWN。
如果数据是前复权、后复权或总回报口径，不能写成 raw。

## 第 2 步：告诉 Codex 分析范围

A 股示例：

> 使用 $price-cycle-equities 分析这个日线 CSV。代码 600000，市场 CN，交易所 SSE，
> 板块 MAIN，截止 2026-09-18，数据来自我的券商导出，价格口径 raw。运行确定性
> 分析器后，用中文解释候选阶段、支持证据、反证、UNKNOWN 和数据警告。不要下单。

美股示例：

> 使用 $price-cycle-equities 分析这个日线 CSV。代码 AAPL，市场 US，交易所 XNAS，
> 证券类型 COMMON_STOCK，截止 2026-09-18，数据来自我的券商导出，价格口径
> split_adjusted。若有基准 CSV，请以 Nasdaq-100 为 benchmark。不要下单。

你需要替换代码、日期、数据来源和价格口径。若不知道 venue 或 segment，直接说不知道；
系统会返回 PARTIAL，而不是猜测。

## 第 3 步：先看警告

报告生成后按以下顺序阅读：

1. `数据质量`：是否缺 200 日历史、基准、稳定证券 ID 或市场规则身份。
2. `一句话结论`：只是当前证据最支持的候选阶段，不是涨跌概率。
3. `候选阶段证据明细`：同时看支持、反证与未知项。
4. `CAN SLIM`：仅有 OHLCV 时，财务、催化剂和机构证据会保持 UNKNOWN。
5. `条件式计划`：当前版本不计算实盘仓位，也不会创建订单。

常见警告：

- `SMA200_WARMUP_INCOMPLETE`：数据少于 200 行。
- `BENCHMARK_NOT_SUPPLIED`：没有相对强度基准。
- `FALLBACK_INSTRUMENT_ID`：只用了市场加代码的临时身份。
- `ADJUSTED_PRICE_POINT_IN_TIME_RISK`：复权数据可能含后来才知道的公司行动。
- `MARKET_RULES_PARTIAL/UNKNOWN`：交易所、板块、日期覆盖或规则核验不完整。

## 第 4 步：需要时再补数据

最小补充原则：缺基准就补同日期基准 CSV；缺市场身份就补 venue/segment；缺 CAN SLIM
就补带公告时间或 known_at 的点时财务与催化剂数据。不要为了得到 TRUE/FALSE 而把未知
值填成 0。

## 第 5 步：本地验证（可选）

只有想亲自运行时才需要安装 Python 3.11+。在仓库根目录执行：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

看到最后一行 `OK` 表示自动检查通过。分析命令、字段和退出码见
[CSV 分析说明](../.agents/skills/price-cycle-equities/references/csv-analysis.md)。

## 安全边界

- 不要把券商密码、验证码、API 密钥、身份证件或完整账户流水放进仓库。
- GitHub 上传阶段不要在聊天中发送访问令牌；使用浏览器或官方凭据管理器登录。
- 本项目是研究工具，不构成投资建议，不保证收益，也不替你下单。
