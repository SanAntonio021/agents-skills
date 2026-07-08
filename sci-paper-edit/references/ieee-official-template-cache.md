# IEEE 官方模板技能资源

本文件说明 `sci-paper-edit` 技能内可复用的 IEEE 官方 Word/LaTeX 模板资源。模板文件放在技能 `assets/` 下，调用本技能时可直接作为参考模板使用。

## 资源位置

技能源码内位置：

```text
D:\Workspace\04-agents\agents-skills-src\sci-paper-edit\assets\ieee-official-templates
```

通用写法：

```text
<skill-root>\assets\ieee-official-templates
```

## 已内置模板

| 目录 | 用途 | Word | LaTeX |
|---|---|---|---|
| `transactions-journals-letters/` | IEEE Transactions/Journals/Letters 通用模板；IEEE Transactions on Terahertz Science and Technology 与 IEEE Transactions on Microwave Theory and Techniques 当前都指向这组模板 | `IEEE-Transactions-Word-templates-and-instructions.zip`；解压后可用 `word-extracted/Transactions-template-and-instructions-on-how-to-create-your-article-formatted (4).docx` | `IEEE-Transactions-LaTeX2e-templates-and-instructions.zip`；解压后可用 `latex-extracted/bare_jrnl_new_sample4.tex` |
| `ieee-access/` | IEEE Access 专用模板 | `Access_Word_Template.docx` | `Access_LaTeX_template.zip`；解压后可用 `latex-extracted/ACCESS_latex_template_20240429/access.tex` |
| `ieee-journal-of-microwaves/` | IEEE Journal of Microwaves 专用模板 | `JMW_Word_Template.docx` | `JMW_LaTex_Template.zip`；解压后可用 `latex-extracted/IEEE_JMW_LaTex_Template_Oct18_2021/JMW_template.tex` |

## 使用规则

1. 用户要求 IEEE 模板、IEEE 风格格式化、Word 参考模板或 LaTeX 模板时，先查本技能资源。
2. 目标是 IEEE Transactions 类期刊且未指定专用模板时，优先用 `transactions-journals-letters/`。
3. 目标是 IEEE Access 或 IEEE Journal of Microwaves 时，用对应专用目录。
4. 如果目标期刊、文章类型或模板年份不确定，先用 IEEE Template Selector 官方 API 或网页核对，不要只凭技能内旧资源判断最新状态。
5. 如果从官方重新下载了新模板，更新本技能资源，并在目标论文目录保留一份使用记录，便于追溯该论文实际用过的模板版本。

## 官方来源

- IEEE Author Center: https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/tools-for-ieee-authors/ieee-article-templates/
- IEEE Template Selector: https://template-selector.ieee.org/

下载接口格式：

```text
https://template-selector.ieee.org/api/ieee-template-selector/template/<association-id>/download
```

本次已核验的 association id：

- `54`: IEEE Transactions on Terahertz Science and Technology / Word
- `292`: IEEE Transactions on Terahertz Science and Technology / LaTeX
- `447`: IEEE Access / Word
- `541`: IEEE Access / LaTeX
- `544`: IEEE Journal of Microwaves / Word
- `545`: IEEE Journal of Microwaves / LaTeX
