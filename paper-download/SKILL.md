---
name: paper-download
license: MIT
description: 获取、复用或导入论文 PDF 到 Zotero，先查已有条目、附件和任务本地资料，只补请求的缺项；入库前控制非请求的自动抓取，超时先核实原操作。Use when 用户给出题名、DOI、论文 URL、作者主页、论文列表、本地 PDF 或 paper-search 结果，要求下载、保存到 Zotero、整理已有论文或继续机构授权下载。研究问题检索与引用元数据核验用 paper-search；原文技术核对用 paper-review。联网由 web-access 路由；Windows 版机构模块通过 web-access HTTP Broker 复用当前 Edge 会话，负责出版物核验，不自行执行浏览器登录或验证码。
---

# 论文 PDF 获取与入库

## 范围与交付

获取或复用用户请求的论文版本，核验后保存为 Zotero 管理的附件。已知论文下载和本地 PDF 入库使用本技能；筛选论文或寻找论断证据先用 `paper-search`，技术核对用 `paper-review`。只问访问状态时保持只读。

沿用检索交接的题名、稳定标识、已核实来源、资料库、工作区集合、父条目及版本要求；已有父条目只补附件，未建条目则查重后建立一次。仅在身份或目标确有关键歧义时询问，不重复确认已授权的入库和归类。

- Zotero 是默认文献库；未指定资料库时用个人库，不猜当前选中分类。论文沿用 [`zotero-workspace-library`](../zotero-workspace-library/SKILL.md) 确定的工作区集合；同一资料复用条目和附件，不按文章或检索任务复制分类。
- 用户明确只要本地文件时按指定位置交付；要求项目副本时从 Zotero 导出。索引仅在用户要求或有效项目约定需要时维护，不默认创建 `paper_index.md`、引用账本或另一套 PDF 库。
- 阅读复用已有笔记。文献本身的方法、结果、局限及原文位置留在 Zotero；当前文章的引用用途和待核问题留在工作区已有材料，不默认批量重做精读。
- Windows 机构访问只复用用户已有合法权限；`web-access` 是唯一浏览器执行层，默认当前 Edge 的 `existing` 会话。常规登录、验证和下载按任务授权由该层处理，不复制 Profile，不读取或导出学校密码、浏览器密码库、Cookie 或认证令牌；真正短信、动态口令、刷脸或系统级验证才交还用户。

## 目标版本

开始时沿用用户的版本要求。纯本地整理、归类或导入已有文件时，核对身份并如实记录文件版本，不自动扩大为下载或升级任务；只有请求获取或补齐版本时，未指定且论文已正式发表才默认出版社当前正式版。明确只要作者稿、预印本或某个历史版本时，以该版本验收。确认仅有预印本、无正式发表记录时，按预印本任务处理；发表状态未知时继续核实，不推定正式版存在或不存在。

`publication_status` 描述论文是否发表；`version` 描述实际文件，两者不能混用。库内已有作者稿或旧 Early Access，不能满足当前卷期正式版请求。默认目标为正式版时，可保存合法作者稿供阅读，但仍报告“作者稿已保存，正式版待补”；用户明确指定非正式版本时，按请求完成，不强制补另一版本。

## 执行流程

