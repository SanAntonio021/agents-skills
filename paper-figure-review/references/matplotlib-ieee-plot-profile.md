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

单栏独立数据图可先按下面顺序定基线：

1. 先看当前论文或项目是否已有统一字体和版式。
2. 若用户未指定，默认字体可用 `Times New Roman`。
3. 新 IEEE 单栏数据图的统一基线是所有可见文字 `8 pt`；刻度数字、科学计数倍率、负号、上标和 mathtext 也使用同一已批准字体族，不允许静默回退；若目标刊物另有明确要求，在 profile 中记录覆盖原因。
4. 若子图需要后期拼版，先固定真实宽度，再调 `axes_box`、`labelpad` 和 legend 位置；不要靠额外白边把图片“撑到”目标宽度。

示例：如果一张双栏图需要在同一行放 3 张数据子图，并给子图之间留总间距，则可以得到约 `2.30 in` 的单张子图宽度。但这个数值只属于该图组，不是三联图通用标准。

## exact-size 导出

用于精确拼版的独立子图，应保持 Matplotlib `figsize` 对应的真实物理尺寸：

```python
fig.savefig(path, dpi=600, bbox_inches=None, pad_inches=0.0)
```

`bbox_inches="tight"` 会根据可见元素重新裁剪外框。新 IEEE 单栏数据图的 draft 和 formal 都不用它；普通旧图预览只有在不要求精确物理尺寸时才可显式使用。

如果一组并列子图的纵轴标题长度不同，不要只复制同一组 `label_coords` 数值。最终应以可见边界对齐为准，必要时分别微调纵轴标题位置，再检查导出的像素边界或最终拼版效果。

`scripts/ieee_plot_style.py` 中的建议用法：

```python
from ieee_plot_style import (
    export_ieee_single_column,
    propose_figure_color_map,
    repair_single_column_figure,
    use_ieee_single_column_style,
)

use_ieee_single_column_style()
fig, ax = plt.subplots(figsize=(3.5, 2.45))
# Draw data and set all labels, limits, ticks, annotations, and legends first.
proposal = propose_figure_color_map(["method_a", "method_b"])
repair_single_column_figure(fig, [ax], grid_mode="major_xy")
export_ieee_single_column(
    fig,
    "figure_panel",
    output_dir="exports",
    mode="draft",
    profile_path="plot_profile.json",
    grid_mode="major_xy",
)
```

需要双栏或后期拼版的独立面板时，旧 `compute_panel_size()` 和 `save_exact_size_figure()` 仍可显式使用；它们不属于严格单栏 formal 闸门。

在没有项目级网格规范时，只在完整横纵主网格和无网格之间选模式：

| 图形语义 | 模式 | 网格 |
| --- | --- | --- |
| 普通数值坐标图，包括连续量、采集序号和离散工作点 | `major_xy` | 横纵主网格 |
| 类别图、热图、图像或网格会增加干扰的面板 | `none` | 无网格 |

主网格为 `#B8B8B8`、`0.35 pt`、长虚线 `(5, 3)`、`alpha=0.52`。新图默认不画次网格；对数轴只画 decade 主网格并关闭次刻度。只有复现旧图时才使用 `legacy_major_minor_xy`，同时在 `grid` profile 字段记录理由。

上下堆叠的面板若表达同一量纲族但默认刻度字符串长度差异明显，应优先统一显示倍率并把倍率写进各自轴题，例如都写为 `($\times 10^{-3}$)`，刻度只显示 `5, 10, ...` 与 `1, 2, ...`。保留原始数据语义，不用前导零填宽；随后仍按显示坐标对齐刻度右边缘和轴题右边缘。

上下堆叠图的 `hspace` 只作为初始布局参数，不作为最终视觉规范。`repair_single_column_figure()` 会测量上方面板最低可见内容到下一坐标框上边界的显示距离，并收敛到 `4 pt`。profile 同时记录最终 `axes_box_gap_pt` 和 `content_clearance_pt`，这样标签或图高变化后仍能判断是否真正紧凑。

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
| palette_status | `proposed` 或 `confirmed`；formal 必须为 `confirmed` |
| palette_confirmation | `confirmed_by=user` 和 `confirmed_at` |
| axis_range_ticks | `xlim`、`ylim`、major/minor ticks |
| axis_spacing | `labelpad`、tick pad、tick direction |
| stacked_spacing | 上下相邻面板的 `axes_box_gap_pt`、`content_clearance_pt` 和 `4 pt` 目标；不要只记录初始 `hspace` |
| visual_alignment | 并列子图左/右可见边界是否一致，是否单独调整过 `yaxis.set_label_coords(...)` |
| legend | `loc`、`bbox_to_anchor`、字体、列数、handle 参数 |
| grid | `mode`、主网格参数；旧图启用次网格时同时记录理由和次网格参数 |
| export | 格式、dpi、fonttype、是否 exact-size |
| assembly_check | 插入 PPT/PDF 后的有效 dpi 和物理尺寸 |
| visual_review_approval | 用户在最终尺寸预览后确认的 `reasons`、`approved_by=user` 和 `approved_at` |

Matplotlib `>=3.5,<4.0` 是已验证范围。范围外版本允许生成 draft；用户检查最终尺寸预览后，在 `visual_review_approval.reasons` 中同时记录 `final_size_preview` 和 `unvalidated_matplotlib_version`，才允许 formal。

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
