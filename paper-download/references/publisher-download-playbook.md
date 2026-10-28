# 论文全文入口与出版社下载参考

更新时间：2026-10-27。本文件集中维护检索渠道、机构访问与站点经验；目标版本、文件核验和完成条件以 [paper-download](../SKILL.md) 为准，通用联网与授权规则以 [web-access](../../web-access/SKILL.md) 为准。历史站点经验不代表本轮访问成功。

## 全文入口发现

`paper-search` 和 `paper-download` 共用下表，不各建一份来源清单。研究检索按问题发现候选；指定论文补全文用准确 DOI、完整题名及作者找其他版本，再回到实际托管源核实。

| 学术检索入口 | 用途与检查重点 |
|---|---|
| [Google Scholar](https://scholar.google.com/) | 综合发现、引用链与“所有版本”。检查 PDF/HTML 入口及能提供新来源的后续分页，不只看第一条结果；版本数包含引用和元数据记录，不能计为可下载文件数。 |
| [Semantic Scholar](https://www.semanticscholar.org/) | 论文及关联文献发现，核查论文页的 PDF、原文或出版社链接；没有全文入口不代表论文不存在。 |
| [OpenAlex](https://openalex.org/) | 文献身份、引用关系与公开副本位置；读取实际记录中可用的 locations/公开版本入口，不凭索引标签认定文件版本。 |
| [CORE](https://core.ac.uk/) | 跨机构及学科仓储查找开放全文，回到聚合记录所指原始页面或实际 PDF。 |
| [BASE](https://www.base-search.net/) | 补查学术网页、学位论文和仓储资源，核对结果的原始来源及是否确有全文。 |

按缺口选择当前可用且可能提供新线索的入口，不强制逐篇遍历全部平台；某一入口无结果、访问受阻或需要未配置的 API 权限时，记录该结果并继续其他独立可用来源，不为普通检索新增账号或凭据。发现候选后核实身份，不把索引摘要当全文。

默认正式版先从 DOI/出版社当前页面确认目标与公开 PDF，再实际尝试已配置且获授权的机构渠道。仍缺全文时主动用上表补查并检查以下实际来源：

- 出版社公开副本、开放获取定位服务（如 Unpaywall）指向的文件；作者、研究组、机构或学科仓储中的对应版本。预印本服务器、开放全文库按领域适用性使用，来源可靠不等于文件为正式版。
- ResearchGate、Academia 等作者上传平台可提供线索；实际下载需要申请、注册或新授权时报告，不把可读预览当已取得 PDF，不默认联系作者或注册。
- 已观察到的原始全文链接失效时，可检查该准确地址的合法历史存档。记录原来源、快照地址与日期，取得原始 PDF 后照常核验；不猜文件名或枚举未知标识，不重建排版来冒充原件。

跨平台结果按文献身份归并；同一论文的候选地址先按规范化落地地址与最终 PDF 入口去重，未知或不同版本保留线索。已有文件与新文件的去重由主技能按哈希、内容和版本处理，同 DOI 不能证明文件相同。

找到并核验目标版本即可停止扩来源。未取得时，当前相关可用渠道已查、机构步骤有实际访问结果或明确阻塞后报告缺口；只保存其他版本时按目标要求决定是否仍待补。不使用无限改写检索式、反复请求同一错误页或固定数量打卡代替查找。宿主明确拒绝的动作遵循 `web-access` 的恢复条件，不能换工具重放；独立获准的公开检索和下载可继续。

## 公开机构访问模块

Windows 机构模块支持 IEEE Xplore 和 Optica Publishing Group，通过 `scripts/institutional_access/run.ps1` 保留 `acquire/status/resume/complete` CLI。模块依赖同仓库 `web-access`，Python 环境位于 `%LOCALAPPDATA%\PaperDownload\venv`；浏览器发现、连接、页面、登录、验证、下载及恢复只有 `web-access` 一套实现。默认当前运行 Edge 的 `existing` 会话，CDP 从 `DevToolsActivePort` 动态发现，HTTP Broker 通常 `127.0.0.1:3456`。`managed` 仅明确要求隔离时使用，不作自动回退。

每个任务创建独立后台 tab，不改用户原有活动页；只把短生命周期 Broker task token 存入 Windows 凭据管理器，不复制 Profile，不读取或导出密码库、Cookie 或认证令牌。主前检 `check-deps.mjs --browser edge --mode existing --json` 必须确认 Edge 身份及控制探针；HTTP `/json/version` 404 不证明 CDP 不可用，WebSocket 和后台建 tab 的验证交给 `web-access`。

推荐流程：

```text
文章页 -> acquire -> 当前 Edge 内新建后台任务页
    -> Broker /access 返回脱敏访问状态
    -> 已有登录可用：寻找官方 PDF
    -> 常规登录：Broker 复用保存账号并提交，随后回读
    -> 图形/滑块/邮箱验证：web-access 页面动作/获授权邮件工具
    -> 真正短信/动态口令/刷脸/系统验证：handoff，完成后 resume
    -> Broker /download 返回完整二进制、最终 URL、长度、SHA-256
    -> 本技能核验身份/版本/PDF，Zotero 入库并回读 -> complete
```

`POST /v2/tabs/{targetId}/access` 返回 `state`、`failureCode`、`handoffRequired`、`interactionRequired`，不返回凭据。`interactionRequired` 不等于人工；能力不足或工具限制如实报告，不承诺所有验证码都能自动通过。接口缺失或未声明能力是环境/版本缺口，不能在机构模块另写登录脚本。常规登录以外的消息、申请、权限变更和付款仍须核对准确目标及授权。

| 命令或兼容状态 | 处理 |
|---|---|
| `acquire` | 创建或复用同一文章任务；先消费 `/access`，已有合法访问时直接寻找 PDF。 |
| `user_login_required` | 保留兼容状态；结合 Broker 探针确定可执行登录、能力缺口或真正 handoff，不等同于学校无订阅。 |
| `publisher_verification` | 保留兼容状态；验证执行归 `web-access`，不默认所有验证码都交给用户。 |
| `institutional_access` | 页面有机构信号，但仍未取得可核验的目标 PDF。 |
| `access_unavailable` | 保留实际站点原因；确认登录有效与明确权限拒绝后才能报告订阅不足。 |
| `downloaded_identity_verified` | 完整 PDF、正文、身份和目标版本已核验；仍须完成请求的 Zotero 入库回读。 |
| `resume` | 真正用户接管结束后恢复同一任务并回读，不把用户回复当成功证据。 |
| `complete` | 正常收尾只关闭本任务 tab/popup；不停止 Broker、Edge 或其他任务。 |

下载只通过 `POST /v2/tabs/{targetId}/download`，body 含 `url`、`timeoutMs`、`maxBytes`；同源按 scheme/host/port 判断，额外 PDF 主机须已确认，跳转及 wrapper 内层 URL 受同样约束。完整二进制、长度与 SHA-256 复核后才做 DOI/题名/版本检查；HTML 包装和截断数据不得保存为成功 PDF，不再在本模块重写 CDP/fetch/Base64 下载。

handoff 期间不得读取、截图或修改页面；未知登录提交不重复，先查原任务，不能换幂等键或另建任务猜测结果。401/403/429/418、访问检查或挑战按站点层有界处理，与 CDP 控制故障和机构订阅不足分开；文件层保留 `not_pdf`、`incomplete`、`identity_mismatch`、`too_large`、`download_timeout`。本页是流程与历史经验，不是当前真实验收或发布通过记录。

## IEEE Xplore

### 推荐路径

`文章详情页 -> Institutional Sign In -> Access Through <institution> -> stamp/stamp.jsp -> PDF`

### 经验

- 若文章详情页还显示 `You do not have access to this PDF`，说明学校权限还没真正挂上。
- `Access provided by <institution>` 是是否真正接通权限的高价值信号。
- 对受限条目，命令行直抓 `stampPDF/getPDF.jsp` 常被风控或返回包装页；浏览器内下载更稳。
- `IEEE Access` 虽然是开放获取，也优先通过文章页确认官方 PDF 链接后再下载。
- 默认复用当前 Edge 的已有会话，通过 `web-access` 在新后台任务页进入授权流程；不复制 Profile，也不为 IEEE 另开受管或临时浏览器重做登录。
- 对 IEEE，`stamp/stamp.jsp` 常是外层 HTML wrapper；真正 PDF 往往在页面里的 `iframe`、`embed` 或 `object`，例如 `stampPDF/getPDF.jsp?...`。保存时必须抓内层 PDF，并用 `%PDF-` 文件头确认。
- `Access provided by <institution>` 只作为辅助信号；最终以实际取得并通过 DOI 校验的 PDF 为准。
- 机构登录已经接通后，后续 IEEE Xplore PDF 下载通常不需要二次登录；仍需逐篇确认拿到的是 `%PDF-`，不是 `stamp/stamp.jsp` 外层 HTML。
- 登录方式与需用户参与的步骤沿用上方公开机构访问流程。
- 授权中断时保留当前浏览器页面和任务状态，用户完成验证后继续原下载，不要重新搜索导致下载到错误版本。
- 浏览器代理或出版社返回 `502 Bad Gateway`，不等于 IEEE 授权失败；先以同一页面的访问状态和 PDF 入口可见性判断。
- PDF viewer 或按钮卡住时，通过 `web-access` 的[统一下载接口](../../web-access/references/cdp-content.md#同源服务器文件字节提取)取回；不在本模块重写字节提取，不导出 Cookie 或关闭证书检查。失败保留具体状态。
- 前检的 `cdp_unreachable`、`tab_create_failed`、`proxy_version_mismatch`、`control_probe_failed` 或 `task_capacity_reached` 属控制/Broker 问题；显式隔离任务的 `managed_*` 亦单独保留，不能改写为学校未登录、出版社挑战或无订阅。

## ScienceDirect / Elsevier

### 推荐路径

`文章页 -> 机构访问 / 验证 -> View PDF -> 浏览器 PDF 下载按钮`

### 经验

- 文章页验证码和 PDF 端点验证可能是两道不同风控。
- 文章页出现学校名称且 `View PDF` 可点时，说明机构访问已经接通。
- 如果页面显示用户所属机构名称及 `Full text access` 或 `View PDF`，优先走浏览器授权下载。命令行直接抓 PDF 端点可能因为缺少浏览器 Cookie 而中断或返回网页。
- `Ctrl+S`、页面另存或命令行直接抓 `pdfft`，有时会落成 HTML 包装页而不是真 PDF。
- 对 Elsevier，优先使用浏览器内 PDF 工具栏下载。
- ScienceDirect 文件常命名为 `1-s2.0-...-main.pdf`；入库沿用 Zotero 附件命名，明确本地交付时再按项目约定命名。

## Optica / OPG

### 开放获取

- 开放获取条目常直接提供 `directpdfaccess/...pdf`。
- 这类条目优先使用官方 `directpdfaccess` 路径，不必额外绕文章摘要页。

### 机构访问

推荐路径：

`出版社机构登录 -> CARSI / OpenAthens / Shibboleth -> 学校 -> authorized copy / view_article.cfm -> directpdfaccess`

Optica 同样使用当前 Edge 的任务自有页，访问状态、常规登录与验证由 `web-access` 执行。图形/滑块验证通过页面动作，邮箱验证码通过获授权邮件工具按实际能力处理；真正短信、动态口令、刷脸或系统验证才 handoff。已有可访问内容直接复用，不强制退出或重登，不读取密码或 Cookie。

### 经验

- 常见路径是 `Publisher institutional sign-in -> CARSI / OpenAthens -> Access through <institution> -> Continue -> directpdfaccess`。
- 若页面写着 `Please wait... Your PDF will open shortly` 且明确出现
  `Brought to you by <institution>`，说明学校授权已经成功。
- 授权成功后出现 `directpdfaccess` URL，是可以保存正式 PDF 的高价值信号。
- 某些条目授权成功后，浏览器会先出现 `.crdownload`，需要等待其转正。
- 对 Optica 受限条目，优先浏览器保存，不优先走命令行抓取。

## Nature Communications

- 开放获取条目通常可直接保存官方 `.pdf`。
- 优先保留 DOI 与期刊文章页，而不是只保留 PDF 直链。

## 仓储 / 学位论文

- 仓储全文在 Zotero 条目类型、附件版本与来源中明确标识，避免误认为期刊正式 PDF。

## Edge 下载面板

- 新版 `edge://downloads/hub` 的可见文字不一定完整。
- 某些情况下，下载实际上已经开始，但页面文字不直接显示文件名。
- `.crdownload` 存在时先等待，不要立即判定失败。
- 浏览器工具能安全完成保存时继续；必须用户操作的原生对话框才交接，不把每次保存都变为人工步骤。
