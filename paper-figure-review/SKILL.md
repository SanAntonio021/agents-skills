---
name: paper-figure-review
description: 审查、规范化和重画 IEEE 论文图件。Use when 用户要审查已画好的图、判断图是否符合 IEEE 投稿风格、把数据图重画成论文图、处理太赫兹/通信系统论文里的曲线图、频谱图、BER/SNR/EVM/带宽/链路预算图、Google Earth/卫星地图链路图、系统框图、机制图、实验平台图或多子图；也用于多子图精确尺寸导出、记录 plot profile、核对图数据溯源和图-表-正文数值一致性、检查 PPT/PDF 有效 dpi；优先用原始数据和可编辑源文件，按 IEEE 单栏/双栏尺寸、字体、线宽、分辨率和黑白可读性输出可投稿版本。
---

# 论文图件规范

## 作用

这份 skill 负责把论文图从“能看”推进到“适合 IEEE 论文投稿”：

- 审查已画好的图是否符合 IEEE 论文风格
- 有原始数据时，按 IEEE 风格重画数据图
- 对机制图、系统框图和实验平台图做技术表达与版式规范化
- 输出可投稿图件、可编辑源文件和简短审查意见

## 先分图类型

开始前先判断图属于哪一类，再选处理方式：

1. `data_plot`：曲线图、柱状图、散点图、热力图、频谱图、BER/SNR/EVM/带宽/功率图。
2. `system_diagram`：太赫兹通信系统框图、链路框图、发射接收链路、实验平台结构图。
3. `mechanism_diagram`：原理机制图、模块工作机理、信号处理流程图。
4. `photo_or_screenshot`：实物照片、仪器截图、仿真软件截图、版图截图。
5. `multi_panel`：由多个子图拼成的 Fig. 1(a)-(d)。

数据图优先重画；系统图和机制图优先改成可编辑矢量源；照片和截图不伪造细节，只做裁剪、标注、分辨率和说明规范。

## 核心规则

- 不凭截图反推精确数据。没有原始数据时，只能做风格审查或近似复刻，并明确标注 `approximate_redraw`。
- 不为了“好看”改变技术含义。系统框图的信号流、频段、单位、模块名称、测量点和实验条件必须先对。
- 不使用自由发挥式 AI 生成替代技术图。机制图、系统图优先用 PowerPoint、draw.io、SVG、TikZ、Mermaid 或 Matplotlib 等可编辑源。
- 不把 PPT 风格当论文风格。避免大面积渐变、阴影、厚边框、装饰图标、花哨背景和过饱和配色。
- 只要进入投稿或定稿阶段，就用 IEEE Author Center 或目标期刊/会议最新版要求复核格式；本 skill 的默认值是工作基线，不替代目标刊物最终说明。

## 可复现图源版本保护

- 数据图：用 Git 跟踪 Python/MATLAB 绘图脚本、必要源数据和 plot profile。实际修改前沿用 [../writing-router/references/document-version-protection.md](../writing-router/references/document-version-protection.md) 的项目根目录、baseline、无关文件隔离、验证后 commit、里程碑 tag 和不 push 规则；这里的目标文件清单改为可复现图源。
- 普通中间 PDF/PNG 不逐轮提交。只长期保留用户选中的 Image 2 参考图和最终投稿导出件。
- 手工 PowerPoint 图不进入这套 Git 提交流程；PPTX 按正常保存和现有备份方式处理。
- 最终 PDF/PNG 仍由本 skill 的投稿导出流程生成。

## PPTX 原生图件与照片替换

- 以 PPTX 内的高分辨率嵌入媒体替换照片时，必须先应用 PowerPoint 的裁剪元数据：读取并执行 `a:srcRect`，或等价的 `crop_left`、`crop_top`、`crop_right`、`crop_bottom`。
- 不得把完整原始照片直接嵌入原先裁剪后的 PDF 照片框；这会改变作者已确认的构图。
- 以作者导出的原生 PDF 作为视觉基线，只替换照片层，保留原生矢量文字、透明度和连接线。

## IEEE 默认基线

默认按 IEEE 工程类论文图件处理：

