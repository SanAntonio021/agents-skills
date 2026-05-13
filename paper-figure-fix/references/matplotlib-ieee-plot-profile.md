# Matplotlib IEEE plot profile

这份参考文件用于记录论文数据图的可复现绘图参数。它解决的问题不是“某张图好不好看”，而是以后还能不能用同一套参数重画、微调、拼版和导出。

## 什么时候记录

出现下面情况时，给当前图组建立 plot profile：

- 多个子图需要在 IEEE 单栏或双栏版式中精确拼接。
- 用户反复调整坐标轴题、刻度数字、图例、网格、边距或导出尺寸。
- 输出文件要插入 PowerPoint、Illustrator、LaTeX 或 Word，且最终物理尺寸不能被自动裁剪改变。
- 同一篇论文需要多张数据图保持字体、线宽、颜色和图例风格一致。

## 尺寸计算

不要把某一次的子图尺寸写成通用默认值。先由目标版式反推尺寸：

```python
panel_width = (total_figure_width - total_gutter_width) / ncols
panel_height = panel_width * height_ratio
```

IEEE 常用起点：

- single-column: `3.5 in`
- double-column: `7.16 in`

这些是工作基线，最终仍以目标期刊模板为准。

示例：如果一张双栏图需要在同一行放 3 张数据子图，并给子图之间留总间距，则可以得到约 `2.30 in` 的单张子图宽度。但这个数值只属于该图组，不是三联图通用标准。

## exact-size 导出

用于精确拼版的独立子图，应保持 Matplotlib `figsize` 对应的真实物理尺寸：

```python
fig.savefig(path, dpi=600, bbox_inches=None, pad_inches=0.0)
```

`bbox_inches="tight"` 会根据可见元素重新裁剪外框。它适合单图预览或普通投稿图，但不适合需要保持固定宽度的拼版子图。

`scripts/ieee_plot_style.py` 中的建议用法：

```python
from ieee_plot_style import (
    compute_panel_size,
    apply_axes_box,
    apply_compact_axis_spacing,
    apply_ieee_grid,
    save_exact_size_figure,
)

figsize = compute_panel_size(
    total_width="double",
    ncols=3,
    total_gutter_in=0.26,
    height_ratio=0.74,
)
fig, ax = plt.subplots(figsize=figsize)
apply_axes_box(fig, left=0.16, right=0.97, bottom=0.15, top=0.955)
apply_compact_axis_spacing(ax, xlabel_pad=0.8, ylabel_pad=0.8)
apply_ieee_grid(ax)
save_exact_size_figure(fig, "figure_panel", formats=("pdf", "png"))
```

## plot profile 字段

每个图组至少记录这些字段：

| 字段 | 要记录什么 |
| --- | --- |
| figure_id | 图号，例如 `Fig. 4(c)` |
| purpose | 该图展示什么结果 |
| source_script | 生成图的脚本路径 |
| data_source | 原始数据文件路径 |
| output_files | 输出文件路径 |
| target_layout | 单栏、双栏、几行几列、是否后期拼版 |
| figsize | Matplotlib `figsize`，单位 inch |
| axes_box | `subplots_adjust(left, right, bottom, top)` |
| font | 字体族、坐标轴字体、刻度字体、图例字体 |
| line_marker | 线宽、线型、marker、marker 大小 |
| color_map | 每种数据角色对应颜色 |
| axis_range_ticks | `xlim`、`ylim`、major/minor ticks |
| axis_spacing | `labelpad`、tick pad、tick direction |
| legend | `loc`、`bbox_to_anchor`、字体、列数、handle 参数 |
| grid | major/minor grid 颜色、线宽、透明度和线型 |
| export | 格式、dpi、fonttype、是否 exact-size |
| assembly_check | 插入 PPT/PDF 后的有效 dpi 和物理尺寸 |

## 距离参数怎么看

常用 Matplotlib 参数含义：

- `figsize=(w, h)`：输出画布的物理尺寸。
- `subplots_adjust(left, right, bottom, top)`：坐标轴区域在画布中的相对位置。
- `labelpad`：轴题和刻度/坐标轴之间的距离。
- `tick_params(..., pad=...)`：刻度数字和坐标轴之间的距离。
- `bbox_to_anchor`：图例锚点，相对于坐标轴的位置。
- `pad_inches`：保存图片时额外留白；exact-size 导出时通常设为 `0.0`。

如果需要换算成 inch：

```python
left_margin_in = left * figure_width_in
right_margin_in = (1 - right) * figure_width_in
bottom_margin_in = bottom * figure_height_in
top_margin_in = (1 - top) * figure_height_in
```

## PPT/PDF 检查

组合图在 PowerPoint 或其他软件中再次导出后，要分别检查：

- PPT 页面尺寸是否等于目标双栏或单栏尺寸。
- 嵌入图片的像素数和显示尺寸是否支持目标 dpi。
- PDF 内部是否仍保留足够分辨率；PDF 文件本身合格不代表里面的图片 dpi 合格。
- 如果 PowerPoint 导出的 PDF 把 600 dpi 图降采样到 200 dpi，应改用高分辨率整图导出，或用真正的矢量组图流程。

## 图文同步

多子图顺序、图号或曲线含义变化后，同时检查：

- 图注中的 `(a)`, `(b)`, `(c)` 说明。
- 正文结果段对每个子图的引用。
- 实验方法段对测量条件、拟合区间、数据状态的说明。

不要让旧图号、旧曲线命名或旧结论留在正文里。
