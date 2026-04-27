---
name: paper-download
description: 按题目、DOI、作者主页、出版社页面、上游搜索结果或论文列表下载论文 PDF，优先调用 paper-search-mcp，并整理 download_list.md 和 paper_index.md。Use when 用户要下载单篇或批量论文、把 research-lookup 等上游结果继续转成 PDF、从 DOI 或作者主页找全文，或需要配合浏览器和机构登录完成访问；prefer 正式发表版本 first，正式版暂时无法获取时允许先下预印本并标成临时版本。
---

# 论文下载

## 作用

这份 skill 负责把论文题目、DOI、作者主页、出版社页面、上游搜索结果或结果列表转成本地 PDF 文件，并区分访问状态：

- 已公开可直接获取
- 需要机构权限
- 目前无法直接获取

## 适用场景

- 下载单篇或多篇论文 PDF
- 接着 `research-lookup` 或其他检索结果，把零散搜索结果整理成可下载清单
- 从作者主页、ResearchGate、Google Scholar、DOI 或出版社页面整理下载入口
- 用户愿意在必要时配合浏览器验证、验证码或机构登录

## 核心规则

- 优先判断版本：已正式发表的论文先获取正式发表版本；正式版暂时无法获取时，才下载预印本，并标为 `temporary_preprint`。
- 优先调用 `paper-search-mcp`：先用 MCP 补元数据、分版本、下载 PDF；MCP 不足时再用网页或浏览器补线索。
- 来源不是第一判断标准；版本对不对才是第一判断标准。只要是公开或已授权可访问来源，且 PDF 对应最终发表形态（出版社排版、卷期页码、DOI 等信息齐全），就可以按正式版处理，不局限于出版社官网或机构入口。仍然不要绕过访问控制。
- ResearchGate 更适合当线索来源，不把它当默认主下载源。
- 先补元数据，再下载；至少要补标题、DOI、年份、发表源、版本状态和访问状态。
- 先找公开的最终发表版副本，再通过机构权限补齐受限条目；正式版仍无法获取时通过 Sci-Hub 获取出版社 PDF；Sci-Hub 也失败时才降级到预印本。
- 下载后的 PDF 默认按 `年份-期刊或会议全称-题名.pdf` 命名，方便跨会话和人工浏览时快速识别。
- 不默认做截图、首图提取、文本抽取或 BibTeX，除非用户另外提出。
- 工具调用里同意 Sci-Hub 路线。

## 上游衔接

如果用户还在问“某个领域有哪些论文”“帮我筛方向”“找近几年代表作”，先用 `research-lookup` 或其他检索能力完成查找。

如果当前对话里已经有论文线索，就直接进入本 skill，不要求上游一定给出标准清单。可接受的线索包括：

- 题目、DOI、arXiv ID、PubMed ID、出版社页面或作者主页
- `research-lookup` 返回的论文标题、摘要、链接或引用信息
- 用户手写的论文列表
- 某个网页里能识别出的论文条目

进入下载前，先把这些线索整理成 `download_list.md`。如果一篇明确论文都识别不出来，再只问用户一个问题：这次要下载的是哪几篇？

## 优先用 paper-search-mcp

优先使用当前会话里的 `paper-search-mcp` 工具：

- `search_papers`：统一检索、去重和补元数据。默认先用全来源；如果结果噪声过多，再按任务收窄到 `crossref,openalex,semantic,unpaywall,pmc,core,europepmc,arxiv,biorxiv,medrxiv,hal,zenodo,doaj,base`。
- `search_unpaywall`：已知 DOI 时单独查开放获取链接和正式版可得性。
- `download_with_fallback`：用于公开来源下载 PDF；调用时写清楚 `source`、`paper_id`、`doi`、`title`、`save_path`，并把 `use_scihub` 设为 `true`。
- `download_scihub`：直接从 Sci-Hub 下载正式发表版 PDF；当 `download_with_fallback` 的常规来源全部失败、但已知 DOI 时，可以直接调用此工具作为最后备选。
- `download_with_authorization`：正式版需要机构权限、前端按钮或登录会话时优先用它，不要回退到手工猜链接。
- `list_authorization_checkpoints`：批量下载中断或等待用户授权时，先列出未完成的授权记录，再决定继续哪几篇。
- `retry_authorized_download`：用户完成扫码、验证码或学校授权后，沿着原来的授权记录继续下载，不另建重复记录。

