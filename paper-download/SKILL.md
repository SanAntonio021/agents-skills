---
name: paper-download
license: MIT
description: 获取、复用或导入论文 PDF 到 Zotero，先查已有条目、附件和任务本地资料，只补请求的缺项；入库前控制非请求的自动抓取，超时先核实原操作。Use when 用户给出题名、DOI、论文 URL、作者主页、论文列表、本地 PDF 或 paper-search 结果，要求下载、保存到 Zotero、整理已有论文或继续机构授权下载。研究问题检索与引用元数据核验用 paper-search；原文技术核对用 paper-review。联网由 web-access 路由；Windows 版内置公开机构访问模块，使用用户已有浏览器登录态并支持登录交接。
---

# 论文 PDF 获取与入库

## 范围与交付

获取或复用用户请求的论文版本，核验后保存为 Zotero 管理的附件。已知论文下载和本地 PDF 入库使用本技能；筛选论文或寻找论断证据先用 `paper-search`，技术核对用 `paper-review`。只问访问状态时保持只读。

沿用检索交接的题名、稳定标识、已核实来源、资料库、任务分类、父条目及版本要求；已有父条目只补附件，未建条目则查重后建立一次。仅在身份或目标确有关键歧义时询问，不重复确认已授权的入库和归类。

- Zotero 是默认文献库；未指定资料库时用个人库，不猜当前选中分类。文章或持续调研的归类遵循 [paper-search](../paper-search/SKILL.md#按研究任务组织文献)，同一任务共用已确定分类，不复制条目或附件。
- 用户明确只要本地文件时按指定位置交付；要求项目副本时从 Zotero 导出。索引仅在用户要求或有效项目约定需要时维护，不默认创建 `paper_index.md`、引用账本或另一套 PDF 库。
- 阅读复用已有笔记。文献本身的方法、结果、局限及原文位置留在 Zotero；当前文章的引用用途和待核问题留在工作区已有材料，不默认批量重做精读。
- Windows 公开机构访问模块只复用用户已有合法访问。用户自己的学校/CARSI/OpenAthens/MFA 登录由用户完成；不得读取或保存学校密码、浏览器密码库、Cookie 或认证令牌。

## 目标版本

开始时沿用用户的版本要求。纯本地整理、归类或导入已有文件时，核对身份并如实记录文件版本，不自动扩大为下载或升级任务；只有请求获取或补齐版本时，未指定且论文已正式发表才默认出版社当前正式版。明确只要作者稿、预印本或某个历史版本时，以该版本验收。确认仅有预印本、无正式发表记录时，按预印本任务处理；发表状态未知时继续核实，不推定正式版存在或不存在。

`publication_status` 描述论文是否发表；`version` 描述实际文件，两者不能混用。库内已有作者稿或旧 Early Access，不能满足当前卷期正式版请求。默认目标为正式版时，可保存合法作者稿供阅读，但仍报告“作者稿已保存，正式版待补”；用户明确指定非正式版本时，按请求完成，不强制补另一版本。

## 执行流程

1. **查重与定位**：用现有 Zotero 工具检查可用性，先按 DOI 等稳定标识找条目，再核对题名、作者和年份。通用搜索可能不覆盖 DOI 字段，空结果时改用题名、作者找候选并读取实际 DOI，不能凭一次空结果新建条目。读取现有正文附件、版本、分类与阅读内容；再核对本任务已知的索引、BibTeX、PDF 和上一步交接的本地路径，不全盘扫描。
2. **核实身份与目标**：复用可定位、未变化的已核实信息；缺口交 `paper-search`，未知字段不猜。需要获取或升级已发表论文时，读取出版社当前记录，核对 DOI、卷期页码或文章号和当前版本，再判断已有文件是否满足请求。已有可读目标版本优先复用；库内缺 PDF 而本地已有时，直接核验本地文件并入库，缺父条目不等于缺全文。纯本地整理不触发升级下载。已有附件的冗余检查按下文执行。
3. **发现全文入口**：尚缺目标文件时，按 [全文入口发现](references/publisher-download-playbook.md#全文入口发现) 查找。默认正式版先查出版社公开入口和已配置、获授权的机构渠道；受阻后主动扩展公开来源，不等用户提醒。未适配的助手、工具故障或页面访问检查不能当成学校无订阅。找到可靠目标版本即可停止扩渠道；保存其他版本不自动结束正式版补齐。
4. **取得并核验 PDF**：具体论文页面及 PDF 统一走 `web-access` 的受管浏览器；搜索与公开元数据按 `web-access` 选择工具。IEEE Xplore 或 Optica 文章需要机构访问时，优先使用本技能的 [公开机构访问模块](scripts/institutional_access/README.md)。依赖登录、动态按钮或访问检查时直接用相应入口，不先盲目直抓。下载到本次任务暂存目录，按下文核验文件身份、可读性及版本。
5. **原生入库与回读**：关闭本次 PDF 读取句柄，按 [共享入库流程](references/zotero-storage.md) 检查自动抓取和原操作状态，再创建缺少的父条目或补附件；仅导入元数据也执行这项检查。批量按篇串行查重、保存并记录查询线索，不重投结果未知的整批导入。回读归属、实际路径、文件和哈希，核对所需版本确实保存。请求超时不代表 Zotero 停止执行，先查询同一操作和持久化结果；每轮状态检查最多 45 秒，仍未知时保留有效文件并报告待续。Zotero 不可用时报告待入库，不换建长期文献库。
6. **版本去重与收尾**：目标版本入库或复用核验成功后，仅按下文规则把可清理的冗余正文附件原生移入回收站；再次核对保留文件、分类、标签和笔记。成功后清理本次自有暂存，移动导入则确认原临时路径消失；失败时保留有效文件和旧附件。按 `web-access` 收尾自有会话和页面，保留用户页面及长期服务。

准确机构登录授权、用户接管、网络重试和宿主拒绝边界统一遵循 [web-access](../web-access/SKILL.md)；站点操作见 [下载参考流程](references/publisher-download-playbook.md#公开机构访问模块)。不读取或导出密码、Cookie、令牌，不通过其他工具重放宿主明确拒绝的动作；独立获准的公开查找可继续。

## 机构访问模块

第一版机构下载仅支持 Windows、Python 3.10+、Node.js 22+、`web-access` 受管 Edge、IEEE Xplore 和 Optica Publishing Group。必须同时安装同一仓库的 `web-access` 技能；模块通过 `%LOCALAPPDATA%\PaperDownload\venv` 创建独立 Python 环境，并把浏览器任务令牌保存在 Windows 凭据管理器。学校密码不进入该环境或配置。日常 Edge 或 Chrome 的 `existing` 模式不用于机构下载；`web-access` 失败时不会自动回退到日常浏览器。

受管 Edge 的独立 Profile 位于 `%LOCALAPPDATA%\web-access\managed-edge-profile`，CDP 端口为 `9222`，长期 Proxy 端口为 `3456`。首次任务按需启动，登录 Cookie 随该 Profile 持久化；本模块只创建和关闭自己的 task/tab，不停止 Broker、不关闭其他对话或用户页面。

同一 `--session` 一次只允许一个命令运行；并发调用返回会话占用，不并行操作同一页面。

```powershell
$skillRoot = '<已解析的 paper-download 技能目录>'
$ia = Join-Path $skillRoot 'scripts/institutional_access/run.ps1'
& $ia acquire --session <唯一任务名> --url <文章页> --doi <DOI> --output <新PDF路径>
& $ia status --session <唯一任务名>
& $ia resume --session <唯一任务名> --doi <DOI> --output <新PDF路径>
& $ia complete --session <唯一任务名>
```

- `acquire` 返回 `downloaded_identity_verified` 时复用同一 PDF，不再启动第二条机构下载路径。
- 内部前检固定运行 `web-access check-deps.mjs --browser edge --mode managed --json`，并要求真实控制探针通过。返回 `managed_profile_busy`、`managed_cdp_port_conflict`、`managed_browser_launch_failed`、`proxy_version_mismatch`、`control_probe_failed`、`task_capacity_reached` 等 Broker 故障时，保留具体状态；不要把它们改写成学校登录或订阅失败。
- 返回 `user_login_required` 时，浏览器标签已经激活。告知用户完成学校/CARSI/OpenAthens 登录或 MFA，完成后只记录“用户报告完成”；用户回复后必须调用 `resume` 回读页面，不能把回复本身当作授权或下载成功。
- 仅当页面是 HTTPS 登录页、用户名与密码已由浏览器填好、表单和唯一提交控件同源且没有待确认的必选项时，本模块可自动提交一次。它不读取或返回字段值；账号、机构或表单有歧义、需要 MFA/验证码或提交结果未知时仍交给用户，完成后回复再 `resume`。
- 返回 `publisher_verification` 时等待用户完成验证码或安全验证，再 `resume`。
- 返回 `access_unavailable` 表示登录后仍没有出版社权限；不要改代理、Cookie 或命令行端点绕过。
- 返回 `institutional_access` 但无 PDF 时保留同一页面和会话，报告 PDF 入口缺口，不重新建任务。
- 下载成功仍需按本技能主流程核对文件、DOI、版本、Zotero 附件和回读。Zotero 保存完成后才调用 `complete`；会话处于 handoff 时不能直接关闭。
- 已确认本次不再重试的活动任务也应在用户结束该分支后调用 `complete`。handoff 中的任务不能绕过恢复屏障强制关闭；若用户明确取消，保留给用户关闭，或等待任务到期释放。

## PDF 身份与版本核验

- 文件头为 `%PDF-`，文件可读且是对应论文正文，不是登录页、HTML 包装、摘要、封面、补充材料或错误通知。真 PDF 也可能是整期文件，提取单篇时记录原页范围。
- 核对完整题名、作者及发表身份。有印刷 DOI 时核对一致；未印 DOI 不单独判失败，但须串联已核实出版社记录、实际全文入口、题名作者及出版标记。存在身份冲突时保留待核，不自动入库或删除有效旧文件。
- 正式版须与出版社当前排版、卷期页码或文章号及年份对应。当前仅提供已编辑正式 Early Access 时注明尚无卷期版；标有作者版、未完成编辑的文件仍按实际状态处理。双栏外观、DOI、仓储标签、网页 `Full Text` 或 `FULL ACCESS` 均不能单独证明正式 PDF 已取得。
- 作者或机构公开副本可以是正式版，但需同样核验；没有接收证据的发表前稿不能标 `accepted_manuscript`。接收稿、预印本、历史稿和身份已确认但版本未明的文件分别记录，不能一律称正式版。

## 版本选择与去重

仅处理本次触及的论文正文 PDF；补充材料、更正文件、独立笔记和其他附件不进入清理集合。阅读内容保护包括 Zotero 批注、PDF 内嵌批注、附件自身及关联笔记；读取失败按未知保留。

- **同一版本**：优先复用有批注的可读附件，其次有附件笔记的已有附件，再其次已有可读文件，不因下载时间较新替换。多份都有阅读内容或版本等价不明时暂留。无批注、无附件笔记的重复正文可原生移入回收站。
- **确有更新**：目标新版核验并保存后，无阅读内容的旧正文可移入回收站；带批注或笔记的旧版暂留，报告准确新版入口及旧版待迁移原因，不按页码或坐标搬批注。用户请求历史版本时，不据此清理不同版本的现有正文。
- **依据与提交**：同哈希可证明字节相同，不同哈希、同 DOI、文件名或时间不能证明版本更新。结合出版状态、修订说明、正文和图表判断；提交前复核归属、版本及阅读内容。新增批注或文件变化使原清理判断失效时重新检查。

具体候选记录、原生回收站调用和回读要求见 [版本去重执行](references/zotero-storage.md#版本去重执行)。不永久删除、不清空回收站、不直接修改数据库或 storage；入库失败不进入旧版清理。

## 命名与输出

Zotero 管理的文件沿用库内命名设置，不直接重命名 storage 文件。明确导出本地且无项目约定时，使用 `年份-期刊名-标题名.pdf`；年份按正式发表年，仅预印本则用其年份并标版本，期刊或会议名以核实信息为准。清理 Windows 非法文件名字符，长题名可截短，完整身份留在条目中。多版本用 `(official)`、`(accepted-manuscript)`、`(temporary-preprint)`、`(arXiv)` 等最小后缀。重命名仅更新任务引用和明确存在的索引，不修改登录授权记录。

交付题名、实际保留版本、目标是否完成、Zotero 条目或本地交付入口、任务分类及必要待补原因。仅元数据、可读网页或下载暂存不能当成 PDF 入库完成。批量结果分别统计已取得的目标版本、其他可读版本及待补数量；去重状态、原生移入回收站数量和暂留理由单独说明，不能用“每篇都有 PDF”代替版本验收。

未取得目标版本时，说明实际已查的相关渠道、访问结果及未闭合步骤；不将“本轮未取得”扩大成“全文不存在”。记录复用的历史证据与本轮实际访问，不把旧错误当今天的实测。返回便于库内搜索的关键词，通常无需展示 storage 路径或让用户记住 key。

沿用以下状态值，不另建状态体系：

- `version`：`official`、`accepted_manuscript`、`preprint`、`temporary_preprint`、`unresolved`。
- `publication_status`：`published`、`preprint_only`、`unknown`。
- `access_status`：`open`、`institutional`、`request-only`、`unresolved`。
- `download_status`：`downloaded`、`pending`、`failed`、`skipped`，只表示相应文件状态。
- `official_status`：`obtained`、`pending`、`not_applicable`；用户指定非正式目标或确认仅有预印本时用 `not_applicable`，不把它解释为论文未正式发表。
- 受阻时附具体原因：`host_policy`、`environment`、`user_verification`、`institution_permission`、`transport`、`pdf_validation` 或 `zotero_write_unknown`。文件占用属于本地环境；未知写入与已确认失败分开，不把各类阻塞统称为学校登录失败。

技能维护按 `skill-creator`，发布按 `agent-rules`；普通下载不自动修改技能，也不把单机或单一机构验收推广为全部出版社均可用。
