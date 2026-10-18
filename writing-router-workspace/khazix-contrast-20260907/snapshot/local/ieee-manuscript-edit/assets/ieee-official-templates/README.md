# IEEE 官方模板运行资源

日期：2026-05-02

本目录保存从 IEEE 官方 Template Selector 获取并整理出的可直接使用的 Word 和 LaTeX 模板。CC Switch 分发本目录，但不分发原始下载 ZIP、生成 PDF 或系统元数据。

官方入口：

- IEEE Author Center: https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/tools-for-ieee-authors/ieee-article-templates/
- IEEE Template Selector: https://template-selector.ieee.org/

## 已分发模板

| 目录 | 用途 | Word | LaTeX |
|---|---|---|---|
| `transactions-journals-letters/` | IEEE Transactions/Journals/Letters 通用模板；IEEE Transactions on Terahertz Science and Technology 与 IEEE Transactions on Microwave Theory and Techniques 当前都指向这组模板 | `word-extracted/ieee-transactions-template.docx` | `latex-extracted/bare_jrnl_new_sample4.tex` 及同目录依赖 |
| `ieee-access/` | IEEE Access 专用模板 | `Access_Word_Template.docx` | `latex-extracted/ACCESS_latex_template_20240429/access.tex` 及同目录依赖 |
| `ieee-journal-of-microwaves/` | IEEE Journal of Microwaves 专用模板 | `JMW_Word_Template.docx` | `latex-extracted/IEEE_JMW_LaTex_Template_Oct18_2021/JMW_template.tex` 及同目录依赖 |

## 完整来源快照

完整官方下载包和全部解压内容保存在：

```text
D:\BaiduSyncdisk\.agents\downloads\ieee-official-templates\<snapshot-date>
```

每个快照用 `manifest.sha256` 固定文件集合和内容。该快照只作来源追溯与恢复，不是技能运行依赖。

## 官方 API 对应关系

下载接口格式：

```text
https://template-selector.ieee.org/api/ieee-template-selector/template/<association-id>/download
```

本次使用的 association id：

- `54`: IEEE Transactions on Terahertz Science and Technology / Word
- `292`: IEEE Transactions on Terahertz Science and Technology / LaTeX
- `447`: IEEE Access / Word
- `541`: IEEE Access / LaTeX
- `544`: IEEE Journal of Microwaves / Word
- `545`: IEEE Journal of Microwaves / LaTeX

补充核对：

- IEEE Transactions on Microwave Theory and Techniques 当前也返回同一组通用 Transactions 模板：Word 为 `IEEE-Transactions-Word-templates-and-instructions.zip`，LaTeX 为 `IEEE-Transactions-LaTeX2e-templates-and-instructions.zip`。

## 后续使用与更新

- 当前论文如果按 IEEE Transactions 类目标处理，优先使用：
  - Word 参考模板：`transactions-journals-letters/word-extracted/ieee-transactions-template.docx`
  - LaTeX 主文件：`transactions-journals-letters/latex-extracted/bare_jrnl_new_sample4.tex`
- 如果目标改成 IEEE Access，再使用 `ieee-access/`。
- 如果目标改成 IEEE Journal of Microwaves，再使用 `ieee-journal-of-microwaves/`。
- 上游 skill 里的 venue/template 说明只能作为检查清单，不能作为官方模板来源。
- 更新模板时先创建新的日期快照，再同步可直接使用的 `.docx`、`.tex`、`.cls`、样式、字体和图片依赖。
- 原始 ZIP、生成 PDF、`__MACOSX`、`.DS_Store` 和 `._*` 不进入本目录的 Git 提交。