- 单栏宽度：`3.5 in` / `89 mm`
- 双栏宽度：`7.16 in` / `182 mm`
- 图中文字：最终尺寸下优先 `8-10 pt`，拥挤图不要低于可读底线
- 字体：先问用户或看现有项目是否已有统一字体；若用户未指定，默认 `Times New Roman`
- 线图：优先 PDF/EPS 矢量；如需栅格，线稿按 `600 dpi` 起
- 照片或灰度图：通常按 `300 dpi` 起
- 彩色：线上可用 RGB，但必须保证黑白打印和色盲场景仍能区分
- 子图编号：IEEE 论文中通常用 `(a)`, `(b)`, `(c)`，并和正文、图注一致
- JPEG 不作为论文图默认格式；作者照片例外

### 小型数据图网格推荐基线

对没有项目级网格规范的小型 IEEE 数据图，网格必须作为完整笛卡尔参考系出现或整体关闭，不能只画一个方向：

| 图形语义 | `grid_mode` | 可见网格 |
| --- | --- | --- |
| 普通数值坐标图，包括连续量、采集序号和离散工作点 | `major_xy` | 横纵轴主网格 |
| 类别图、热图、图像或网格会增加干扰的面板 | `none` | 无笛卡尔网格 |

主网格统一为 `#B8B8B8`、`0.35 pt`、长虚线 `(5, 3)`、`alpha=0.52`。次网格不进入新单栏图的默认路由；对数轴只画 decade 主网格，次网格和次刻度默认关闭。旧图必须复现双层网格时才显式使用 `legacy_major_minor_xy`，并在 plot profile 中记录理由。

更细的检查项见 `references/ieee-figure-review-checklist.md`。

## 单栏数据图基线

未来 IEEE 单栏 Matplotlib 数据图只以 `scripts/ieee_plot_style.py` 为规范实现。先把
`assets/ieee_single_column_data_plot.py` 复制到项目绘图目录作为调用骨架，不在项目里再复制一套
字体、边框、网格或留白常量。

1. 调用 `use_ieee_single_column_style()`：画布宽 `3.5 in`，所有可见文字 `8 pt` 衬线字体，四边 `0.7 pt` 黑框，四边向内刻度。字体统一范围包括正文标签、图例、刻度数字、负号、科学计数倍率、上标和 Matplotlib mathtext；不能只检查外层 `Text` 对象后允许公式字形回退到 DejaVu 或 Computer Modern。
2. Times New Roman 优先从本机查找并进程级注册；四个字形文件不完整时使用技能内固定 SHA-256 的 Liberation Serif 2.1.5，不修改系统字体目录，不静默回退。
3. 数据、标签、图例和坐标范围设置完成后，在完整横纵主网格 `major_xy` 与无网格 `none` 之间显式选择，再调用 `repair_single_column_figure()`；它修字体、框线、刻度、语义网格、纵轴显示坐标对齐、面板标签间距、上下堆叠面板的 `4 pt` 内容安全间距、3 pt 可见墨迹留白和未锁定坐标的 marker 留量。
4. 调用 `preflight_single_column_figure()` 检查字体完整性、mathtext 无回退配置、尺寸、所选网格模式、文字碰撞、裁切、越界 marker、锁定坐标冲突和最终视觉确认状态；导出后继续检查 PDF/SVG 实际字体名。复杂图无法在不改变数据语义的前提下修复时，保留结构化冲突报告。
5. `export_ieee_single_column(mode="draft")` 只写入 `drafts/`；未确认配色、未完成人工复核或未验证 Matplotlib 版本都可以先出 draft。
6. `mode="formal"` 只在预检通过、配色已由用户确认并冻结、字体已解析，且 plot profile 记录了最终尺寸视觉确认原因和时间后写入正式目录。PDF/SVG/PNG 始终使用 `bbox_inches=None`、`pad_inches=0.0`，并在 manifest 中记录物理尺寸和 SHA-256。

执行细节见 `references/ieee-single-column-data-plot.md`；需要记录可复现参数时，继续看 `references/matplotlib-ieee-plot-profile.md`。

### 旧 SCIS profile

`assets/scis_compact_single_column.py` 和 `references/scis-compact-single-column.md` 只用于解释既有图件和只读回归，不再进入新图默认路由。不要把其中固定的 CH1/CH2 绿色、紫色映射带到下一篇论文。

## 审查流程

1. 明确目标。
   记录目标期刊/会议、图编号、单栏还是双栏、是否最终投稿、是否有原始数据或可编辑源文件。
