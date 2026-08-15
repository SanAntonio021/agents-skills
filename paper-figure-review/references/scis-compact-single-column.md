# 旧 SCIS 派生 profile（只读回归）

## 使用范围

这是 GLOBECOM 图 2--4 形成过程中的历史 profile，只用于解释既有图件和只读回归。新 IEEE 单栏数据图统一走 `scripts/ieee_plot_style.py`、`assets/ieee_single_column_data_plot.py` 和 `references/matplotlib-ieee-plot-profile.md`，不再从本文件取默认颜色或实现。

历史模板文件：`assets/scis_compact_single_column.py`。不要复制到新项目；它保留是为了核对旧图，不是默认入口。

## 固定基线

| 项目 | 取值 |
| --- | --- |
| 目标宽度 | `3.50 in` IEEE 单栏 |
| 栅格预览 | `600 dpi`，实际绘制 canvas 可保持 `150 dpi` |
| 字体 | 旧图使用 Times New Roman，基础字号 `8 pt`，刻度/图例约 `7 pt` |
| 初始轴区 | `left=0.115`, `right=0.985`, `bottom=0.120`, `top=0.960` |
| 外框与主刻度 | 四边黑色 `0.7 pt`，四边向内 `3.0 pt` |
| 次刻度 | 黑色 `0.6 pt`，向内 `2.2 pt` |
| 主网格 | `#B8B8B8`，`0.35 pt`，`(5, 3)` 长虚线，`alpha=0.52` |
| 次网格 | `#D6D6D6`，`0.35 pt`，点线，`alpha=0.40` |
| 通道 1 | 旧 GLOBECOM 映射：`#009E73`，圆点 |
| 通道 2 | 旧 GLOBECOM 映射：`#CC79A7`，方点 |
| 阈值、差值、参考线 | 黑色；由线型、marker 或标注补充语义 |
| 纵轴刻度 | 右边缘在显示坐标中对齐，距左 spine `1.5 pt` |
| 纵轴标题 | 自动置于最宽可见刻度块左 `1.2 pt` |
| 单面板外白边 | 通过 `fit_outer_label_margins(..., target_points=3.0)` 使纵轴标题左侧和横轴标题下方各为 `3 pt` |
| 导出 | `bbox_inches=None`，`pad_inches=0.0`，PDF/SVG/PNG 按需要输出 |

## 历史调用顺序

1. 先调用 `use_compact_single_column_style()`，按目标高度建立 `fig, ax`。
2. 用 `apply_compact_single_column_layout()` 设置轴区；只有图例或多行横轴文字确实放不下时才改 `bottom` 或 `top`。
3. 绘制数据，再设置数据范围、major/minor ticks、轴题、图例和技术标注。
4. 对每个轴调用 `apply_compact_single_column_axes()` 与 `apply_compact_grid()`；对纵轴标题调用 `prepare_compact_ylabel()`。
5. 所有可见元素确定后，对整组轴调用 `align_y_tick_labels()`，再调用 `place_ylabels_clear_of_ticks()`。单面板图再调用 `fit_outer_label_margins(fig, ax, target_points=3.0)`，随后重复前两次对齐，令左、下外白边同时收紧而不裁切标题。
6. 用 `save_exact_size_figure()` 输出，并在项目内记录实际的 `figsize`、`axes_box`、色彩角色、对齐间距、网格、源数据和输出文件。

## 不应固定的内容

- 不固定图高、横纵坐标范围、刻度密度、图例位置、子图编号和数据标签。
- 不因为模板的两个通道色就给无关变量强行分配 CH1/CH2 语义。
- 不把这里的 CH1/CH2 色值作为未来论文默认色表。
- 不把阈值、拟合线、置信区间或分组分隔线误画成主数据。
- 不用额外白边达到 `3.50 in` 宽度；保持真实画布尺寸并压缩可见边界。
