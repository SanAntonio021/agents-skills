---
name: lunwen-xiazai
description: 按题目、DOI、作者主页、出版社页面、上游搜索结果或论文列表下载论文 PDF，优先调用 paper-search-mcp，并整理 download_list.md 和 paper_index.md。Use when 用户要下载单篇或批量论文、把 research-lookup 等上游结果继续转成 PDF、从 DOI 或作者主页找全文，或需要配合浏览器和机构登录完成访问；prefer 正式发表版本 first，正式版暂时拿不到时允许先下预印本并标成临时版本。
---

# 论文下载

## 作用

这份 skill 负责把论文题目、DOI、作者主页、出版社页面、上游搜索结果或结果列表，稳定转成可落盘的 PDF 下载结果，并把状态分清楚：

- 已公开可直接获取
- 需要机构权限
- 目前无法直接获取

## 适用场景

- 下载单篇或多篇论文 PDF
- 接着 `research-lookup` 或其他检索结果，把零散搜索结果整理成可下载清单
- 从作者主页、ResearchGate、Google Scholar、DOI 或出版社页面整理下载入口
- 用户愿意在必要时配合浏览器验证、验证码或机构登录

## 核心规则

- 优先判断版本：已正式发表的论文先拿正式发表版本；正式版暂时拿不到，才下载预印本，并标为 `temporary_preprint`。
- 优先调用 `paper-search-mcp`：先用 MCP 补元数据、分版本、下载 PDF；MCP 不足时再用网页或浏览器补线索。
- 来源不是第一判断标准；版本对不对才是第一判断标准。仍然不要绕过访问控制。
- ResearchGate 更适合当线索来源，不把它当默认主下载源。
- 先补元数据，再下载；至少要补标题、DOI、年份、发表源、版本状态和访问状态。
- 先拿公开副本，再考虑机构权限补齐受限条目。
- 不默认做截图、首图提取、文本抽取或 BibTeX，除非用户另外提出。
- 不使用盗版论文站点；调用 `download_with_fallback` 时默认显式传 `use_scihub: false`。

## 上游衔接

如果用户还在问“某个领域有哪些论文”“帮我筛方向”“找近几年代表作”，先用 `research-lookup` 或其他检索能力完成查找。

如果当前对话里已经有论文线索，就直接进入本 skill，不要求上游一定给出标准清单。可接受的线索包括：

- 题目、DOI、arXiv ID、PubMed ID、出版社页面或作者主页
- `research-lookup` 返回的论文标题、摘要、链接或引用信息
- 用户手写的论文列表
- 某个网页里能识别出的论文条目

进入下载前，先把这些线索整理成 `download_list.md`。如果一篇明确论文都识别不出来，再只问用户一个问题：这次要下载的是哪几篇？

## MCP 优先路线

优先使用当前会话里由 `paper-search-mcp` 暴露的 MCP 工具：

- `search_papers`：统一检索、去重和补元数据。默认先用全来源；如果结果太杂，再按任务收窄到 `crossref,openalex,semantic,unpaywall,pmc,core,europepmc,arxiv,biorxiv,medrxiv,hal,zenodo,doaj,base`。
- `search_unpaywall`：已知 DOI 时单独查开放获取链接和正式版可得性。
- `download_with_fallback`：下载公开 PDF；必须传入 `source`、`paper_id`、`doi`、`title`、`save_path`，并显式设置 `use_scihub: false`。
- `download_with_authorization`：正式版需要机构权限、前端按钮或登录会话时优先用它，不要退回手工猜链接。
- `list_authorization_checkpoints`：批量下载中断或等待用户授权时，先列出未完成 checkpoint，再决定继续哪几篇。
- `retry_authorized_download`：用户完成扫码、验证码或学校授权后，用 checkpoint 继续原下载，不重新建一条混乱链路。

把 MCP 返回结果统一抽成这些字段：`paper_id`、`title`、`authors`、`doi`、`published_date`、`source`、`url`、`pdf_url`、`extra`。不要把某个平台的原始字段直接写进最终索引。

