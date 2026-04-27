---
name: paper-reading
description: 论文 PDF 获取、下载清单和索引维护，以及单篇英文论文中文总结的一体流程。Use when 用户要按题目、DOI、作者主页、出版社页面、论文列表或上游检索结果下载论文 PDF，或要把单篇论文整理成中文总结、文献笔记、论文卡片；若用户只是在找方向或筛代表作，先用 `research-lookup`，若用户已经给出单篇论文线索并要求总结，先定位或下载 PDF，再生成 `paper-summaries` 下的中文 `.md` 文件。
---

# 论文下载与单篇总结

## 作用

这份 skill 把“找到论文 PDF”和“读完单篇论文后生成中文总结”合成一个连续流程。

默认目标是先确认版本和访问状态，再保存 PDF、维护索引，最后在需要时生成一份客观、可归档的中文 Markdown 总结。

## 任务分流

- 用户还在问“某个领域有哪些论文”“近几年代表作是什么”“帮我筛方向”时，先走 `research-lookup` 或其他检索能力。
- 用户已经给出题目、DOI、URL、作者主页、出版社页面、论文列表或上游检索结果时，直接进入下载和索引流程。
- 用户要求总结单篇论文，但只给了 DOI、题名或 URL 时，先定位或下载 PDF，再做总结。
- 用户要求“读这一篇”“整理这篇”“做文献卡片”时，只处理单篇论文，不扩成多篇综述。

## 默认产物

- 下载好的 PDF 文件。
- `download_list.md`：下载前后的清单，记录每篇论文的候选版本、访问状态、下载状态和失败原因。
- `paper_index.md`：最终索引，记录标题、DOI、年份、发表源、版本、文件名、来源 URL、下载日期和备注。
- `paper-summaries/<year>-<journal>-<title-short>.md`：单篇论文中文总结。

如果用户已有固定论文目录，默认把“下载、规范命名、索引更新、必要时总结”视为同一个完整动作。

## 输入范围

下面这些输入都可以作为论文线索：

- 本地 PDF
- DOI
- arXiv ID、PubMed ID 或论文 URL
- 论文题目、作者主页、出版社页面
- 已经提取出的论文全文或节选
- 用户手写的论文列表
- `research-lookup` 返回的标题、摘要、链接或引用信息

如果一篇明确论文都识别不出来，只问用户一个问题：这次要下载或总结的是哪几篇？

## 下载规则

1. 先补元数据，再下载；至少补标题、DOI、年份、发表源、版本状态和访问状态。
2. 版本优先于来源。已正式发表的论文优先获取正式发表版本；正式版暂时无法合法获取时，才下载预印本，并标为 `temporary_preprint`。
3. 来源不是第一判断标准。只要是公开或已授权可访问来源，且 PDF 对应最终发表形态，就可以按正式版处理，不局限于出版社官网。
4. 不绕过访问控制。对只支持购买、申请全文或用户没有权限的条目，记录为 `request-only` 或 `unresolved`，不要假装已经下载。
5. ResearchGate 更适合当线索来源，不把它当默认主下载源。
6. 不默认做截图、首图提取、文本抽取或 BibTeX，除非用户另外提出。

## 优先用 paper-search-mcp

优先使用当前会话里的 `paper-search-mcp` 工具：

- `search_papers`：统一检索、去重和补元数据。默认先用全来源；结果噪声过多时再收窄来源。
- `search_unpaywall`：已知 DOI 时单独查开放获取链接和正式版可得性。
- `download_with_fallback`：用于公开来源下载 PDF；调用时写清 `source`、`paper_id`、`doi`、`title` 和 `save_path`。
- `download_with_authorization`：正式版需要机构权限、前端按钮或登录会话时优先用它，不回退到手工猜链接。
- `list_authorization_checkpoints`：批量下载中断或等待用户授权时，先列出未完成的授权记录。
- `retry_authorized_download`：用户完成扫码、验证码或学校授权后，沿着原来的授权记录继续下载，不另建重复记录。

