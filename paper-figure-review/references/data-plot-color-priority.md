# IEEE 数据图配色路由

IEEE 没有规定唯一官方 HEX 色表。默认规则是先确定数据角色，再为当前论文提出候选配色；用户确认一次后，全文冻结颜色、marker 和线型。未确认配色只能生成 draft。

## 使用顺序

1. 列出物理变量和视觉角色，不按曲线出现顺序临时分色。
2. 判断数据类型：无序类别、连续强度，或有明确中心值的正负偏差。
3. 调用 `scripts/ieee_plot_style.py` 的 `propose_figure_color_map()` 生成候选。
4. 在最终 `3.5 in` 尺寸下检查灰度、色盲、线型、marker 和图例。
5. 用户确认后调用 `freeze_figure_color_map()` 写入论文 plot profile；后续图不得重新排序相同变量的颜色。

## 路由表

| 数据关系 | 默认候选 | 限制 |
| --- | --- | --- |
| 2--3 个无序类别 | Tol `high-contrast` | 同时使用不同 marker 或线型 |
| 4--7 个无序类别 | Tol `bright` | 六条 BER 曲线仍需 marker/线型冗余，不能只靠颜色 |
| 8--10 个无序类别 | Tol `muted` | 最终单栏尺寸过密时优先拆分子图 |
| 连续强度、热力图、谱图 | `cividis`，备选 `viridis` | 必须有 colorbar；避免 `jet` 和 rainbow |
| 有明确中心值的正负偏差场 | Tol `nightfall` | 必须记录中心值，例如 `0` 或 baseline |
| 单个 Delta 数值、阈值、规范线 | 黑色 `#000000` | 用虚线、点划线或文字说明语义，不占用类别色 |
| 参考或基线 | 深灰 `#404040` | 识别优先级弱于主数据 |
| 置信区间、误差带 | 主线同色，`alpha=0.15--0.25` | 不遮挡数据；必要时增加边界线 |
| 主网格 | `#B8B8B8`、`0.35 pt`、alpha `0.52`、dash `(5, 3)` | 固定背景框架 |
| 次网格 | `#D6D6D6`、`0.35 pt`、alpha `0.40`、dash `(1, 1.65)` | 固定背景框架 |

## API 示例

```python
from ieee_plot_style import propose_figure_color_map, freeze_figure_color_map

proposal = propose_figure_color_map(
    ["channel_a", "channel_b", "channel_c", "channel_d", "channel_e", "channel_f"]
)
# 用户查看最终尺寸 draft 并确认 proposal 后：
freeze_figure_color_map("plot_profile.json", proposal, confirmed_by="user")
```

连续量：

```python
proposal = propose_figure_color_map(["power_density"], data_kind="continuous")
```

有中心值的偏差场：

```python
proposal = propose_figure_color_map(["gain_delta"], data_kind="diverging", center=0.0)
```

## 黑白与可访问性检查

- 同一含义同时使用颜色和线型、marker、纹理或直接标注。
- 不把红绿、蓝绿、黄红作为唯一差异。
- 参考线和网格不能压过主数据。
- 图例命名、颜色、marker 和线型在全文保持一致。
- 候选色不等于已确认配色；正式导出必须在 plot profile 中带 `palette_status=confirmed`、`confirmed_by=user` 和确认时间。

旧代码中的 `FIGURE_PRIORITY_COLORS` 和 `OKABE_ITO` 仅为兼容已有脚本保留。新单栏数据图使用上述 Tol/连续色图路由。
