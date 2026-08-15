# IEEE 单栏 Matplotlib 数据图执行规范

## 唯一入口

- 规范实现：`scripts/ieee_plot_style.py`
- 调用模板：`assets/ieee_single_column_data_plot.py`
- 旧 `assets/scis_compact_single_column.py` 只做历史回归，不用于新图。

新图不要在项目脚本中重新声明字体、网格、边框、留白或默认色表。需要覆盖目标刊物要求时，把覆盖值和理由写进当前论文的 plot profile。

## 固定机械基线

| 项目 | 取值 |
| --- | --- |
| 画布宽度 | `3.5 in` |
| 可见文字 | `8 pt` 衬线字体；刻度数字、科学计数倍率、上标和 mathtext 也必须同族 |
| 字体解析 | 本机完整 Times New Roman；否则技能内 Liberation Serif 2.1.5 |
| 边框 | 四边黑色 `0.7 pt` |
| 刻度 | 四边向内；major `3.0 pt`，minor `2.2 pt` |
| 主网格 | `#B8B8B8`、`0.35 pt`、alpha `0.52`、dash `(5, 3)` |
| 次网格 | 新图默认关闭；仅旧图复现可显式启用 |
| 可见墨迹外边界 | 四边目标 `3 pt`，允许测量容差 `0.75 pt` |
| 上下堆叠面板间距 | 上方面板最低可见内容到下一坐标框上边界目标 `4 pt`，允许测量容差 `0.75 pt` |
| 导出 | PDF/SVG/PNG，`600 dpi`，`bbox_inches=None`，`pad_inches=0.0` |

图高、坐标范围、刻度密度、图例位置、标注文字和数据语义不跨项目固定。上下堆叠图也不固定某个 `hspace`；机械修复按最终显示坐标收紧内部空白，因此换图高或换标签后仍保留相同的视觉安全距离。

Times New Roman 可用时，普通文字和 mathtext 的正体、斜体、粗体都绑定到 Times New Roman，并关闭 mathtext 静默回退。不能只依赖 `Text.get_fontfamily()`：正式导出还要扫描 PDF 的嵌入字体名和 SVG 的实际 `font-family`；发现 DejaVu、Computer Modern 或其它未批准字体时阻止 formal。

## 网格模式

新图必须在完整笛卡尔主网格和无网格之间显式选择。只画横向或只画纵向主网格会让坐标参考系看起来不完整，因此不进入新图规范：

| `grid_mode` | 适用情况 | 网格结果 |
| --- | --- | --- |
| `major_xy` | 普通数值坐标图，包括连续量、采集序号和离散工作点 | 横纵轴主网格 |
| `none` | 类别图、热图、图像或网格会增加干扰的面板 | 无网格 |
| `legacy_major_minor_xy` | 只读复现已有双层网格图 | 横纵主次网格；必须记录复现理由 |

对数轴只保留 decade 主网格；对数次网格和次刻度默认关闭。需要读出非 decade 数值时，直接标注关键点、阈值或误差，不用密集背景线代替标注。

### 阈值和参考线标注

阈值、规范线和其它不属于数据系列的水平参考线统一采用“贴线标注”规则：

- 线条保持黑色或中性灰，并使用与数据系列不同的虚线/点划线；
- 短标签直接放在线的内侧右端（默认 `x=0.985`），略高于线条并留 `2 pt` 显示间距；
- 标签不作为图例项，图例只列出数据系列；
- 若右端有数据或多个参考线发生冲突，沿线移动到最空的一端，必要时改为线下 `2 pt`，但仍保持贴线；
- 标签必须留在坐标框内，并在最终 `3.5 in` 尺寸下做人工复核。

调用 `scripts/ieee_plot_style.py` 的 `place_reference_line_label()`（或模板中的
`add_reference_line()`）实现该规则，不在项目脚本中重复一套位置常量。

## 标准流程

1. 调用 `use_ieee_single_column_style()` 并创建宽 `3.5 in` 的 figure。
2. 画数据，设置轴题、刻度、图例、阈值、标注和确有语义要求的坐标约束。
3. 调用 `propose_figure_color_map()`；候选状态为 `proposed`。
4. 在 `major_xy` 与 `none` 之间选择 `grid_mode`，调用 `repair_single_column_figure()`。未声明 `locked_limits=True` 时，它可以为贴边 marker 增加安全留量。
5. 调用 `preflight_single_column_figure(mode="draft")`，读取 `errors`、`visual_review_required` 和 `metrics`。
6. 调用 `export_ieee_single_column(mode="draft")`。draft 只能写入 `drafts/`。
7. 用户查看最终尺寸预览，确认当前论文配色；调用 `freeze_figure_color_map()`，并在 profile 中写入视觉确认。
8. 调用 `export_ieee_single_column(mode="formal")`。正式导出 manifest 记录字体文件和 SHA-256、确认时间、修复动作、预检、文件尺寸和文件 SHA-256。

## Formal profile 最小确认字段

```json
{
  "grid": {"mode": "major_xy"},
  "palette_status": "confirmed",
  "figure_color_map": {
    "palette_status": "confirmed",
    "confirmed_by": "user",
    "confirmed_at": "2026-08-14T12:00:00+08:00"
  },
  "visual_review_approval": {
    "approved_by": "user",
    "approved_at": "2026-08-14T12:05:00+08:00",
    "reasons": ["final_size_preview"]
  }
}
```

Matplotlib 不在 `>=3.5,<4.0` 时，draft 继续生成；formal 的 `reasons` 还必须包含 `unvalidated_matplotlib_version`。

## 自动修复与阻止边界

自动修复：字体、mathtext 无回退字体映射、8 pt 字号、3.5 in 宽度、四边框、向内刻度、已选语义网格、纵轴刻度和标题显示坐标对齐、面板标签间距、上下堆叠面板的 `4 pt` 内容安全间距、3 pt 可见边界，以及未锁定坐标的 marker 留量。

阻止 formal：字体文件不完整或 SHA-256 不符、mathtext 允许回退、PDF/SVG 出现未批准字体、明确锁定坐标导致数据/marker 越界、无法安全消除的文字碰撞或裁切、可见边界无法达到容差、未确认配色，或缺少必要视觉确认。

图例和数据可能重叠时保留 `legend_data_overlap` 视觉复核原因，不用像素级基线比较替代人工判断。
