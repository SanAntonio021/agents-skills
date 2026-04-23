---
name: lunwen-xiazai
description: 按题目、DOI、作者主页、出版社页面或论文列表下载论文 PDF，并把结果落盘和记索引。Use when 用户要下载单篇或批量论文、从作者主页和 DOI 找全文、补齐公开副本，或在必要时配合浏览器和机构登录完成合法访问；prefer 公开和合法来源 first。
---

# 论文下载

## 作用

这份 skill 负责把论文题目、DOI、作者主页、出版社页面或结果列表，稳定转成可落盘的 PDF 下载结果，并把状态分清楚：

- 已公开可直接获取
- 需要机构权限
- 目前无法直接获取

## 适用场景

- 下载单篇或多篇论文 PDF
- 从作者主页、ResearchGate、Google Scholar、DOI 或出版社页面整理下载入口
- 用户愿意在必要时配合浏览器验证、验证码或机构登录

## 核心规则

- 优先官方和合法来源：出版社页面、机构知识库、作者公开副本、PubMed Central 等。
- ResearchGate 更适合当线索来源，不把它当默认主下载源。
- 先补元数据，再下载；至少要补标题、DOI、年份、来源和访问状态。
- 先拿公开副本，再考虑机构权限补齐受限条目。
- 不默认做截图、首图提取、文本抽取或 BibTeX，除非用户另外提出。

## 流程

1. 先整理论文清单。
   从作者主页、题目列表、DOI 页面或出版社页面抽出标题和基础线索。
2. 再补元数据。
   尽量补 DOI、期刊或会议名、年份、出版方和开放状态。
3. 做访问分流。
   把每篇论文标成 `open`、`institutional`、`request-only` 或 `unresolved`。
4. 先尝试公开下载。
   先从 DOI 指向的正式页面找公开 PDF、作者公开副本或机构仓储副本。
5. 遇到风控、前端按钮或登录墙时，切到浏览器协作。
   需要用户动作时，一次只请用户做一个动作。
6. 对明确需要机构权限的条目，引导用户完成学校或机构登录，再继续下载。
7. 下载后立刻做最小校验。
   先看文件头是不是 `%PDF-`；文件异常偏小时，优先怀疑下载到的是 HTML 包装页、验证码页或确认页。
8. 统一命名并更新索引。
   默认用“论文标题.pdf”；同一论文存在多个版本时，再追加最小后缀，如 `(official)` 或 `(arXiv)`。
   如果用户已有固定目录，默认同步更新该目录下的 `paper_index.md` 或等价索引。

## 来源优先级

建议按下面顺序找：

1. DOI 对应的出版社正式页面
2. PubMed Central、机构知识库、作者主页公开副本
3. 出版方允许的开放获取副本
4. ResearchGate 等学术社交站点上的公开全文入口
5. 机构登录后的正式出版社 PDF

## 浏览器协作

遇到下面这些情况，默认切到浏览器路线，而不是盲目重试命令行：

- `Security check required`
- Cloudflare 或行为风控
- `Download` 按钮不是直链，而是前端事件
- PDF 依赖会话、Cookie、短时令牌或前端 viewer
- 机构登录要走统一身份认证

这类任务优先配合 `playwright-interactive`。

## 交付

默认交付只有两类：

- 下载好的 PDF 文件
- 一份简洁索引，例如 `paper_index.md`，记录标题、DOI、来源、访问状态和是否已下载

如果用户已有固定论文目录，默认把“下载 + 规范命名 + 索引更新”视为一个完整动作。

## 边界

- 不绕过访问控制，不使用盗版论文站点。
- 对只支持 `Request full-text`、只支持付费购买、且用户没有合法访问权限的条目，要明确说明目前不能直接下载。
- 不把站点经验写回 `vendor` skill；需要沉淀时，优先放进当前 `custom` skill 的 `references/`。

## 相关文件

- 出版社下载经验：[references/publisher-download-playbook.md](references/publisher-download-playbook.md)

## 相关技能

- 浏览器协作：`playwright-interactive`
- PDF 后处理：`pdf`
- 文献归档：`zotero`
- 本地 skill 维护：[../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)

## 维护

- 新出现的站点经验，优先沉淀到 [references/publisher-download-playbook.md](references/publisher-download-playbook.md)，正文只保留稳定流程和边界。
- 如果以后长期要处理某一出版方的特殊流程，再补更具体的站点分流规则，不要把正文堆成站点清单。
