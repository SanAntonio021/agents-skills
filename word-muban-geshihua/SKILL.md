---
name: word-muban-geshihua
description: 用用户提供的 Word 模板、本机默认格式或仓内内置 style profile，把目标 `.docx` 统一成可交付版式。Use when 用户提供模板文档、要求沿用既有标题和正文格式、要求按 `Normal.dotm` 成稿，或源文件是 Markdown 但最终要落到 Word 版式；prefer this over 通用导出技能 when 关键目标是 Word 端样式落地。
---

# Word 模板格式化

## 作用

这份 skill 负责把“样例 Word 文档里的版式规则”稳定迁移到实际交付文档里。

它适合处理三类任务：

- 已有模板 `.docx`，要把同样的标题、正文、段落和页面设置用到另一份文档
- 用户说“按我平时 Word 默认格式来”，需要以 `Normal.dotm` 作为格式来源
- 源内容是 Markdown 或纯文本，但最终交付必须是符合现有 Word 模板的 `.docx`

当前内置预设名固定为：

- `tongyong-moren`
- `jishu-zongjie`
- `gongzuo-zongjie`
- `qiye-shenbao`

本机当前受治理的默认预设是 `qiye-shenbao`。用户未明确指定格式来源时，先按这个默认值处理；如果默认策略已变，再先确认。

## 流程

1. 先确认格式来源。
   可选来源只有四类：用户给的模板 `.docx`、`Normal.dotm`、内置预设、纯转换不套模板。
2. 再确认源材料类型。
   如果输入和输出都是 Word，直接走模板套用流程；如果输入是 Markdown 或纯文本，先转成 `.docx`，再做 Word 端格式落地。
3. 用户若明确说“按我 Word 默认格式”“按空白文档默认样式”，且没有给别的模板，就使用 `%APPDATA%\Microsoft\Templates\Normal.dotm`。
4. 用户若明确点名某个预设，就直接用该预设；公开仓默认只带该预设的 style profile，需要时会临时合成模板；不要把旧英文别名当主名称展示。
5. 用户若要查看样式清单、保存可复用规则或核对模板结构，先执行提取流程。
6. 用户若只关心交付文档，直接执行应用流程，默认输出到新文件，不覆盖原文档。
7. 请求若变成“维护预设体系”“更换默认模板”“重建 `tongyong-moren`”或“安装 `Normal.dotm`”，仍在这里处理，但优先使用现有脚本，不再拆独立治理 skill。

## 常用命令

### 提取模板规则

```powershell
python scripts/word_template_formatter.py extract
```

公开仓不再附带预设 `.docx` 资产；默认提取前要先准备你自己的模板文件。若你已经在本机保留了与某个预设对应的模板，也可以显式指定预设名后再传 `--template`：

```powershell
python scripts/word_template_formatter.py extract --preset qiye-shenbao
```

若用户给了明确模板路径：

```powershell
python scripts/word_template_formatter.py extract `
  --template C:\path\template.docx `
  --profile C:\path\template.style-profile.json `
  --report C:\path\template.style-profile.md
```

### 把模板格式应用到目标文档

```powershell
python scripts/word_template_formatter.py apply `
  --input C:\path\draft.docx `
  --output C:\path\draft.formatted.docx
```

公开仓默认用随仓附带的 style profile 临时生成模板，所以即使没有预设 `.docx` 资产，下面的预设模式也能直接用：

```powershell
python scripts/word_template_formatter.py apply `
  --preset qiye-shenbao `
  --input C:\path\draft.docx `
  --output C:\path\draft.formatted.docx
```

常用参数：

- `--title-mode auto`：自动识别题名
- `--title-mode first-paragraph`：强制把第一段当题名
- `--title-mode skip`：跳过题名自动处理
- `--clear-direct-formatting`：先清理直接格式，再套用样式
- `--body-style "Custom Body"`：指定正文样式名
- `--page-scope first-section`：只复制第一页或首节页面设置

### 先导出 Markdown，再落到 Word 模板

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_markdown_to_word.ps1 `
  C:\path\draft.md
```

这个流程会先把 Markdown 转成 `.docx`，再套用 Word 端格式。默认优先使用 `Normal.dotm` 或当前默认预设，而不是停在原始 `pandoc` 输出。

如果要指定预设：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_markdown_to_word.ps1 `
  C:\path\draft.md `
  -Preset qiye-shenbao
```

如果要指定模板文件：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_markdown_to_word.ps1 `
  C:\path\draft.md `
  -TemplatePath C:\path\custom-template.docx
```

## 规则

- 重点是“复制版式规则”，不是复制模板原文内容。
- 用户没明确说 plain conversion 时，不要把“导出 Word”理解成只做原始转换。
- 用户明确说“我的 Word 默认格式”时，优先把 `Normal.dotm` 当作权威来源。
- 能用 Word 内建样式时，优先沿用 `Title`、`Heading 1-9`、`Normal`、`Body Text`。
- 目标文档如果已经正确使用标题和正文样式，通常只要复制模板样式即可，不必重排内容。
- 目标文档如果大量依赖手工加粗、字号和段前段后，优先考虑加 `--clear-direct-formatting`。
- 展示给用户时，内置预设用拼音名；旧英文名只作为兼容别名存在，不作为主说法。
- 默认预设受治理规则控制，不要擅自把 `tongyong-moren` 当作所有场景的默认值。
- 公开仓只分发 style profile 和脚本，不分发原始样例 `.docx`。

## 边界

- 不把一次性的样例文档直接升级成正式预设。
- 不在没有验证的情况下改默认预设或替换全局 `Normal.dotm`。
- 低频治理动作也优先走现有脚本，不额外拆新的治理入口。

## 相关文件

- 主脚本：[scripts/word_template_formatter.py](scripts/word_template_formatter.py)
- Markdown 转 Word 包装脚本：[scripts/export_markdown_to_word.ps1](scripts/export_markdown_to_word.ps1)
- 预设构建脚本：[scripts/build_master_template.py](scripts/build_master_template.py)
- 默认预设校验脚本：[scripts/validate_master_default.py](scripts/validate_master_default.py)
- `Normal.dotm` 安装脚本：[scripts/install_normal_template.py](scripts/install_normal_template.py)
- 工作流说明：[references/workflow.md](references/workflow.md)
- 主预设说明：[references/master-template.md](references/master-template.md)
- 技术总结预设说明：[references/default-template.md](references/default-template.md)
- 企业申报预设说明：[references/qiye-shenbao-template.md](references/qiye-shenbao-template.md)

## 维护

- 以后如果默认预设变更，直接在这里和相关脚本里同步说明。
- 新增预设时，优先补充现有脚本和引用说明，不要在正文里堆过多一次性示例。
- 如果同类需求持续稳定出现，再补新的触发词或命令示例，不要把这份 skill 写成 Word 大全。
