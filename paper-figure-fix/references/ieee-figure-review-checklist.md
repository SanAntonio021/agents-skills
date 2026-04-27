# IEEE 图件审查清单

## 0. 官方核验入口

投稿和定稿前优先查这些入口，不只依赖本地经验：

- IEEE Author Center - Create Graphics for Your Article: https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/
- IEEE Author Center - File Formatting: https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/
- IEEE Author Center - Tools for IEEE Authors: https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/tools-for-ieee-authors/
- IEEE Graphics Analyzer 已下线，投稿系统会自动检查图件；历史模板里提到的 `graphicsqc.ieee.org` 不再作为默认路线。

## 1. 先判定图件角色

- 这张图是否真的支撑论文的一个关键结论？
- 图件类型是否正确：数据图、系统图、机制图、照片/截图、多子图？
- 如果删掉这张图，正文是否仍然完整？如果完整，考虑改成表格、文字或补充材料。

## 2. IEEE 基础格式

- 图宽是否按单栏 `3.5 in / 89 mm` 或双栏 `7.16 in / 182 mm` 设计？
- 单个图件最终尺寸不要超过 IEEE 常见上限 `7.16 x 8.8 in`，除非目标刊物另有说明。
- 最终尺寸下文字是否能读清？优先保持 `8-10 pt`。
- 线稿是否优先导出 PDF/EPS 矢量文件？
- 栅格图是否满足最终尺寸下的分辨率：照片/灰度图约 `300 dpi` 起，线稿约 `600 dpi` 起？
- 文件格式是否为 IEEE 常见可处理格式：PDF、EPS、PNG、TIFF 等？
- 是否避免把普通 JPEG 当论文图主文件？

## 3. 可读性

- 缩到论文最终版面后，坐标轴、图例、单位、子图编号仍然清楚。
- 图中文字不过密，不把解释性长句塞进图内。
- 图例不遮挡数据，不漂在关键曲线或热点区域上。
- 坐标轴刻度数量适中，刻度标签不重叠。
- 多子图之间尺寸、字体、线宽、坐标轴风格一致。

## 4. 数据图

- 横纵坐标必须有物理量和单位，例如 `Frequency (GHz)`、`Power (dBm)`、`BER`、`EVM (%)`。
- dB、dBm、GHz、THz、Gbps、mmWave、IF、RF 等单位写法统一。
- 对数坐标要明确，不让读者误解趋势。
- 曲线数量超过 4 条时，必须用颜色以外的冗余区分：线型、marker、灰度、标注。
- 误差条、置信区间、重复次数、仿真/实测条件不能含糊。
- 平滑曲线不得掩盖原始采样点；必要时同时显示 marker。
- 数据图重画必须保留脚本和原始数据路径。

## 5. 太赫兹通信系统图

- 发射端、信道、接收端、基带/中频/射频/太赫兹链路边界清楚。
- TX/RX、LO、Mixer、PA/LNA、ADC/DAC、DSP、antenna、waveguide 等模块命名统一。
- 频率、带宽、调制方式、采样率、符号率、链路距离、发射功率、接收功率等关键参数按图件目的选择性标注。
- 测量点和数据流方向清楚，不把硬件链路和算法流程混在一起。
- 实验平台图要能对应正文中的测试条件和仪器连接关系。

## 6. 机制图和系统框图

- 先保证技术含义，不追求装饰感。
- 连线方向明确，交叉线少；必要时拆成两个子图。
- 模块大小按逻辑层级组织，不按视觉花样随机摆放。
- 不使用渐变背景、厚阴影、立体按钮、卡通图标。
- 可编辑源文件必须保留，避免后续只能改截图。

## 7. 多子图

- 子图编号使用 `(a)`, `(b)`, `(c)`，并与正文和图注一致。
- 子图之间留白足够，但不浪费版面。
- 共享坐标轴时，避免重复标签；不共享时，单位必须各自写清。
- 颜色、线型、图例命名在所有子图中保持一致。
- 图注要解释每个子图的含义，不能只写 “Results.”。

## 8. 黑白与色盲可读

- 转灰度后仍能区分曲线、柱形、区域和标注。
- 不把红/绿作为唯一差异。
- 热力图优先使用感知均匀色图，如 `viridis`、`cividis`，避免 `jet` 和彩虹色图。
- 重要类别用线型、marker、纹理或直接标注做冗余编码。

## 9. 审查结论分级

### 必须改

- 数据或技术含义可能误导
- 最终尺寸下文字、坐标轴或图例读不清
- 缺少单位、实验条件或关键标注
- 分辨率明显不够，或截图痕迹严重
- 只有位图且后续还需要反复修改

### 建议改

- 配色不够稳，但不影响基本理解
- 图例位置、留白、字体、线宽还能更统一
- 图注和图内标注有轻微不一致
- 单栏太挤，建议改双栏或拆图

### 可保留

- 技术含义准确
- 最终尺寸可读
- 格式和分辨率基本满足要求
- 后续有可编辑源文件或可复现脚本

## 10. 最终交付

每张定稿图尽量同时保留：

- 投稿图：PDF/EPS/TIFF/PNG
- 预览图：PNG
- 可编辑源：PPTX/SVG/draw.io/TikZ/Mermaid/Python/MATLAB/Origin
- 数据来源：CSV/XLSX/MAT/MATLAB 脚本或实验记录
- 审查记录：`figure_review.md` 或 `figure_index.md`
