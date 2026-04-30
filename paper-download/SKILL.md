---
name: paper-download
description: 获取论文 PDF，并维护统一的 `paper_index.md`。Use when 用户给出题名、DOI、论文 URL、出版社页、作者主页、论文列表或 research-lookup 结果，要求下载正式版 PDF、判断正式版/预印本、继续机构授权下载，或为 SCI 润色和术语核查提供正式论文原文证据。总结已有 PDF 时用 `paper-summary`。
---

# 论文 PDF 下载

## 目标

只做一件事：把论文 PDF 找到、下对、命名好、登记清楚。

基本顺序：先确认论文信息和版本，再下载合法可访问的 PDF，最后校验文件并更新索引。

## 什么时候用

- 用户还在问“有哪些论文”“哪些方向重要”“帮我筛代表作”时，先走 `research-lookup`。
- 用户已经给出题名、DOI、URL、作者主页、出版社页面、论文列表或检索结果时，进入下载流程。
- 用户要“下载并总结”时，先用本技能获取 PDF，再用 `paper-summary` 总结。
- 用户给的是本地 PDF，并且要读懂或总结时，转 `paper-summary`。

## 输出

- 下载好的 PDF 文件。
- `paper_index.md`：统一索引。未下载、下载中、下载失败、已下载都写在这里。

## 能接收什么

- DOI
- arXiv ID、PubMed ID 或论文 URL
- 论文题目、作者主页、出版社页面
- 用户手写论文列表
- `research-lookup` 返回的标题、摘要、链接或引用信息

如果一篇明确论文都识别不出来，只问一个问题：这次要下载的是哪几篇？

## 怎么下载

1. 先补元数据，再下载；至少补标题、DOI、年份、发表源、版本状态和访问状态。
2. 版本优先于来源。已正式发表的论文优先获取正式发表版本；正式版暂时无法合法获取时，才下载预印本，并标为 `temporary_preprint`。
3. 来源不是第一判断标准。只要是公开或已授权可访问来源，且 PDF 对应最终发表形态，就可以按正式版处理，不局限于出版社官网。
4. 不绕过访问控制。对只支持购买、申请全文或用户没有权限的条目，记录为 `request-only` 或 `unresolved`，不要假装已经下载。
5. ResearchGate 更适合当线索来源，不把它当默认主下载源。
6. 不默认做截图、首图提取、文本抽取、BibTeX 或中文总结，除非用户另外提出。

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

## 论文索引

`paper_index.md` 记录论文信息、版本判断和下载状态。每篇论文尽量补这些字段：

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

## 怎么判断版本

1. 先确认是否已有正式发表版本。有 DOI，且 Crossref、OpenAlex、Semantic Scholar、Unpaywall、出版社页面或正式期刊/会议页面能对应到同一标题时，标为 `published`。
2. 对 `published` 条目，先下载正式发表版本。优先 DOI/出版社正式页、出版社开放 PDF、PMC/Europe PMC 正式全文、Unpaywall 指向的 published PDF。
3. 作者主页、机构库、课程页、实验室页面或 Google Scholar 指到的公开 PDF，只要能确认是最终发表形态，也可作为正式版来源，并在索引备注里写清来源。
4. 如果公开和机构授权渠道都无法获取最终发表版，再找预印本。文件名和索引都标 `temporary_preprint`，备注写清“正式版存在，但本次未能合法获取正式 PDF”。
5. 如果只能确认预印本、没有正式发表线索，标为 `preprint`，不要写成正式版。
6. 如果同一论文同时出现多个候选，优先保留 DOI 和正式来源；预印本的 ID、URL 和下载结果作为 `alternate_version` 记录。

## 怎么判断是不是正式版

- 标题、作者、DOI 能和正式论文对应上。
- 版面是期刊或会议正式排版，而不是 arXiv、投稿稿、接收稿或网页打印稿。
- 卷、期、页码、发表年份、期刊名或会议信息齐全。
- 文件不是补充材料、勘误、封面页、摘要页或 HTML 网页另存。

页面上写 `FULL ACCESS`、`Full Text` 或能阅读全文，只能说明网页正文可读；这不等于已经获取到正式 PDF。仍要点击或请求 PDF 入口，并确认下载文件开头是 `%PDF-`。

## 文件命名

下载完成并确认文件头是 `%PDF-` 后，默认把 PDF 统一命名为：

`年份-期刊名-标题名.pdf`

命名细则：

- `年份` 用正式发表年份；只确认预印本时用预印本年份，并在索引中标明版本。
- `期刊名` 优先用正式论文里的期刊全名；会议论文用会议名，预印本用 `arXiv` 或对应预印本平台名。
- `标题名` 保留英文原标题的主要单词和大小写；清理 Windows 文件名不适合的字符，如 `\ / : * ? " < > |`。
- 同一论文存在多个版本时，在标题名后、扩展名前追加最小版本后缀，如 `(official)`、`(accepted-manuscript)`、`(temporary-preprint)` 或 `(arXiv)`。
- 遇到超长标题时，保留年份和期刊名，标题名只做可读截断，并在索引中保存完整标题和 DOI。
- 重命名后同步更新 `paper_index.md`，以及授权记录里的下载路径。

## 什么时候用浏览器

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

固定状态值：

- `version`：`official`、`accepted_manuscript`、`preprint`、`temporary_preprint`、`unresolved`
- `publication_status`：`published`、`preprint_only`、`unknown`
- `access_status`：`open`、`institutional`、`request-only`、`unresolved`
- `download_status`：`downloaded`、`pending`、`failed`、`skipped`

## 边界

- 多篇文献综述、代表作筛选：先用 `research-lookup`。
- 投稿文章、引言综述、申报书材料：转 `sci-writing` 或 `project-writing`。
- 本地 PDF 总结、文献卡片、术语摘录：转 `paper-summary`。

## 会用到的工具

- 上游查找：`research-lookup`
- 论文检索和下载后端：`paper-search-mcp`
- 网页访问和动态页面：`web-access`
- 浏览器协作：`browser-use` 或当前可用的浏览器工具
- PDF 后处理：`pdf`
- 本地 PDF 总结：`paper-summary`
- SCI 论文精修和术语核查：`sci-paper-edit`

## 以后怎么维护

- 新出现的站点经验，优先记录到 [references/publisher-download-playbook.md](references/publisher-download-playbook.md)，正文只保留稳定流程和边界。
- 如果改变文件命名习惯或目录规则，再改对应规则，不要把一次性项目目录写死。