2. 查看图件。
   对图片路径使用视觉读取；对 PDF、PPTX、SVG、draw.io、Python、MATLAB、Origin 等源文件优先读取源文件。
3. 缩到最终尺寸判断可读性。
   单栏图按 3.5 in 宽检查，双栏图按 7.16 in 宽检查。重点看坐标轴、图例、子图编号、单位和关键标注。
4. 按三档给结论。
   使用 `必须改`、`建议改`、`可保留`，不要只说“挺好”或“需要优化”。
5. 决定是否重画。
   有原始数据且问题集中在绘图风格时，直接重画；没有数据时只改版式或要求补数据。
6. 输出文件。
   批量处理时在当前工作区生成 `figure_review.md` 和 `figure_index.md`；单图任务可直接在回复中给审查意见。

## 数据溯源与图-表-文一致性

数据图审查不只看风格，还要核验图、数据、表格和正文是否同源一致。改图、更换数据源或投稿前审查时，按下面顺序检查：

1. 先建溯源对照表：每张数据图记录图号、精确数据来源（采集批次/run 编号或数据文件，不只写目录）、绘图/导出脚本和对应的正文、表格位置。批量任务写进 `figure_index.md`，`raw_data_path` 精确到批次/run。
2. 核验来源声明。图注和正文里"同一采集""同一批次""N 条采集"这类说法必须对着实际数据文件核验；多个子图声称同源时，逐个子图确认数据路径一致，不能只看图形效果。
3. 选取规则必须可核验。图注写明可复算的判据（如"较差一路 pre-FEC BER 居该批中位的一次采集"），不用"代表性""性能接近中位水平"这类无法核验的措辞；代表性数据优先直接取结果表工作点批次里的样本，让图、表、正文同一来源。
4. 样本数要能复算。图注/正文出现的样本数（如"404 条采集"）要能从主记录表加过滤条件重新算出来；差 1 条也要查导出脚本的过滤逻辑，弄清原因再定表述。
5. 改图后做关键数值多处对齐。同一数值在摘要、正文、表格、图注和结论中逐处核对；多人或多会话并行改稿后必须重跑这一步。
6. 贴边结论要标记。正文措辞与实测值余量很小时（如写"X 以上"而实测值只比 X 大 0.02），提示作者换成有余量或更精确的说法，由作者拍板，不擅自改结论强度。

核验结果按下面结构记录，一图一条：

```text
figure_id: Fig. X
声明: <图注/正文里的来源或数量说法>
实际数据源: <批次/run/脚本>
核验结论: 一致 / 不一致（差异说明） / 需改措辞
```

## 重画数据图

有原始数据时，优先用 Python/Matplotlib 重画：

1. 读取原始数据，不手动改数据点。
2. 单栏图使用 `use_ieee_single_column_style()`、`repair_single_column_figure()`、`preflight_single_column_figure()` 和 `export_ieee_single_column()`；`use_ieee_style()`、`save_ieee_figure()` 只为旧通用脚本保留。
3. 第一次为一篇论文出图时，用 `propose_figure_color_map()` 按数据角色给出候选，再由用户确认一次并用 `freeze_figure_color_map()` 冻结全文映射。
4. 无序类别使用 Tol high-contrast、bright 或 muted，并配合线型和 marker；连续量使用 `cividis` 或 `viridis`；阈值、参考线和普通 Delta 标注默认黑色。
5. 先生成 draft 并按最终 `3.5 in` 尺寸检查；只有 profile 中记录配色确认和视觉确认后才生成 formal PDF/SVG/PNG。
6. 保留重画脚本、数据来源说明、plot profile 和导出 manifest，保证论文修改时可复现。

阈值、规范线和普通参考线统一贴线标注：默认放在坐标框内的右端、略高于线条，且不单独占用图例；右端拥挤时沿线移动到空白端并保持相同规则。

如果用户只给截图，先说明无法保证数据精确；只有用户接受近似复刻时，才输出 `approximate_redraw`。

## 多子图尺寸和精确导出

当用户要把多个独立数据图拼成 IEEE 单栏或双栏多子图时，不要把某一次的子图尺寸写成通用标准。先由目标版式反推单张子图尺寸，再记录本次实际数值。

推荐顺序：

