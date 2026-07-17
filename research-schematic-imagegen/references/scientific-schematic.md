# 科研示意图提示词模板

提示词可用英文描述视觉要求，但图内标签必须来自技术合同。不要让模型翻译或发明专业术语。

## 通用模板

```text
Create a high-density scientific engineering schematic for [literal technology or mechanism].

Audience and use:
- [natural science proposal / engineering proposal / technical defense presentation]
- 3:2 landscape canvas, [1536x1024]

Technical narrative:
- Main line: [one-sentence technical relationship]
- Show these required components and flows: [must-show list]
- Use arrows to distinguish [main signal/data flow] from [control/feedback/measurement flow]
- Keep the physical layer, algorithm layer, control layer, and validation layer visually distinct when applicable

Exact labels:
- Use only these labels: [approved short labels]
- Render every label exactly as written
- No paragraphs, slogans, invented acronyms, or placeholder text

Do not show:
- [forbidden or obsolete concepts]
- [unconfirmed quantitative values]
- decorative charts, marketing icons, radar dashboards, fictitious measurements, or ornamental background graphics

Visual system:
- clean white background
- restrained dark blue, blue-gray, charcoal, with at most one warm accent color
- publication-grade technical illustration, precise geometry, thin lines, clear arrow hierarchy
- compact but readable information density
- no gradients, glow, dark grid, photorealistic stock-scene background, or decorative frame
- no nested cards and no large text blocks

Composition:
- [left-to-right / top-to-bottom / closed-loop / central mechanism] layout
- title at a consistent top position
- leave safe margins for PPT placement
```

## 结构选择

### 信号处理链

适合波形、同步、捕获、编码、接入和传输控制。

```text
Input/environment -> front-end observation -> estimation/synchronization -> decision/control -> communication output
```

主链横向排列；反馈链使用较细或虚线箭头。不要把算法模块画成独立设备。

### 多传感器闭环

适合光电粗捕获、射频精跟踪、波束控制和失锁重捕获。

```text
Target dynamics -> coarse observation -> fine RF tracking -> beam control -> link quality feedback -> reacquisition
```

粗捕获、精跟踪和预测重捕获必须用阶段或环路明确区分。

### 非对称收发架构

适合上下行功能不对称、TDD、导引信号与业务数据分工。

```text
Airborne terminal <-> propagation channel <-> ground terminal
Uplink function and downlink function must be separately labeled and visually unequal when technically asymmetric.
```

不要因为双向箭头就暗示上下行业务能力对称。

### 半实物仿真闭环

适合真实设备、信道注入、数字模型和测试控制混合。

```text
Real transmitter/receiver hardware -> channel/emulator injection -> measurement -> control and parameter update -> repeated closed loop
```

明确哪些是实物、哪些是实时仿真、哪些是离线分析。不要把半实物仿真画成已经完成的外场或飞行验证。

## 系列图一致性

- 第一张通过后记录颜色、字体、模块尺寸、箭头和标题位置。
- 后续提示词复制视觉系统，不复制不适用的技术结构。
- 同一术语在所有图中保持同一写法。
- 强调色在系列内保持同一含义。