把工具返回的信息整理成统一字段：`paper_id`、`title`、`authors`、`doi`、`published_date`、`source`、`url`、`pdf_url`、`extra`。不要把某个平台的原始字段直接写进最终索引。

如果当前会话还未加载 `paper-search-mcp` 工具，先提醒用户新开 Codex 窗口或检查 `C:\Users\SanAn\.codex\config.toml` 的 MCP 注册；不要因此直接改同步副本。

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

不要为了填满字段而猜。无法获取的信息写 `unknown`、`unresolved` 或简短说明。

## 版本判定

按下面顺序判断每篇论文要拿哪个版本：

1. 先确认是否已有正式发表版本。
   有 DOI，且 Crossref、OpenAlex、Semantic Scholar、Unpaywall、出版社页面或正式期刊/会议页面能对应到同一标题时，标为 `published`。
2. 对 `published` 条目，先下载正式发表版本。
   优先 DOI/出版社正式页、出版社开放 PDF、PMC/Europe PMC 正式全文、Unpaywall 指向的 published PDF；作者主页、机构库、课程页、Google Scholar 指到的公开 PDF 或其他公开站点，只要能确认是最终发表形态，也可作为正式版来源。
3. 如果公开和机构渠道都无法获取最终发表版，先通过 Sci-Hub 获取出版社 PDF。
   已知 DOI 时直接调 `download_scihub`；Sci-Hub 获取的是出版社正式 PDF，按正式版记录，来源标 `scihub`。
4. Sci-Hub 也失败时，再找预印本。
   arXiv、bioRxiv、medRxiv、SSRN 等仅作为最后备选；文件名和索引都标 `temporary_preprint`，备注写清楚”正式版存在，但本次未能获取正式 PDF”。
5. 如果暂时只能确认预印本、没有正式发表线索，标为 `preprint`，不要写成正式版。
6. 如果同一论文同时出现多个候选，优先保留 DOI 和正式来源；预印本的 ID、URL 和下载结果作为 `alternate_version` 记录。

### 最终发表形态怎么判断

只要来源可靠，文件不一定非要从出版社官网直接下来。判断重点放在文件本身：

- 标题、作者、DOI 能和正式论文对应上。
- 版面是期刊或会议正式排版，而不是 arXiv、投稿稿、接收稿或网页打印稿。
- 卷、期、页码、发表年份、期刊名或会议信息齐全。
- 文件不是补充材料、勘误、封面页、摘要页或 HTML 网页另存。
- 如果来源是作者主页、机构库、课程页、实验室页面或 Google Scholar 指到的公开 PDF，要在索引备注里写清楚来源。

页面上写 `FULL ACCESS`、`Full Text` 或能阅读全文，只能说明网页正文可读；这不等于已经获取到正式 PDF。仍要点击或请求 PDF 入口，并确认下载文件开头是 `%PDF-`。

## 文件命名规则

下载完成并确认文件头是 `%PDF-` 后，默认把 PDF 统一命名为：

`年份-期刊或会议全称-题名.pdf`

命名细则：

- `年份` 用正式发表年份；只确认预印本时用预印本年份，并在索引中标明版本。
- `期刊或会议全称` 优先取 Crossref、OpenAlex、Semantic Scholar、Unpaywall、出版社页面或正式 PDF 元数据里的完整 `container_title` / venue 名称；不要主动缩写成期刊简称。
- 如果只能获取到缩写或来源缺失，先补元数据；仍无法补全时才使用现有来源名，并在 `paper_index.md` 的备注里说明。
- `题名` 保留英文原标题的主要单词和大小写；清理 Windows 文件名不适合的字符，如 `\ / : * ? " < > |`，把冒号、逗号、破折号等会干扰路径或阅读的标点替换为空格或短横线。
- 字段之间用短横线 `-` 分隔；字段内部保留空格，优先可读性。
- 同一论文存在多个版本时，在题名后、扩展名前追加最小版本后缀，如 `(official)`、`(accepted-manuscript)`、`(temporary-preprint)` 或 `(arXiv)`。
- 遇到超长题名时，先尝试使用 Windows 长路径方式完成重命名；不要退回 `official_DOI.pdf` 这类只给机器看的名字。确实需要缩短时，保留年份和期刊或会议全称，题名只做可读截断，并在索引中保存完整题名和 DOI。
- 重命名后同步更新 `download_list.md`、`paper_index.md`，以及授权记录里的下载路径，避免索引和实际文件名不一致。