1. 明确总宽度：单栏通常 `3.5 in`，双栏通常 `7.16 in`，以目标期刊模板为准。
2. 明确同一行子图数量、子图间距、是否要给外部图题或手动标注留空间。
3. 用 `compute_panel_size(total_width, ncols, total_gutter_in, height_ratio)` 计算单张子图尺寸；`height_ratio` 根据数据密度和最终可读性决定。
4. 如果子图要在 PPT、Illustrator 或 LaTeX 中精确拼版，保存时用 `save_exact_size_figure()`，它使用 `bbox_inches=None` 和 `pad_inches=0.0`。不要用 `bbox_inches="tight"` 做最终拼版图，因为它会改变真实外框尺寸。
5. 用 `apply_axes_box()`、`apply_compact_axis_spacing()` 和带显式 `grid_mode` 的 `apply_ieee_grid()` 统一坐标轴区域、轴题距离、刻度数字距离和网格样式。
6. 在项目内保存 plot profile。profile 至少记录 `figsize`、`subplots_adjust`、`labelpad`、tick pad、legend anchor、线宽、字体、坐标范围、输出格式、dpi、源脚本、数据文件和输出文件。

上下堆叠图不固定某个 `hspace`。`repair_single_column_figure()` 按显示坐标测量上方面板最低可见内容（横轴刻度、轴题和面板编号）到下一坐标框上边界的距离，并自动收敛到 `4 pt`；这样图高或标签长度变化时仍保持紧凑且不遮挡。

具体记录模板见 `references/matplotlib-ieee-plot-profile.md`。尺寸、间距等示例数值仍只属于当前图组；网格模式在 `major_xy` 与 `none` 之间选择，并在 profile 中记录。

## 数据图视觉编码优先级

数据图先按信息角色定视觉编码，再定具体颜色。IEEE 没有唯一官方 HEX 色表，不要把某一篇论文里的 blue/orange/gray 经验写成通用答案。颜色只是分类、顺序、差异或强调的一层编码，不能承担全部区分任务。需要具体色表时，先读 `references/data-plot-color-priority.md`。

决策顺序：

1. 先判断数据角色：主结果、对照/基线、阈值/规范线、理论曲线、拟合/趋势、不确定性区间、异常/告警、背景区域、多面板共享变量。
2. 先用位置和几何形态表达关系：坐标轴、排序、分组、子图拆分、直接标注、线宽层级。
3. 再加冗余编码：线型、marker、填充纹理、灰度深浅、透明度；黑白打印时仍应能读。
4. 最后选颜色。颜色方案要服务于数据关系，不先套固定 palette；一旦本篇论文确定某个优先级颜色，就在不同图中保持一致。

通用优先级表，具体颜色见 `references/data-plot-color-priority.md`：

| 数据角色或图类型 | 优先视觉编码 | 颜色建议 | 注意事项 |
| --- | --- | --- | --- |
| 单序列、主结论曲线 | 线宽、marker、直接标注、最高识别优先级 | 使用本篇论文的一级强调色 | `主结果`表示识别优先级；不同论文可以重新定色，同一篇论文内应一致 |
| 少量无序类别曲线/柱形 | 颜色 + 线型/marker/纹理 | 使用本篇论文的离散类别色表 | 类别超过 4 条时不能只靠颜色区分 |
| 对照、基线、参考态 | 灰度、细线、虚线、浅 marker | 深灰或中灰 | 弱于主结果，但要能被识别 |
| 阈值、理论极限、规范线 | 细虚线、点划线、短文字标注 | 浅灰或中灰 | 不使用抢眼颜色，不抢主数据 |
| 拟合线、趋势线 | 与原始数据关联的线型或透明度 | 主数据同色的深浅版本，或灰色 | 不新增一个独立语义色 |
| 置信区间、误差带、工作区间 | 半透明填充、灰阶填充、边界线 | 主线同色浅色透明填充，或浅灰填充 | 透明度不能遮挡原始数据 |
| 有序强度、热力图、谱图 | 连续色图 + colorbar | `viridis`、`cividis`、`gray` 等感知均匀 sequential colormap | 避免 `jet`、rainbow 和红绿单通道 |
| 正负偏差、增益/损耗差值热图 | 以中心值分开的 diverging colormap | Tol `nightfall` | 必须明确中心值，如 `0`、`baseline` 或 `no change`；普通 Delta 数值或参考线仍用黑色 |
| 多子图共享变量 | 同一变量同一颜色/线型/marker | 沿用全篇色表 | 不因某个子图曲线数量不同而重新排序颜色 |
| 双 Y 轴图 | 轴题、刻度、对应 spine 和数据关联 | 可让左右轴颜色跟对应数据一致 | 上下边框通常保持黑色，避免图框过花 |

