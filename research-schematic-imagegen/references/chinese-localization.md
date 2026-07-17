# 中文化与文字纠错

## 基本原则

- 中文化是基于已确认构图的编辑任务，不默认重新生图。
- 标签优先使用 2-8 个汉字或简短中英混合术语。
- 专业缩写如 `DFT-s-OFDM`、`LDPC`、`CRC`、`TDD` 保持原样。
- 不把英文长句逐字翻译成中文长句；先压缩为技术短语。
- 每个标签必须来自技术合同，不让模型自行改写术语。

## 编辑提示词

```text
Edit the supplied scientific schematic while preserving all geometry, arrows, icons, colors, layout, and technical relationships.

Replace only the specified labels with the exact Chinese text below:
- "[old label]" -> "[exact Chinese label]"

Render the Chinese text exactly, with no extra characters, no synonyms, no paraphrasing, and no changes outside the label area.
Match the existing font weight, size, alignment, background color, and spacing.
```

局部遮罩时再补一句：

```text
Modify only the transparent/masked label region. Everything outside the mask must remain pixel-identical in composition and meaning.
```

## 失败处理

1. 第一次错误：缩短提示词，只保留目标文字和“不改其他内容”。
2. 第二次错误：使用紧贴文字区域的遮罩重新编辑。
3. 仍错误：停止调用模型。对纯色或规则色块区域使用确定性覆盖。

不要连续重复同一提示词。模型两次都写错同一个词时，继续重试通常只增加成本和版本混乱。

## 确定性覆盖

`fix-label.ps1` 适合纯色标签框、白底标题区和规则矩形区域。它会覆盖指定矩形，再绘制准确文字。

使用前确认：

- 覆盖区域不包含箭头、图标或渐变背景。
- 坐标和尺寸没有超出图片范围。
- 背景色、文字色、字体和字号与原图相近。

使用后检查：

- 放大查看目标文字。
- 检查矩形边缘是否露出旧文字。
- 检查相邻箭头和模块是否被覆盖。
- 再按 PPT 实际显示尺寸检查可读性。
