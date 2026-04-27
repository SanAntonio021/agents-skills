---
name: lunwen-tujian-guifan
description: 审查、规范化和重画 IEEE 论文图件。Use when 用户要审查已画好的图、判断图是否符合 IEEE 投稿风格、把数据图重画成论文图、处理太赫兹/通信系统论文里的曲线图、频谱图、BER/SNR/EVM/带宽/链路预算图、系统框图、机制图、实验平台图或多子图；优先用原始数据和可编辑源文件，按 IEEE 单栏/双栏尺寸、字体、线宽、分辨率和黑白可读性输出可投稿版本。
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

## IEEE 默认基线

默认按 IEEE 工程类论文图件处理：

- 单栏宽度：`3.5 in` / `89 mm`
- 双栏宽度：`7.16 in` / `182 mm`
- 图中文字：最终尺寸下优先 `8-10 pt`，拥挤图不要低于可读底线
- 字体：优先 Arial、Helvetica 或相近无衬线字体
- 线图：优先 PDF/EPS 矢量；如需栅格，线稿按 `600 dpi` 起
- 照片或灰度图：通常按 `300 dpi` 起
- 彩色：线上可用 RGB，但必须保证黑白打印和色盲场景仍能区分
- 子图编号：IEEE 论文中通常用 `(a)`, `(b)`, `(c)`，并和正文、图注一致
- JPEG 不作为论文图默认格式；作者照片例外

更细的检查项见 `references/ieee-figure-review-checklist.md`。

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

## 重画数据图

有原始数据时，优先用 Python/Matplotlib 重画：

1. 读取原始数据，不手动改数据点。
2. 使用 `scripts/ieee_plot_style.py` 中的 `use_ieee_style()`、`ieee_figure_size()` 和 `save_ieee_figure()`。
3. 统一字体、线宽、标记、图例、坐标轴单位和输出尺寸。
4. 使用色盲友好配色，并用线型、标记或纹理做冗余区分。
5. 导出 PDF/EPS 作为投稿主文件，必要时同时导出 PNG/TIFF 预览。
6. 保留重画脚本和数据来源说明，保证论文修改时可复现。

如果用户只给截图，先说明无法保证数据精确；只有用户接受近似复刻时，才输出 `approximate_redraw`。

## 系统图和机制图

系统图、机制图、实验平台图按“技术准确优先”处理：

- 信号流方向清楚，默认左到右或上到下
- 太赫兹链路中的 TX、RX、LO、Mixer、PA/LNA、ADC/DAC、IF/baseband、antenna/waveguide 等模块命名统一
- 关键频率、带宽、采样率、调制方式、功率、损耗、距离、测量点和数据流方向要标清
- 模块边框和连线足够细，不用厚重装饰线
- 标签短、准、统一，图注再解释细节
- 可编辑源优先保留为 PPTX、SVG、draw.io、TikZ 或 Mermaid，不只给 PNG 截图

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
- K-Dense `scientific-visualization` 的 publication-ready、journal formatting、colorblind-safe、multi-panel、export 思路可作为绘图底座。
- K-Dense `matplotlib` 的细粒度绘图控制可作为数据图重画底座。
- K-Dense `venue-templates` 的 IEEE 投稿边界可作为辅助参考。
- 不吸收自由生成型 `generate-image` / `infographics` 风格作为论文图默认风格。
