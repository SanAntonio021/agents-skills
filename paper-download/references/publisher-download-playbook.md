# 论文全文入口与出版社下载参考

更新时间：2026-10-22。本文件集中维护检索渠道、机构访问与站点经验；目标版本、文件核验和完成条件以 [paper-download](../SKILL.md) 为准，通用联网与授权规则以 [web-access](../../web-access/SKILL.md) 为准。历史站点经验不代表本轮访问成功。

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

Windows 第一版支持 IEEE Xplore 和 Optica Publishing Group，使用 `scripts/institutional_access/run.ps1`。模块依赖同仓库的 `web-access`，首次运行会在 `%LOCALAPPDATA%\PaperDownload\venv` 创建独立 Python 环境。浏览器固定使用受管 Edge：Profile 为 `%LOCALAPPDATA%\web-access\managed-edge-profile`，CDP 为 `9222`，Proxy 为 `3456`；首次任务按需启动，后续任务复用同一 Broker。只有短生命周期浏览器 task token 存入 Windows 凭据管理器；学校密码、浏览器密码库、Cookie 和认证头均不读取、不保存。

推荐流程：

```text
文章页 -> acquire
    -> 已有登录：直接寻找官方 PDF
    -> 需要登录/MFA：激活同一 tab，状态 user_login_required
用户完成登录并回复
    -> resume
    -> 回读页面、尝试官方 PDF、校验 DOI/文件头/页数/哈希
    -> 入库并回读 Zotero
    -> complete
```

命令和状态：

| 命令或状态 | 处理 |
|---|---|
| `acquire` | 创建或复用同一文章任务；已有合法访问时可直接得到 PDF。 |
| `user_login_required` | 只表示页面需要用户登录；不证明账号、学校订阅或 PDF 权限。 |
| `publisher_verification` | 需要用户完成验证码或出版社安全检查。 |
| `institutional_access` | 页面有机构访问信号，但仍未找到可核验的官方 PDF。 |
| `access_unavailable` | 用户恢复后仍没有出版社权限；不得绕过。 |
| `downloaded_identity_verified` | PDF 文件头、页面、DOI 和出版社身份已通过检查。 |
| `resume` | 用户声称完成登录后必须调用；从同一浏览器 tab 回读页面。 |
| `complete` | 仅在 PDF 与 Zotero 收尾完成后关闭本任务自己的 tab；不停止 Broker、不关闭受管 Edge 或其他对话页面。 |

仅当页面为 HTTPS 登录页、用户名与密码已由浏览器填好、存在唯一同源 POST 表单和唯一提交控件且没有待确认的必选项时，模块可自动提交一次。账号或机构有歧义、出现 MFA/扫码/短信或邮件验证码、提交失败或结果未知时交给用户。页面激活后由用户确认站点并完成必要步骤；用户回复“已登录”本身不构成成功证据。

任务处于 handoff 时不得读取、截图或修改页面。未知写入先回读同一任务；不重复提交，不通过换工具或新 task 规避宿主拒绝。登录过期时保留文章身份，重新建立该任务的有效登录状态。

## IEEE Xplore

### 推荐路径

`文章详情页 -> Institutional Sign In -> Access Through <institution> -> stamp/stamp.jsp -> PDF`

### 经验

- 若文章详情页还显示 `You do not have access to this PDF`，说明学校权限还没真正挂上。
- `Access provided by <institution>` 是是否真正接通权限的高价值信号。
- 对受限条目，命令行直抓 `stampPDF/getPDF.jsp` 常被风控或返回包装页；浏览器内下载更稳。
- `IEEE Access` 虽然是开放获取，也优先通过文章页确认官方 PDF 链接后再下载。
- 首次使用时在受管 Edge 中完成学校登录，之后 Cookie 随独立 Profile 持久化；不要改用日常浏览器或另一个临时 Profile 重做登录。
- 对 IEEE，`stamp/stamp.jsp` 常是外层 HTML wrapper；真正 PDF 往往在页面里的 `iframe`、`embed` 或 `object`，例如 `stampPDF/getPDF.jsp?...`。保存时必须抓内层 PDF，并用 `%PDF-` 文件头确认。
- `Access provided by <institution>` 只作为辅助信号；最终以实际取得并通过 DOI 校验的 PDF 为准。
- 机构登录已经接通后，后续 IEEE Xplore PDF 下载通常不需要二次登录；仍需逐篇确认拿到的是 `%PDF-`，不是 `stamp/stamp.jsp` 外层 HTML。
- 登录方式与需用户参与的步骤沿用上方公开机构访问流程。
- 授权中断时保留当前浏览器页面和任务状态，用户完成验证后继续原下载，不要重新搜索导致下载到错误版本。
- 浏览器代理或出版社返回 `502 Bad Gateway`，不等于 IEEE 授权失败；先以同一页面的访问状态和 PDF 入口可见性判断。
- 浏览器 PDF viewer 或下载按钮卡住时，按 `web-access` 的已授权同源文件取回流程处理；不导出 Cookie 到命令行或关闭证书检查。取回失败时保留当前状态并报告具体缺口。
- 机构模块前检返回 `managed_profile_busy`、`managed_cdp_port_conflict`、`managed_browser_launch_failed`、`proxy_version_mismatch`、`control_probe_failed` 或 `task_capacity_reached` 时，按 Broker 故障处理；这些状态不等同于学校登录、MFA、出版社挑战或无订阅。

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

Optica 的机构访问同样使用浏览器登录交接。用户自行完成学校/CARSI/OpenAthens 登录和 MFA；工具复用同一浏览器 tab，不读取密码或 Cookie。可见的普通字母/数字图形验证码可按 `web-access` 处理，二次身份验证则交给用户。已有可访问内容直接复用当前会话，不为建立记录而强制重登。

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