把工具返回的信息整理成统一字段：`paper_id`、`title`、`authors`、`doi`、`published_date`、`source`、`url`、`pdf_url`、`extra`。不要把某个平台的原始字段直接写进最终索引。

如果当前会话还未加载 `paper-search-mcp` 工具，先提醒用户新开 Codex 窗口或检查 `C:\Users\SanAn\.codex\config.toml` 的 MCP 注册；不要因此直接改同步副本。

## 下载清单

`download_list.md` 是下载前后的工作清单。每篇论文尽量补这些字段：

- `title`
- `authors`
- `year`
- `venue_or_source`
- `doi`
- `landing_page_url`
- `pdf_url`
- `source_hint`
- `publication_status`
- `preferred_version`
- `access_status`
- `download_status`
- `saved_path`
- `notes`

不要为了填满字段而猜。无法获取的信息写 `unknown`、`unresolved` 或简短说明。

建议表格：

| title | authors | doi | year | venue_or_source | publication_status | preferred_version | official_candidate | preprint_candidate | access_status | download_status | saved_path | notes |
|---|---|---|---:|---|---|---|---|---|---|---|---|---|

## 版本判定

1. 先确认是否已有正式发表版本。有 DOI，且 Crossref、OpenAlex、Semantic Scholar、Unpaywall、出版社页面或正式期刊/会议页面能对应到同一标题时，标为 `published`。
2. 对 `published` 条目，先下载正式发表版本。优先 DOI/出版社正式页、出版社开放 PDF、PMC/Europe PMC 正式全文、Unpaywall 指向的 published PDF。
3. 作者主页、机构库、课程页、实验室页面或 Google Scholar 指到的公开 PDF，只要能确认是最终发表形态，也可作为正式版来源，并在索引备注里写清来源。
4. 如果公开和机构授权渠道都无法获取最终发表版，再找预印本。文件名和索引都标 `temporary_preprint`，备注写清“正式版存在，但本次未能合法获取正式 PDF”。
5. 如果只能确认预印本、没有正式发表线索，标为 `preprint`，不要写成正式版。
6. 如果同一论文同时出现多个候选，优先保留 DOI 和正式来源；预印本的 ID、URL 和下载结果作为 `alternate_version` 记录。

### 最终发表形态怎么判断

- 标题、作者、DOI 能和正式论文对应上。
- 版面是期刊或会议正式排版，而不是 arXiv、投稿稿、接收稿或网页打印稿。
- 卷、期、页码、发表年份、期刊名或会议信息齐全。
- 文件不是补充材料、勘误、封面页、摘要页或 HTML 网页另存。

页面上写 `FULL ACCESS`、`Full Text` 或能阅读全文，只能说明网页正文可读；这不等于已经获取到正式 PDF。仍要点击或请求 PDF 入口，并确认下载文件开头是 `%PDF-`。

## 文件命名

下载完成并确认文件头是 `%PDF-` 后，默认把 PDF 统一命名为：

`年份-期刊或会议全称-题名.pdf`

命名细则：

- `年份` 用正式发表年份；只确认预印本时用预印本年份，并在索引中标明版本。
- `期刊或会议全称` 优先取 Crossref、OpenAlex、Semantic Scholar、Unpaywall、出版社页面或正式 PDF 元数据里的完整来源名。
- `题名` 保留英文原标题的主要单词和大小写；清理 Windows 文件名不适合的字符，如 `\ / : * ? " < > |`。
- 同一论文存在多个版本时，在题名后、扩展名前追加最小版本后缀，如 `(official)`、`(accepted-manuscript)`、`(temporary-preprint)` 或 `(arXiv)`。
- 遇到超长题名时，保留年份和期刊或会议全称，题名只做可读截断，并在索引中保存完整题名和 DOI。
- 重命名后同步更新 `download_list.md`、`paper_index.md`，以及授权记录里的下载路径。