缺少项目色表时，调用 `propose_figure_color_map()` 建立候选 `figure color map`。候选未确认只能出 draft；用户确认一次后调用 `freeze_figure_color_map()`，同一物理变量的颜色、线型和 marker 在全文保持不变。

出图前检查：转灰度后能区分；色盲场景不依赖红绿差异；最终单栏/双栏尺寸下线型和 marker 仍可见；图例只负责识别数据类别，拟合方法、`R^2` 和实验条件优先放图注或正文。

## 系统图和机制图

系统图、机制图、实验平台图按“技术准确优先”处理：

- 信号流方向清楚，默认左到右或上到下
- 太赫兹链路中的 TX、RX、LO、Mixer、PA/LNA、ADC/DAC、IF/baseband、antenna/waveguide 等模块命名统一
- 关键频率、带宽、采样率、调制方式、功率、损耗、距离、测量点和数据流方向要标清
- 模块边框和连线足够细，不用厚重装饰线
- 标签短、准、统一，图注再解释细节
- 可编辑源优先保留为 PPTX、SVG、draw.io、TikZ 或 Mermaid，不只给 PNG 截图

## 卫星地图和外场链路图

论文里的 Google Earth / Google Maps / 卫星地图链路图按 `photo_or_screenshot` 或 `multi_panel` 处理。目标是给外场实验位置和距离提供可信背景，不把地图当成装饰图。

推荐流程：

1. 先问清用途：论文单栏/双栏、PPT 汇报、还是只做内部记录。用户问“怎么导出/怎么标注”时，先讲菜单步骤和取舍，不擅自操作或导出用户文件。
2. 在 Google Earth Pro 里只做位置确认、placemark/path/ruler 测距和高分辨率底图导出。优先用 `File > Save > Save Image...`，不要把普通屏幕截图当论文主图。
3. 自定义论文标注优先放到 PowerPoint、Illustrator、Inkscape 或 SVG 里做矢量对象，包括 TX/RX、起点/终点、link line、distance label、箭头、子图编号和说明文字。
4. Google Earth 里可以临时加 placemark/path 辅助定位，但最终论文图不依赖 Google Earth 内置标签样式；这样字体、线宽、红色虚线框和其他子图能统一。
5. 保留 Google attribution 和数据来源标注，不裁掉、不遮挡。若目标期刊或机构有额外版权要求，按 Google Geo Guidelines 和期刊说明复核。
6. 图内文字要严格区分已完成实验和计划链路，例如 `measured 350 m link`、`planned 1 km link` 或 `prospective 1 km link`。不要把未实测距离写成 measured。
7. 双栏 composite figure 中，先定总画布和各 panel 的信息量；地图底图只占其中一块时，不要为了导出整张图而提前改 PPT 或覆盖用户源文件。
8. 如果需要帮用户继续出图，先确认可编辑源文件、目标页/子图、是否允许生成新副本。没有确认前，只给步骤或审查建议。

## RF/THz 系统示意图

处理射频、微波和太赫兹实验系统图时，先把“实物连接关系”和“器件功能关系”分开：

