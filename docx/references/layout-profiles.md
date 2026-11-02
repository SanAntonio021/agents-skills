# 文档系列的格式检查与模板复用

反复使用同一类报告时，保留已验收底稿，再从其样式、编号、多节页面和记录表制作空白骨架。单纯把样式复制到新文件，不能复现横向表格页、正文起始页码或整张记录表的分页。

## 静态格式检查

`scripts/layout_audit.py` 只读检查 DOCX/DOTX，按文档系列自己的 JSON 规则核对格式；不提供通用字体或行距默认值。

```powershell
python <skill-root>/scripts/layout_audit.py report.docx --rules family.rules.json --report audit.json
```

已有报告不覆盖。退出码 0 表示声明的静态项目通过，1 表示发现差异，2 表示输入或规则错误。报告记录源文件和规则 SHA-256、检查范围、文字定位和 XML XPath；`layout_status` 始终为 `NOT_CHECKED`。不能据此声称分页、渲染或字段已通过。

规则示例，数值只属于这个示例：

```json
{
  "schema": 1,
  "a4": true,
  "table_grid": true,
  "paragraph_rules": [
    {"name": "正文", "select": {"style": "TestBody"}, "min": 1,
     "expect": {"first_line_chars": 2, "font_east_asia": "宋体", "font_ascii": "Times New Roman"}},
    {"name": "步骤缩进", "select": {"auto_numbered": true}, "min": 1,
     "expect": {"left_pt": 24, "hanging_pt": 6}}
  ],
  "numbering_groups": [
    {"name": "四组步骤", "select": {"auto_numbered": true}, "counts": [3, 3, 3, 3], "start": 1}
  ]
}
```

- `select` 支持 `style`（原始 styleId）、`text`、`text_regex`、`in_table`、`auto_numbered`，各条件取交集；`min` 默认 1，`max` 默认不限制。需要禁止某类文字时可设 `min=0,max=0`。
- `expect` 支持 `alignment`、`first_line_chars`、`first_line_pt`、`left_pt`、`hanging_pt`、`line`、`line_rule`、`before_pt`、`after_pt`、`outline_level`、`keep_next`、`widow_control`、`font_ascii`、`font_east_asia`、`size_pt`、`bold`、`color`。
- 磅值使用 pt；字符缩进使用字符数；`line` 为 OOXML 原始值，如 `line_rule=auto,line=300` 表示 1.25 倍。字符首行缩进存在时不把 twips 值当作生效值。
- 解析文档默认值、段落样式继承、编号层缩进、字符样式与直接格式。主题字体和主题颜色未解析时报告未解析值；不把缺省值猜成某种字体。条件表格样式未求值，相关字体须另查。
- `numbering_groups` 按 numId 和层级核对定义起号与选中段落数，不模拟全部 Word 计数器；显示出的连续性仍须原生检查。表格网格检查发现列跨度或宽度差异，是否属于排版缺陷需结合渲染判断。
- 范围限主文档正文及其表格；页眉页脚、公式字体、图形内文字、分页和字段新鲜度不在此工具结论中。

## 从验收稿制作本地模板

1. 保留已验收稿作为内容底稿。通用空白骨架移除项目专属指标、实测数据、姓名和评审结论，填入明确占位内容。底稿及含私有内容的模板留用户项目，不带入公开技能。
2. 按用途保留正文、标题、表格、含公式段落和附录说明的样式。步骤使用自动编号、各测试项独立起号；用段前段后间距控制标题间隔。
3. 保留需要的多节页面、页眉页脚、编号域、交叉引用、重复表头和填写空间。目录明确采用哪些层级；资料小标题需要独立样式时，避免意外进入主目录。
4. 在本地保存同系列规则和简短使用说明。规则与实际骨架一并验收；新增内容导致换页后，仍检查受影响页及前后衔接。
5. 使用现有安全 Word 收尾和原生检查流程生成预览。分别记录静态格式结果与页面结果；模板可用不代表填入任意内容后分页保持不变。

修改 `word/styles.xml` 继续通过 `scripts/styles_normalizer.py` 的写边界。