## 浏览器协作

遇到下面这些情况，默认切到浏览器路线，而不是盲目重试命令行：

- `Security check required`
- Cloudflare 或行为风控
- `Download` 按钮不是直链，而是前端事件
- PDF 依赖浏览器会话、Cookie、短时令牌或在线阅读器
- 机构登录要走统一身份认证
- 直链、命令行或普通网页请求返回 403、HTML 页面、登录页，但用户在浏览器里能看到下载按钮或阅读全文

授权协作时只做入口点击和状态观察，不替用户输入账号密码，不绕过登录、订阅或机构权限。若本机已经保存学校登录态，优先复用当前浏览器会话；若工具另开了空白浏览器导致没有登录态，应改用已登录浏览器代理，或请用户在该浏览器里完成授权。

用户完成授权后，不要从头重试整篇论文；优先用 `retry_authorized_download` 继续原来的授权记录。

下载完成后，先检查文件头是不是 `%PDF-`。如果返回的是 `text/html`、`<!DOCTYPE html>`、学校登录页、验证码页或出版社外层网页，就不能当成论文 PDF 保存。

站点经验按需读取 [references/publisher-download-playbook.md](references/publisher-download-playbook.md)。

## 单篇总结规则

默认把总结文件放在当前工作区根目录下：

`<workspace-root>\paper-summaries\`

工作区根目录按下面顺序判断：

1. 当前任务正在处理的工作区根目录。
2. 当前 Git 仓库根目录。
3. 当前工作目录。

默认文件名：

`<year>-<journal>-<title-short>.md`

处理规则：

- `year` 优先取正式发表年份；拿不到就用 `unknown-year`。
- `journal` 优先取期刊名、会议名或论文来源的简短写法；拿不到就用 `unknown-journal`。
- `title-short` 用论文标题的简短版本，并清理成 Windows 可用文件名。
- 如果用户明确指定文件名，按用户指定。

## 内容提取规则

1. 优先从论文正文、首页、摘要、作者信息和图表中提取事实。
2. 读取 PDF 时先用内置 PDF 读取能力。失败后用 Python 库兜底，优先尝试 `pdfplumber`、`PyPDF2`、`fitz`。Windows 控制台如果出现 GBK 编码错误，改用 UTF-8 输出，例如设置 `PYTHONIOENCODING=utf-8`。
3. 不要一开始把全文全部塞进上下文。先提取首页、摘要、作者单位、DOI/ISSN、图表标题、结论和局限附近内容；需要补证据时再扩大范围。
4. 基础元信息优先从论文原文提取，顺序为：题目、作者、第一作者、通讯作者、单位、期刊名、卷期页码、发表/在线发表时间、DOI、ISSN。
5. DOI 页面或 Crossref 只能辅助校验，不能覆盖论文正文中已经明确的信息。
6. `中科院期刊分区`、`影响因子` 不要凭记忆填写，也不要只凭搜索引擎摘要填写。

## LetPub 查询

默认必须用 `web-access` skill 进入 LetPub 期刊查询页做站内检索，速度慢可以接受，稳定和可核验优先：

`https://www.letpub.com.cn/index.php?page=journalapp`

查询顺序：

1. 先加载 `web-access` skill，并按其要求检查 CDP/浏览器代理可用性。
2. 打开 LetPub `journalapp` 页面。
3. 优先在页面表单的 ISSN 字段中填写完整 ISSN，例如 `2095-8099`，提交查询。
4. 如果没有 ISSN、ISSN 无匹配，或结果与论文期刊明显不一致，再用期刊名精确查询。
5. 只有页面返回类似“搜索条件匹配：N条记录”且结果表中出现可核验字段时，才算确认。

优先记录：

- ISSN
- LetPub 页面展示的期刊名，包括别名或缩写
- 影响因子
- 最新分区信息，优先写 LetPub 页面显示的分区口径
- 大类学科和小类学科
- SCI/SCIE/SSCI 等收录状态