1. **查重与定位**：先用本技能自带的 [只读状态脚本](scripts/zotero_local_status.py) 执行 `status --json`，按 [连接与接口选择](references/zotero-storage.md#连接与接口选择) 取得并验证本机地址和各后台能力，无需另找 Zotero 专用插件或缓存脚本。条目和附件检索、读取使用本地 API，写入使用已配置且支持该操作的 Connector 或后台桥接。后台缺少目标能力时说明具体缺口，未经用户明确同意不操作窗口或抢焦点。确认接口后，先按 DOI 等稳定标识找条目，再核对题名、作者和年份。通用搜索可能不覆盖 DOI 字段，空结果时改用题名、作者找候选并读取实际 DOI，不能凭一次空结果新建条目。读取现有正文附件、版本、分类与阅读内容；再核对本任务已知的索引、BibTeX、PDF 和上一步交接的本地路径，不全盘扫描。
2. **核实身份与目标**：复用可定位、未变化的已核实信息；缺口交 `paper-search`，未知字段不猜。需要获取或升级已发表论文时，读取出版社当前记录，核对 DOI、卷期页码或文章号和当前版本，再判断已有文件是否满足请求。已有可读目标版本优先复用；库内缺 PDF 而本地已有时，直接核验本地文件并入库，缺父条目不等于缺全文。纯本地整理不触发升级下载。已有附件的冗余检查按下文执行。
3. **发现全文入口**：尚缺目标文件时，按 [全文入口发现](references/publisher-download-playbook.md#全文入口发现) 查找。默认正式版先查出版社公开入口和已配置、获授权的机构渠道；受阻后主动扩展公开来源，不等用户提醒。访问机构资源失败时，先核对实际登录态（页面是否显示机构名称或「Access provided by」字样），未登录或登录态已失效时按 `web-access` 重新完成机构登录再重试，不得在未确认登录态的情况下断言机构无订阅。未适配的助手、工具故障或页面访问检查不能当成学校无订阅。找到可靠目标版本即可停止扩渠道；保存其他版本不自动结束正式版补齐。
4. **取得并核验 PDF**：具体论文页面及 PDF 统一走 `web-access`，默认当前 Edge 的 `existing` 会话；机构模块消费 HTTP Broker 的 `/access` 与 `/download`，不重写浏览器或认证逻辑。搜索与公开元数据按 `web-access` 选择工具。IEEE Xplore 或 Optica 文章需要机构访问时，优先使用本技能的 [公开机构访问模块](scripts/institutional_access/README.md)。依赖登录、动态按钮或访问检查时直接用相应入口，不先盲目直抓。下载到本次任务暂存目录，按下文核验文件身份、可读性及版本。
5. **原生入库与回读**：关闭本次 PDF 读取句柄，按 [共享入库流程](references/zotero-storage.md) 检查自动抓取和原操作状态，再创建缺少的父条目或补附件；仅导入元数据也执行这项检查。批量按篇串行查重、保存并记录查询线索，不重投结果未知的整批导入。回读归属、实际路径、文件和哈希，核对所需版本确实保存。请求超时不代表 Zotero 停止执行，先查询同一操作和持久化结果；每轮状态检查最多 45 秒，仍未知时保留有效文件并报告待续。Zotero 不可用时报告待入库，不换建长期文献库。
6. **版本去重与收尾**：目标版本入库或复用核验成功后，仅按下文规则把可清理的冗余正文附件原生移入回收站；再次核对保留文件、分类、标签和笔记。成功后清理本次自有暂存，移动导入则确认原临时路径消失；失败时保留有效文件和旧附件。按 `web-access` 收尾自有会话和页面，保留用户页面及长期服务。

准确机构登录授权、用户接管、网络重试和宿主拒绝边界统一遵循 [web-access](../web-access/SKILL.md)；站点操作见 [下载参考流程](references/publisher-download-playbook.md#公开机构访问模块)。不读取或导出密码、Cookie、令牌，不通过其他工具重放宿主明确拒绝的动作；独立获准的公开查找可继续。

## 机构访问模块

Windows 机构模块支持 Python 3.10+、Node.js 22+、IEEE Xplore 和 Optica Publishing Group，依赖同仓库的 `web-access`。Python 环境位于 `%LOCALAPPDATA%\PaperDownload\venv`；短生命周期 Broker task token 保存在 Windows 凭据管理器，不是出版社认证令牌。模块只保留出版物识别、身份/PDF/版本验证与既有 CLI，入库继续使用共享 Zotero 流程。

默认前检 `check-deps.mjs --browser edge --mode existing --json`，由 `web-access` 从 `DevToolsActivePort` 发现当前 Edge 的实际 CDP 地址，连接 HTTP Broker（通常 `127.0.0.1:3456`）。每个任务新建后台 tab，保留用户原有活动页；收尾只关闭自有页，不停止 Broker 或 Edge。`managed` 仅显式隔离任务可用，不是默认或自动回退。模块不启动、探测修复或另接浏览器，不复制 Profile 或登录数据。HTTP `/json/version` 404 不等于 CDP 失败，控制判定和恢复交给 `web-access`。

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
- 前检要求 `ready:true`、请求的模式与 Edge 身份一致、控制探针通过；`proxy_version_mismatch`、`control_probe_failed`、`task_capacity_reached` 等保留原状态，不改写成学校未登录或无订阅。
- 访问状态通过 `POST /v2/tabs/{targetId}/access` 取得脱敏 `state`、`failureCode`、`handoffRequired`、`interactionRequired`。先核对 Broker 能力；缺接口是环境/版本缺口，不在本模块重建登录、验证码或 CDP 执行路径。
- 常规保存账号自动填充与登录提交由 Broker 完成；图形/滑块验证由 `web-access` 页面动作、邮箱验证码由获授权邮件工具按实际能力处理。`interactionRequired` 或兼容状态 `user_login_required`、`publisher_verification` 不自动等于人工接管，也不保证脚本能解决所有验证。
- 真正短信、动态口令、刷脸或系统级验证才根据 `handoffRequired` 保留现场交还用户。handoff 期间禁读、禁截图、禁修改；用户完成后调用 `resume` 回读同一任务，不能把回复当作登录、权限或 PDF 成功证据。工具限制、账号歧义或能力不足单独报告，不冒充强验证；发送消息、申请权限或付款不属于常规登录授权。
- PDF 统一调用 `POST /v2/tabs/{targetId}/download`，提供准确 `url`、有限 `timeoutMs` 和 `maxBytes`，仅允许同源或已确认的出版社 PDF 主机。复核完整二进制、解码后的最终 URL、长度与 SHA-256，再进行身份/版本检查；不保留页内 fetch/Base64 分块或另一套 CDP 下载实现。
- `access_unavailable` 需结合实际页面判断；只有确认当前机构登录有效且存在相应权限拒绝证据，才报告订阅不足。401/403/429/418、挑战和控制失败分别记录，不靠重复登录、改代理、Cookie 或端点绕过。返回 `institutional_access` 但无 PDF 时保留同一任务，报告入口缺口。
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

交付题名、实际保留版本、目标是否完成、Zotero 条目或本地交付入口、工作区集合及必要待补原因。仅元数据、可读网页或下载暂存不能当成 PDF 入库完成。批量结果分别统计已取得的目标版本、其他可读版本及待补数量；去重状态、原生移入回收站数量和暂留理由单独说明，不能用“每篇都有 PDF”代替版本验收。

未取得目标版本时，说明实际已查的相关渠道、访问结果及未闭合步骤；不将“本轮未取得”扩大成“全文不存在”。记录复用的历史证据与本轮实际访问，不把旧错误当今天的实测。返回便于库内搜索的关键词，通常无需展示 storage 路径或让用户记住 key。

沿用以下状态值，不另建状态体系：

- `version`：`official`、`accepted_manuscript`、`preprint`、`temporary_preprint`、`unresolved`。
- `publication_status`：`published`、`preprint_only`、`unknown`。
- `access_status`：`open`、`institutional`、`request-only`、`unresolved`。
- `download_status`：`downloaded`、`pending`、`failed`、`skipped`，只表示相应文件状态。
- `official_status`：`obtained`、`pending`、`not_applicable`；用户指定非正式目标或确认仅有预印本时用 `not_applicable`，不把它解释为论文未正式发表。
- 既有 CLI 命令、业务状态与 `version` 等枚举保持兼容；新增 `failure_code` 保留 Broker 的控制/站点/文件分类，不覆盖旧状态。`not_pdf`、`incomplete`、`identity_mismatch`、`too_large`、`download_timeout` 均不能作为下载或入库成功。
- 受阻时附具体原因：`host_policy`、`environment`、`user_verification`、`institution_permission`、`transport`、`pdf_validation` 或 `zotero_write_unknown`。文件占用属于本地环境；未知写入与已确认失败分开，不把各类阻塞统称为学校登录失败。

技能维护按 `skill-creator`，发布按 `agent-rules`；普通下载不自动修改技能，也不把单机或单一机构验收推广为全部出版社均可用。
