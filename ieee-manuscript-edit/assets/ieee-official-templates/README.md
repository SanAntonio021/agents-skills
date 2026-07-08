# IEEE 官方模板下载记录

日期：2026-05-02

本目录保存从 IEEE 官方 Template Selector 下载的 Word 和 LaTeX 模板。它们不是从上游 skill 仓库复制的模板。

官方入口：

- IEEE Author Center: https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/tools-for-ieee-authors/ieee-article-templates/
- IEEE Template Selector: https://template-selector.ieee.org/

## 已下载模板

| 目录 | 用途 | Word | LaTeX |
|---|---|---|---|
| `transactions-journals-letters/` | IEEE Transactions/Journals/Letters 通用模板；IEEE Transactions on Terahertz Science and Technology 与 IEEE Transactions on Microwave Theory and Techniques 当前都指向这组模板 | `IEEE-Transactions-Word-templates-and-instructions.zip`；已解压到 `word-extracted/` | `IEEE-Transactions-LaTeX2e-templates-and-instructions.zip`；已解压到 `latex-extracted/` |
| `ieee-access/` | IEEE Access 专用模板 | `Access_Word_Template.docx` | `Access_LaTeX_template.zip`；已解压到 `latex-extracted/` |
| `ieee-journal-of-microwaves/` | IEEE Journal of Microwaves 专用模板 | `JMW_Word_Template.docx` | `JMW_LaTex_Template.zip`；已解压到 `latex-extracted/` |

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

## 后续使用建议

- 当前论文如果按 IEEE Transactions 类目标处理，优先使用：
  - Word 参考模板：`transactions-journals-letters/word-extracted/Transactions-template-and-instructions-on-how-to-create-your-article-formatted (4).docx`
  - LaTeX 主文件：`transactions-journals-letters/latex-extracted/bare_jrnl_new_sample4.tex`
- 如果目标改成 IEEE Access，再使用 `ieee-access/`。
- 如果目标改成 IEEE Journal of Microwaves，再使用 `ieee-journal-of-microwaves/`。
- 上游 skill 里的 venue/template 说明只能作为检查清单，不能作为官方模板来源。