LetPub 失败状态要写清楚原因，例如：

- `待查询（LetPub 页面无法打开）`
- `待查询（LetPub 站内检索无精确匹配）`
- `待查询（LetPub 结果与论文期刊信息冲突）`
- `待查询（疑似登录墙或访问拦截，未能读取结果表）`

如果当前论文没有正式期刊来源，`中科院期刊分区` 和 `影响因子` 写 `不适用` 或 `待查询`，不要硬查、不要猜。

## 写作规则

- 全文输出中文。
- 论文标题、期刊名、作者名、DOI、URL 可保留原文。
- `关键信息` 使用 Markdown 表格。
- 正文主体使用 `##` 作为大块分组标题。
- 每个具体点使用 `###`，不要继续写成一长串横杠列表。
- 不写主观评价，不做推荐结论。
- 不做多轮“概述 + 详细总结”重复展开，只保留一个展开版本。
- 引用原文时，只摘最关键的少量原句或原始结果，不长段抄录。
- 无法确认的信息写 `未说明`、`待查询` 或 `不适用`，不要编造。

## 总结模板

```markdown
# 论文中文总结

## 关键信息
| 项目 | 内容 |
|---|---|
| 中科院期刊分区 |  |
| 影响因子 |  |
| 期刊名 |  |
| 发表时间 |  |
| 第一作者 |  |
| 通讯作者 |  |
| 单位 |  |
| 题目 |  |
| DOI / URL |  |

## 研究问题

### 研究对象

### 核心问题

### 研究背景

## 研究方法

### 研究思路

### 具体方法

### 关键步骤

### 使用工具

### 研究材料

## 研究对象与验证方式

### 数据来源

### 对比设置

### 判断标准

### 验证过程

## 主要结果

### 主要发现

### 关键数据

### 结果表现

### 图表信息

## 作者结论

### 结果解释

### 最终结论

## 论文中提到的局限

### 已说明的限制

### 适用范围

### 未解决问题

## 术语与专名

### 术语对照 1

### 术语对照 2

## 原文关键信息摘录

### 关键表述 1

### 关键表述 2
```

## 索引模板

`paper_index.md` 建议列：

| title | doi | year | venue_or_source | version | access_status | file | source_url | retrieved_at | notes |
|---|---|---:|---|---|---|---|---|---|---|

版本值统一用：`official`、`accepted_manuscript`、`preprint`、`temporary_preprint`、`unresolved`。

发表状态统一用：`published`、`preprint_only`、`unknown`。

访问状态统一用：`open`、`institutional`、`request-only`、`unresolved`。

下载状态统一用：`downloaded`、`pending`、`failed`、`skipped`。

## 什么时候不要用

- 用户要做多篇文献综述，优先走文献调研或深搜流程。
- 用户要写投稿文章、引言综述、申报书材料，优先走 `sci-writing` 或 `project-writing`。
- 用户要批判性评审、同行评议意见或审稿式打分，优先走 `paper-review`。
- 用户只是问某个领域有哪些论文，还没有明确论文线索，优先先检索。

## 相关工具与技能

- 上游查找：`research-lookup`
- 论文检索和下载后端：`paper-search-mcp`
- LetPub 和网页访问：`web-access`
- 浏览器协作：`browser-use` 或当前可用的浏览器工具
- PDF 后处理：`pdf`
- 学术写作总控：`sci-writing`
- 文稿审查：`paper-review`
- 本地 skill 维护：`skill-creator`

## 维护

- 新出现的站点经验，优先记录到 [references/publisher-download-playbook.md](references/publisher-download-playbook.md)，正文只保留稳定流程和边界。
- 如果以后调整总结模板，优先只改 `## 总结模板`。
- 如果改变文件命名习惯或目录规则，再改对应规则，不要把一次性项目目录写死。