- 先确定图要表达的抽象层级。功能原理图写功能操作（如 `sideband separation` 或 `I/Q combining`）；具体实现图按该文章实际使用的硬件或算法标注。不要把某一种实现方式写成跨文章的必要条件。
- 功能等价不等于器件一一对应。检查输入分量、处理模块和输出支路之间的真实数学或物理关系，不要仅凭标签把一个输入分量直接当作一个已分离输出。
- 对 `I/Q` 等正交分量，若输出分离依赖联合处理，图中应先画联合处理，再画分离后的支路；只有系统定义确实支持一一对应时，才画成直接映射。
- 画系统图前先找 2-4 张已发表参考图，不凭感觉定版式。优先找近 5 年内 IEEE Transactions / IEEE Letters、Nature/Science 子刊或同领域顶级期刊里的相似系统图；记录论文、DOI、图号/图注和可借鉴点。
- 参考图只借鉴版式、端口标注、线型、箭头强弱和信息密度，不直接照抄图形；涉及相似系统图的检索结果，要优先保存到当前项目的 `sources/` 目录，方便论文图修改时追溯。
- 不按作者姓名、机构或国籍推断“英语母语”。需要英文和图件质量时，用期刊层级、同行评审、图注写法和图件成熟度作为判断依据。
- 若找不到近 5 年内高度相似的 IEEE 期刊图，要明确降级来源：更早但经典的期刊图、IEEE 会议、厂商应用笔记、教材或专利只能作为次级参考，不能替代投稿图风格依据；找不到时直接说明，不要硬凭感觉画。
- 端口编号按实物、正文和照片保持一致；功能名称另标。例如 `Port 2` 可以同时标为 `isolated port` 或 `terminated port`。
- 如果论文图要和实验照片对照，端口的空间方位优先贴近实物安装关系。偏心引出线可以保留，只要不改变技术含义。
- directional coupler、bidirectional coupler、bridge coupler 等器件不要只画成装饰性大矩形。优先用简洁的传输线、端口和耦合方向表达，再配短标签说明功能。
- 外接匹配负载要画在器件边界外。不要把外部 `50-ohm matched load` 画成耦合器内部自带电阻，除非用户明确要画内部电桥原理。
- 隔离端口端接时，画法应表达“端口被匹配吸收”，不要用很强的主信号箭头把它画成主要输出通路。
- 监测端、耦合端和干扰注入端要区分线型或箭头强弱；主传输链路最突出，辅助测量链路次之。
- 对小电路符号、端接符号、接地符号这类线稿，优先直接生成 SVG 或 PPT 原生形状。不要用 AI 位图生成替代可编辑矢量线稿。
- 不要默认把 agent 生成的整张系统图当成最终稿。用户已经有自绘 PPT/SVG 草图时，优先帮用户校准端口逻辑、论文符号和局部矢量元件，再审查或微调用户自己的图。

## 输出格式

审查意见默认使用下面结构：

```markdown
# 图件审查结果

## 总体结论
- 图件：Fig. X
- 类型：data_plot / system_diagram / mechanism_diagram / photo_or_screenshot / multi_panel
- 结论：可直接用 / 小修后可用 / 建议重画 / 必须重画
- 目标尺寸：single-column / double-column / unknown

## 必须改
- ...

## 建议改
- ...

## 可保留
- ...

## 重画或导出建议
- ...
```

批量处理时，`figure_index.md` 至少记录：

- `figure_id`
- `type`
- `source_path`
- `raw_data_path`
- `editable_source_path`
- `plot_profile_path`
- `target_width`
- `review_status`
- `output_path`
- `notes`

## 与其他技能的边界

- 用户只要“审图、改图、重画 IEEE 论文图”，直接用本 skill。
- 用户要整篇 IEEE 论文结构、英文表达、图文关系和投稿风格精修时，本 skill 只负责图件部分，正文交给论文精修类 skill。
- 用户要从 PDF 里提取图或读论文图注时，可配合 `pdf` skill。
- 用户要改 PPT 源文件时，可配合 `pptx` skill，但图件标准仍按本 skill 判断。

## 来源与吸收边界

- IEEE 图件格式以 IEEE Author Center 和目标期刊/会议说明为最终准绳。
- K-Dense `scientific-visualization` 固定到提交 `13385c7c4db02fdcc84a020752c07cce91ef780e`；只吸收角色配色、精确尺寸导出 manifest 和预检方法，不复制其 Arial、开放坐标轴、向外刻度或外边距参数。
- Paul Tol 的 high-contrast、bright、muted 和 nightfall 静态色值用于候选配色；不把颜色当作唯一识别编码。
- Liberation Serif 2.1.5 是 Times New Roman 缺失时的固定备用字体，来源提交 `49e1358e4017577429c9f8c39a3e6e879093264e`，按 SIL OFL 1.1 分发；详情见 `THIRD_PARTY_NOTICES.md` 和 `assets/fonts/manifest.json`。
- Galaxy-Dawn `claude-scholar` 的 paper-self-review 审计思路（主张与证据对齐、避免超出证据强度的措辞、结构化核验记录）吸收进「数据溯源与图-表-文一致性」一节。
- 不吸收自由生成型 `generate-image` / `infographics` 风格作为论文图默认风格。