如果当前会话还没有暴露 `paper-search-mcp` 工具，先提醒用户新开 Codex 窗口或检查 `C:\Users\SanAn\.codex\config.toml` 的 MCP 注册；不要因此直接改同步副本或回到盗版站路线。

## 临时清单

`download_list.md` 是下载前后的工作清单。字段参考单篇论文总结的“关键信息”思路，但只保留下载需要的信息。

每篇论文尽量补这些字段：

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

不要为了填满字段而猜。拿不到的信息写 `unknown`、`unresolved` 或简短说明。

## 版本判定

按下面顺序判断每篇论文要拿哪个版本：

1. 先确认是否已有正式发表版本。
   有 DOI，且 Crossref、OpenAlex、Semantic Scholar、Unpaywall、出版社页面或正式期刊/会议页面能对应到同一标题时，标为 `published`。
2. 对 `published` 条目，先下载正式发表版本。
   优先 DOI/出版社正式页、出版社开放 PDF、PMC/Europe PMC 正式全文、Unpaywall 指向的 published PDF。
3. 如果正式版暂时拿不到，再找预印本。
   arXiv、bioRxiv、medRxiv、SSRN 等只能作为兜底；文件名和索引都标 `temporary_preprint`，备注写清楚“正式版存在，但本次未能取得正式 PDF”。
4. 如果暂时只能确认预印本、没有正式发表线索，标为 `preprint`，不要写成正式版。
5. 如果同一论文同时出现多个候选，优先保留 DOI 和正式来源；预印本的 ID、URL 和下载结果作为 `alternate_version` 记录。

## 流程

1. 先整理论文清单。
   从当前对话、上游检索结果、作者主页、题目列表、DOI 页面或出版社页面抽出标题和基础线索。
2. 用 `paper-search-mcp` 补元数据。
   对每个题目或 DOI 调 `search_papers`；已知 DOI 时再调 `search_unpaywall`。尽量补 DOI、期刊或会议名、年份、出版方、版本状态和开放状态。
3. 生成统一下载清单。
   下载前先在目标目录建立或更新 `download_list.md`，把每篇论文的候选正式版、候选预印本、计划动作和备注写清楚。
4. 做访问分流。
   把每篇论文标成 `open`、`institutional`、`request-only` 或 `unresolved`。
5. 先尝试正式版公开下载。
   对 `published` 条目，先用 DOI、正式来源和 `download_with_fallback(..., use_scihub: false)` 下载；失败后再查正式页面或浏览器按钮。
6. 正式版拿不到时再下载预印本。
   只有在正式版失败且预印本公开可得时才下载预印本，并在文件名、`download_list.md` 和 `paper_index.md` 中标 `temporary_preprint`。
7. 遇到风控、前端按钮或登录墙时，先用 `download_with_authorization`。
   如果返回等待授权，记录 checkpoint，并在 `download_list.md` 里把状态写成 `pending_authorization` 或 `institutional`。
8. 对明确需要机构权限的条目，优先复用本机已经登录的浏览器状态。
   可以协助点击出版社页里的 `Institutional Sign In`、学校入口、`登录`、`PDF` 等入口；遇到账号、密码、扫码、验证码或二次确认时，停下来让用户本人操作。
9. 下载后立刻做最小校验。
   先看文件头是不是 `%PDF-`；文件异常偏小时，优先怀疑下载到的是 HTML 包装页、验证码页或确认页。对 IEEE Xplore 这类 PDF wrapper 页面，还要确认抓到的是 iframe/embed/object 里的真正 PDF，而不是外层 HTML。
10. 统一命名并更新索引。
    默认用“论文标题.pdf”；同一论文存在多个版本时追加最小后缀，如 `(official)`、`(accepted-manuscript)`、`(temporary-preprint)` 或 `(arXiv)`。
    如果用户已有固定目录，默认同步更新该目录下的 `paper_index.md`。

## 来源优先级

建议按下面顺序找：

