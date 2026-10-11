# IEEE 官方模板技能资源

本文件说明 `ieee-manuscript-edit` 技能内可复用的 IEEE 官方 Word/LaTeX 模板资源。技能只分发可直接使用的模板文件；完整官方下载包保存在本机来源快照中，不参与 CC Switch 更新。

## 资源位置

技能源码内位置：

```text
D:\BaiduSyncdisk\.agents\skills\ieee-manuscript-edit\assets\ieee-official-templates
```

通用写法：

```text
<skill-root>\assets\ieee-official-templates
```

## 已分发模板

| 目录 | 用途 | Word | LaTeX |
|---|---|---|---|
| `transactions-journals-letters/` | IEEE Transactions/Journals/Letters 通用模板；IEEE Transactions on Terahertz Science and Technology 与 IEEE Transactions on Microwave Theory and Techniques 当前都指向这组模板 | `word-extracted/ieee-transactions-template.docx` | `latex-extracted/bare_jrnl_new_sample4.tex` 及同目录依赖 |
| `ieee-access/` | IEEE Access 专用模板 | `Access_Word_Template.docx` | `latex-extracted/ACCESS_latex_template_20240429/access.tex` 及同目录依赖 |
| `ieee-journal-of-microwaves/` | IEEE Journal of Microwaves 专用模板 | `JMW_Word_Template.docx` | `latex-extracted/IEEE_JMW_LaTex_Template_Oct18_2021/JMW_template.tex` 及同目录依赖 |

## 完整原包

本机完整快照放在：

```text
D:\BaiduSyncdisk\.agents\downloads\ieee-official-templates\<snapshot-date>
```

每个快照包含官方下载 ZIP、解压内容、来源说明和逐文件 SHA-256。该目录只用于来源追溯与恢复，技能运行不得依赖它。

## 使用规则

1. 用户要求 IEEE 模板、IEEE 风格格式化、Word 参考模板或 LaTeX 模板时，先查本技能资源。
2. 目标是 IEEE Transactions 类期刊且未指定专用模板时，优先用 `transactions-journals-letters/`。
3. 目标是 IEEE Access 或 IEEE Journal of Microwaves 时，用对应专用目录。
4. 如果目标期刊、文章类型或模板年份不确定，先用 IEEE Template Selector 官方 API 或网页核对，不要只凭技能内旧资源判断最新状态。
5. 如果从官方重新下载了新模板，先创建新的本机日期快照并核对 SHA-256，再把可直接使用的 Word/LaTeX 文件更新到技能资源；下载 ZIP、生成 PDF、`__MACOSX`、`.DS_Store` 和 `._*` 不进入公开技能仓库。
6. 在目标论文目录保留实际采用的模板版本和来源记录，便于追溯。

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

## TVT 作者指南核验（2026-09-14）

IEEE Transactions on Vehicular Technology（TVT）官方作者说明：
https://vtsociety.org/publication/ieee-transactions-vehicular-technology/guidelines-authors/instructions

- 审稿稿件采用双栏，字体不小于 10 pt，标题通栏。现有 IEEEtran V1.8b（2015/08/26）可用 `journal,10pt` 实现该基础版式。
- Regular Paper 初投最多 14 页，修改稿／终稿最多 16 页；Correspondence 分别为 5 页／6 页，参考文献和作者简介计入。导师审阅稿若暂不限制篇幅，应明确区别于正式投稿合规稿。
- 官方页面说明 AI 可用于修改作者已有文本，并要求在致谢披露相关使用；投稿前由作者核对适用要求及最终文本。
- 核验边界：已读取 TVT 官方说明并核对缓存类文件版本；官方页面提到建议 style/sample，但未取得可验证的 TVT 专用下载关联 ID 或最新 ZIP 哈希。因此只称“IEEEtran 通用期刊模板配合 TVT 作者要求”，不称“已下载最新 TVT 专用模板”。本次不重复下载或复制模板资产。
- 页数及投稿要求可能变化，正式提交时重新读取上述官方页面。
