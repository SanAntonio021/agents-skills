# 计费公式与统一口径

## 1. 先确认 Token 语义

定义：

- `T_in_total`：站点报告的总输入 Token
- `T_in_uncached`：按普通输入价计费的 Token
- `T_cache_read`：缓存读取 Token
- `T_cache_write`：缓存写入 Token
- `T_out`：输出 Token
- `P_in`、`P_cache_read`、`P_cache_write`、`P_out`：每 1M Token 单价

如果协议说明缓存读取是总输入的子集：

```text
T_in_uncached = max(T_in_total - T_cache_read, 0)
```

如果接口已经单独返回未缓存输入，不再相减。缓存写入是否包含在输入中取决于协议，必须查字段定义，不能套用固定假设。

## 2. 按公开单价计算基础成本

```text
B_base =
  T_in_uncached / 1,000,000 * P_in
  + T_cache_read / 1,000,000 * P_cache_read
  + T_cache_write / 1,000,000 * P_cache_write
  + T_out / 1,000,000 * P_out
  + fixed_fee
```

`B_base` 的货币单位由价格表决定，通常是 USD。价格表和模型快照必须带采集时间。

若站点按基础成本再乘倍率：

```text
expected_station_debit = B_base * M_applicable * K_credit
M_applicable = product(被站点公式明确采用的倍率)
```

- `K_credit`：每 1 单位基础货币对应多少站内 credit
- `M_applicable` 可能包含分组、渠道或活动倍率
- 基础价格若已经体现模型价，不要再次乘同义的 `model_ratio`

## 3. 按加权 Token 与 quota 计费

部分 One API/New API 类系统先把 Token 加权，再换算 quota：

```text
T_weighted =
  T_in_uncached
  + T_cache_read * R_cache_read
  + T_cache_write * R_cache_write
  + T_out * R_output

expected_quota = T_weighted * R_model * R_group * Q_scale + fixed_quota
```

`R_*` 和 `Q_scale` 必须来自该站点当时的公式、配置或请求记录。不同部署可能修改默认值；不能因为界面相似就假定公式相同。

## 4. 日志直接返回最终扣费

如果日志字段明确是最终扣费：

```text
observed_station_debit = log_debit
```

此时倍率只用于复核，不再乘到 `log_debit` 上。先确认字段单位：`quota` 可能是内部整数，不一定等于 credit、USD 或 CNY。

如果只能看到 quota：

```text
observed_station_credit = quota / quota_per_credit
```

`quota_per_credit` 必须从站点证据取得；未知就写 `not_evaluable`。

## 5. 充值换算成人民币

单批充值：

```text
R_cny_per_credit = paid_cny / credited_station_credit
real_cny_cost = debited_station_credit * R_cny_per_credit
```

`credited_station_credit` 使用实际到账数，包含明确到账的赠送；支付手续费计入 `paid_cny`。

多批充值可用：

- 加权平均：适合估算一段时间整体成本
- FIFO：适合能证明额度消费顺序的精确核算

必须注明采用哪一种。不能既用充值折扣，又把站内 credit 当人民币再次换算。

## 6. 偏差与有效倍率

```text
delta = observed_station_debit - expected_station_debit
relative_error = delta / expected_station_debit
```

预期值为零时，相对误差写 `not_evaluable`。

若 1 credit 已证明等于 1 单位基础货币：

```text
observed_effective_multiplier = observed_station_debit / B_base
```

单位关系未证明时，改报：

```text
effective_cny_per_base_currency = real_cny_cost / B_base
```

不要把带单位的比值误称为无量纲倍率。

## 7. 余额对账

```text
implied_usage_debit =
  opening_balance
  + sum(non_usage_credits)
  - sum(non_usage_debits)
  - closing_balance

unexplained_gap = implied_usage_debit - sum(request_debits)
```

`non_usage_credits` 包含充值、赠送、退款和人工加款；`non_usage_debits` 包含提现、转出、过期扣除和人工减款。先统一单位和时间边界。

## 8. 多站同负载比较

对站点 `s`：

```text
C_s = expected_debit_s * R_cny_per_credit_s
```

按 `C_s` 排名。只有模型、Token 结构、计费时间点一致时才可比较。倍率更低不一定人民币更便宜，因为基础价、倍率组合、站内单位和充值成本都可能不同。

## 9. 计算示例

已知：

- 总输入 9M，其中缓存读取 7M
- 输出 0.4M
- 输入/缓存/输出单价分别为 5/0.5/30 USD 每 1M
- 分组倍率 0.08，且已证明无其他倍率、1 credit = 1 USD 基础额度

```text
T_in_uncached = 9M - 7M = 2M
B_base = 2 * 5 + 7 * 0.5 + 0.4 * 30 = 25.5 USD
expected_station_debit = 25.5 * 0.08 = 2.04 credit
```

若账本实际减少 50 credit：

```text
delta = 50 - 2.04 = 47.96 credit
observed_effective_multiplier = 50 / 25.5 = 1.960784...
```

这只能证明现有假设无法解释扣费。继续检查时间范围、其他请求、历史倍率、单位和账本调整；不能直接断言站点多扣。

## 10. 精度与容差

- 中间计算保留原始精度，最后显示再四舍五入。
- 容差至少覆盖站点最小记账单位和已知逐请求取整规则。
- 聚合前逐请求取整与聚合后一次取整可能不同，按站点实际记账顺序复现。