1. `paper-search-mcp` 的 DOI、Crossref、OpenAlex、Semantic Scholar、Unpaywall 元数据
2. DOI 对应的出版社正式页面和出版社开放 PDF
3. PubMed Central、Europe PMC、机构知识库、作者主页公开副本
4. CORE、HAL、Zenodo、DOAJ、BASE 等开放仓储
5. arXiv、bioRxiv、medRxiv、SSRN 等预印本源
6. ResearchGate 等学术社交站点上的公开全文入口
7. 机构登录后的正式出版社 PDF

## 浏览器协作

遇到下面这些情况，默认切到浏览器路线，而不是盲目重试命令行：

- `Security check required`
- Cloudflare 或行为风控
- `Download` 按钮不是直链，而是前端事件
- PDF 依赖会话、Cookie、短时令牌或前端 viewer
- 机构登录要走统一身份认证

这类任务优先配合 `browser-use` 或当前可用的浏览器工具。

授权协作时只做入口点击和状态观察，不替用户输入账号密码，不绕过登录、订阅或机构权限。若本机已经保存学校登录态，优先使用 MCP 或浏览器工具复用当前浏览器会话；若 MCP 另开了空白浏览器导致没有登录态，应改用已登录浏览器代理或请用户在该浏览器里完成授权。

用户完成授权后，不要从头重试整篇论文；优先用 `retry_authorized_download` 继续 checkpoint。这样批量下载时可以把所有等待授权的条目排队处理，减少漏下和错下。

## 交付

默认交付三类：

- 下载好的 PDF 文件
- `download_list.md`：下载前后的统一清单，记录每篇论文的正式版候选、预印本候选、计划动作、下载状态和失败原因
- `paper_index.md`：最终索引，记录标题、DOI、年份、发表源、版本、访问状态、文件名、来源 URL、下载日期和备注

如果用户已有固定论文目录，默认把“下载 + 规范命名 + 索引更新”视为一个完整动作。

`download_list.md` 建议列：

| title | authors | doi | year | venue_or_source | publication_status | preferred_version | official_candidate | preprint_candidate | access_status | download_status | saved_path | notes |
|---|---|---|---:|---|---|---|---|---|---|---|---|---|

`paper_index.md` 建议列：

| title | doi | year | venue_or_source | version | access_status | file | source_url | retrieved_at | notes |
|---|---|---:|---|---|---|---|---|---|---|

版本值统一用：`official`、`accepted_manuscript`、`preprint`、`temporary_preprint`、`unresolved`。发表状态统一用：`published`、`preprint_only`、`unknown`。访问状态统一用：`open`、`institutional`、`request-only`、`unresolved`。下载状态统一用：`downloaded`、`pending`、`failed`、`skipped`。

## 边界

- 不绕过访问控制，不使用盗版论文站点。
- 不把 `download_with_fallback` 的默认 Sci-Hub 回退当成默认能力；除非用户明确要求并自行承担合法性，否则始终传 `use_scihub: false`。
- 对只支持 `Request full-text`、只支持付费购买、且用户没有合法访问权限的条目，要明确说明目前不能直接下载。
- 不直接修改 `paper-search-mcp`、`research-lookup` 这类上游来源；需要沉淀下载规则时，优先放进本 skill 的 `references/`。

## 相关文件

- 出版社下载经验：[references/publisher-download-playbook.md](references/publisher-download-playbook.md)

## 相关工具与技能

- 上游查找：`research-lookup`
- 论文检索和下载后端：`paper-search-mcp`
- 单篇总结：`danpian-lunwen-zongjie`
- 浏览器协作：`browser-use` 或当前可用的浏览器工具
- PDF 后处理：`pdf`
- 文献归档：`zotero`
- 本地 skill 维护：`skill-creator`

## 维护

- 新出现的站点经验，优先沉淀到 [references/publisher-download-playbook.md](references/publisher-download-playbook.md)，正文只保留稳定流程和边界。
- 如果以后长期要处理某一出版方的特殊流程，再补更具体的站点分流规则，不要把正文堆成站点清单。