## 流程

1. 先整理论文清单。
   从当前对话、上游检索结果、作者主页、题目列表、DOI 页面或出版社页面抽出标题和基础线索。
2. 用 `paper-search-mcp` 补元数据。
   对每个题目或 DOI 调 `search_papers`；已知 DOI 时再调 `search_unpaywall`。尽量补 DOI、期刊或会议名、年份、出版方、版本状态和开放状态。
3. 生成统一下载清单。
   下载前先在目标目录建立或更新 `download_list.md`，把每篇论文的候选正式版、候选预印本、计划动作和备注写清楚。
4. 做访问分流。
   把每篇论文标成 `open`、`institutional`、`request-only` 或 `unresolved`。
5. 先尝试最终发表版公开下载。
   对 `published` 条目，先用 DOI、正式来源和 `download_with_fallback(..., use_scihub: true)` 下载；失败后再查正式页面、浏览器按钮、Google Scholar 指到的公开 PDF、作者主页、机构库、课程页或其他公开副本。只要能确认是最终发表形态，就按正式版记录来源。
6. 公开和机构渠道都无法获取正式版时，用 Sci-Hub 作为最后备选。
   已知 DOI 时直接调 `download_scihub`；Sci-Hub 获取的是出版社正式 PDF，按正式版记录，来源标 `scihub`。
7. Sci-Hub 也失败时再下载预印本。
   只有在正式版（含 Sci-Hub）全部失败且预印本公开可得时才下载预印本，并在文件名、`download_list.md` 和 `paper_index.md` 中标 `temporary_preprint`。
8. 遇到风控、前端按钮或登录墙时，先用 `download_with_authorization`。
   如果返回等待授权，就保存一条授权记录，并在 `download_list.md` 里把状态写成 `pending_authorization` 或 `institutional`。
9. 对明确需要机构权限的条目，优先复用本机已经登录的浏览器状态。
   可以协助点击出版社页里的 `Institutional Sign In`、学校入口、`登录`、`PDF` 等入口；遇到账号、密码、扫码、验证码或二次确认时，停下来让用户本人操作。
10. 下载后立刻做最小校验。
    先看文件头是不是 `%PDF-`；文件异常偏小时，优先怀疑下载到的是 HTML 包装页、验证码页或确认页。对 IEEE Xplore 这类外层网页，还要确认下载到的是页面里嵌入的真正 PDF，而不是外层 HTML。
11. 统一命名并更新索引。
    默认按 `年份-期刊或会议全称-题名.pdf` 命名；同一论文存在多个版本时追加最小后缀，如 `(official)`、`(accepted-manuscript)`、`(temporary-preprint)` 或 `(arXiv)`。
    如果用户已有固定目录，默认同步更新该目录下的 `paper_index.md`。

## 来源优先级

建议按下面顺序找：

1. `paper-search-mcp` 的 DOI、Crossref、OpenAlex、Semantic Scholar、Unpaywall 元数据
2. DOI 对应的出版社正式页面和出版社开放 PDF
3. Google Scholar 指到的公开 PDF、作者主页、机构知识库、课程页、实验室页面等公开副本；确认是最终发表形态时按正式版记录
4. PubMed Central、Europe PMC、CORE、HAL、Zenodo、DOAJ、BASE 等开放仓储
5. 机构登录后的正式出版社 PDF
6. Sci-Hub（通过 `download_scihub` 或 `download_with_fallback(..., use_scihub: true)`）——公开和机构渠道都无法获取正式版时的最后备选，获取的是出版社正式 PDF
7. arXiv、bioRxiv、medRxiv、SSRN 等预印本源
8. ResearchGate 等学术社交站点上的公开全文入口，优先当线索使用，确认版本后再下载

## 浏览器协作

遇到下面这些情况，默认切到浏览器路线，而不是盲目重试命令行：

- `Security check required`
- Cloudflare 或行为风控
- `Download` 按钮不是直链，而是前端事件
- PDF 依赖浏览器会话、Cookie、短时令牌或在线阅读器
- 机构登录要走统一身份认证
- 直链、命令行或普通网页请求返回 403、HTML 页面、登录页，但用户在浏览器里能看到下载按钮或阅读全文

这类任务优先配合 `browser-use` 或当前可用的浏览器工具。

授权协作时只做入口点击和状态观察，不替用户输入账号密码，不绕过登录、订阅或机构权限。若本机已经保存学校登录态，优先复用当前浏览器会话；若工具另开了空白浏览器导致没有登录态，应改用已登录浏览器代理，或请用户在该浏览器里完成授权。

用户完成授权后，不要从头重试整篇论文；优先用 `retry_authorized_download` 继续原来的授权记录。这样批量下载时可以把所有等待授权的条目排队处理，减少遗漏或误下。

浏览器路线要像人工操作一样验证入口：先看页面上的 `PDF`、`Download PDF`、`View Options`、`Institutional Login` 等按钮，再检查 iframe、embed、pdfdirect、在线阅读器里的真实 PDF 地址。不能只因为直接访问 PDF 链接失败，就判定这篇文章没有正文 PDF。

下载完成后，先检查文件头是不是 `%PDF-`。如果返回的是 `text/html`、`<!DOCTYPE html>`、学校登录页、验证码页或 Science/Nature/IEEE 的外层网页，就不能当成论文 PDF 保存。

## 交付

默认交付三类：

- 下载好的 PDF 文件
- `download_list.md`：下载前后的统一清单，记录每篇论文的正式版候选、预印本候选、计划动作、下载状态和失败原因
- `paper_index.md`：最终索引，记录标题、DOI、年份、发表源、版本、访问状态、文件名、来源 URL、下载日期和备注

如果用户已有固定论文目录，默认把“下载 + 规范命名 + 索引更新”视为一个完整动作。

索引里要把版本和来源说清楚。正式 PDF、作者主页上的正式排版 PDF、机构库公开副本、预印本、临时预印本、补充材料，都不要混成一种状态。补充材料不能替代正文 PDF；网页全文也不能替代正式 PDF。

`download_list.md` 建议列：

| title | authors | doi | year | venue_or_source | publication_status | preferred_version | official_candidate | preprint_candidate | access_status | download_status | saved_path | notes |
|---|---|---|---:|---|---|---|---|---|---|---|---|---|

`paper_index.md` 建议列：

| title | doi | year | venue_or_source | version | access_status | file | source_url | retrieved_at | notes |
|---|---|---:|---|---|---|---|---|---|---|

版本值统一用：`official`、`accepted_manuscript`、`preprint`、`temporary_preprint`、`unresolved`。发表状态统一用：`published`、`preprint_only`、`unknown`。访问状态统一用：`open`、`institutional`、`request-only`、`unresolved`。下载状态统一用：`downloaded`、`pending`、`failed`、`skipped`。

## 边界

- 对只支持 `Request full-text`、只支持付费购买、且用户没有访问权限的条目，要明确说明目前不能直接下载。
- 不直接修改 `paper-search-mcp`、`research-lookup` 这类上游来源；需要记录下载规则时，优先归档到本 skill 的 `references/`。

## 相关文件

- 出版社下载经验：[references/publisher-download-playbook.md](references/publisher-download-playbook.md)

## 相关工具与技能

- 上游查找：`research-lookup`
- 论文检索和下载后端：`paper-search-mcp`
- 单篇总结：`paper-summary`
- 浏览器协作：`browser-use` 或当前可用的浏览器工具
- PDF 后处理：`pdf`
- 文献归档：`zotero`
- 本地 skill 维护：`skill-creator`

## 维护

- 新出现的站点经验，优先记录到 [references/publisher-download-playbook.md](references/publisher-download-playbook.md)，正文只保留稳定流程和边界。
- 如果以后长期要处理某一出版方的特殊流程，再补更具体的站点分流规则，不要让正文变成站点清单。
