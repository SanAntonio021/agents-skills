# Publisher Download Playbook

更新时间：2026-09-15（修订正式版目标与本机助手入口；历史站点经验不代表本轮重新实测）

## 用途

给 `paper-download` 提供可复用的站点级下载经验，重点沉淀：

- 哪些站点优先用真实浏览器
- 哪些站点的“文章页可访问”不等于“PDF 端点可直接抓”
- 下载后如何快速判断拿到的是不是正文 PDF

## 统一检查顺序

1. 查 Zotero 条目及附件，并对照出版社当前文章页核实版本。已取得当前正式版才可直接复用。
2. 先取公开的当前正式 PDF；直链风控、包装页或工具故障时，检查已配置的浏览器及机构访问，不直接退到预印本。
3. 通过本机助手或当前获准工具实际尝试机构渠道；同一站点可复用一次已验证的机构会话，逐篇核对 PDF。
4. 区分页面明确拒绝权限、需要用户验证、服务未启动和工具故障。后两项不构成无机构权限的证据；工具不可继续时记录阻塞，正式版仍待补。
5. 校验 `%PDF-` 文件头、题名、作者、DOI、正文页数和版本标记。真 PDF 也可能只是封面、整期、错误通知或未编辑作者稿；必要时从整期提取单篇并记录原页范围。
6. 合法临时稿可以保存供阅读，但“已有 PDF”不等于“已获正式版”。按主入口的版本与完成状态报告。

## 本机 PaperAccess 助手

在 Windows 上，从启动环境展开 `LOCALAPPDATA`，核实其为非空绝对目录，定位 `PaperAccess/paper_access.py`；不要把环境变量名称当作已解析路径，也不要猜用户名或改回任务过程目录中的旧脚本。其他平台或入口不存在时，按本机配置发现可用能力，明确报告缺项。

```powershell
$paperAccessRoot = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($paperAccessRoot) -or -not [IO.Path]::IsPathRooted($paperAccessRoot)) {
    throw 'LOCALAPPDATA is missing or is not an absolute path.'
}
$paperAccessScript = Join-Path $paperAccessRoot 'PaperAccess/paper_access.py'
if (-not (Test-Path -LiteralPath $paperAccessScript -PathType Leaf)) {
    throw 'Configured PaperAccess entry is unavailable.'
}
# 使用本机已核实的 Python 解释器执行该入口，先读取 --help。
```

助手命令按以下职责使用；参数、session 创建/传递方式和实际可用命令以本机 `--help` 为准，不凭本文拼造接口：

| 命令 | 用途 |
|---|---|
| `check` / `start` | 检查配置、浏览器服务和连接状态；需要时启动已配置服务，再复查。 |
| `login` | 在核实的机构入口和已有授权范围内复用或建立登录。 |
| `status` / `snapshot` | 读取同一任务 session 的状态及已脱敏页面信息，不读取账号密码字段值。 |
| `navigate` / `download` | 在该 session 内前往已确认的论文页面并取得官方 PDF。 |
| `resume` | 用户验证或工具恢复后，接续原 session 和待下载文章。 |
| `complete` | 下载核验及请求的入库/交付完成后结束会话；其返回成功不能替代 PDF 与 Zotero 验收。 |

个人账号、机构配置和操作系统凭据目标只放在本机 `PaperAccess/config.json`，不得写入公开技能、项目材料或命令参数；密码由配置指向的系统凭据库管理，不能存于该 JSON。助手只返回脱敏状态，模型不读取或转储私有配置。入口存在不等于服务运行、登录成功或拥有文章权限，按实际返回逐层核对。

Windows 受限进程可能看不到宿主用户的凭据条目；此时“不可用”不等于凭据未配置。沿宿主支持的审批流程核实同一用户上下文，不能改凭据权限、另建账号或导出密码来排错。解释器须满足助手的 PDF 读取依赖（如 pypdf），优先使用本机已配置且核实可用的运行时；参数帮助成功不代表下载依赖齐全。

预检应使用实际准备执行下载的同一解释器，并检查 `pdf_reader_available` 等依赖结果；缺少 pypdf 属于环境未就绪，不宣称预检完成。优先复用本机已核实且具备依赖的运行时，不为一次失败修改公共解释器；Windows 输出包含中文或特殊字符时启用 UTF-8。

填充接口报错不一定意味着页面字段仍为空。已有 `fillAttempted`、尚无 `submitAttempted` 时，由本机助手重新核实学校 HTTPS origin、登录路径、账号与配置精确匹配、密码非空、同源表单及唯一可见登录控件；对外只返回布尔状态。全部满足才先持久化提交标记、再提交一次；否则停下检查，不清标记或盲目重填。登录控件可能是链接（如 `a#login_submit`）而非 button，须按当前页面核实。已提交却仍停在登录页时不得重复提交。`ACTION_VERIFY_FAILED`、`DIALOG_OPEN` 等固定错误码仅用于定位失败阶段，响应中的字段值和未知错误码仍须脱敏。

所有命令仍受当前宿主工具与权限约束。若宿主禁止某种浏览器/网络操作，不得借助手、脚本或其他通道绕过；记录阻塞并继续不依赖该操作的工作。不得关闭证书校验或导出 Cookie/令牌来修复下载。

若助手返回 `consent_scope_review`，由执行智能体在当前获准工具中核对页面接收方及发布属性，和会话已有授权比较。相同范围继续已有授权，不自动再次问用户；新范围或工具强制确认才交接。仅有该状态不代表范围已核实或同意已提交，不凭页面标题盲点同意。

## 机构授权边界

- 优先复用浏览器已有登录态和自动填充；核对真实机构页面、账号及填充就绪状态后继续，不读取输入值或导出浏览器凭据。网页工具不能访问的原生保存信息下拉框，不视为已支持。
- 已有准确授权及本机安全凭据助手时，可后台登录指定站点和账号。首次配置由用户授权后在本机安全输入窗口录入，凭据存于操作系统凭据库；助手仅在本机进程内读取并传给核实过的 HTTPS 登录表单，对外只返回就绪和登录状态。不要在聊天中索要密码、提取浏览器密码库，或把凭据放进参数、源码、日志及共享目录。按上方稳定入口发现本机助手，不把一台机器已配置视为其他机器也可用。
- 扫码、验证码、短信/邮箱验证及未配置安全助手时的凭据输入由用户完成。新服务条款、信息发布接收方或范围需具体授权；已授权的同一接收方及范围继续复用，不能扩成“向所有服务发布所有信息”。购买、申请全文或新增权限绑定另按具体授权处理。
- 如果工具新开的浏览器没有登录态，不要直接判定失败；先改用已登录浏览器会话，或让用户在这个浏览器里完成一次授权。
- 授权成功后仍要验证文件头。机构网页能打开，不等于命令行直抓的文件就是真 PDF。

## IEEE Xplore

### 推荐路径

`文章详情页 -> Institutional Sign In -> Access Through <institution> -> stamp/stamp.jsp -> PDF`

未使用本机 PaperAccess、且当前允许使用 `paper-search-mcp` 时的路径：

`DOI/文章详情页 -> download_with_authorization -> 机构 WAYF -> 已登录浏览器会话 -> stamp/stamp.jsp -> iframe 中的 stampPDF/getPDF.jsp`

### 经验

- 若文章详情页还显示 `You do not have access to this PDF`，说明学校权限还没真正挂上。
- `Access provided by <institution>` 是是否真正接通权限的高价值信号。
- 对受限条目，命令行直抓 `stampPDF/getPDF.jsp` 常被风控或返回包装页；浏览器内下载更稳。
- `IEEE Access` 虽然是开放获取，也优先通过文章页确认官方 PDF 链接后再下载。
- 若本机日常浏览器已经有学校登录态，优先复用该浏览器会话；MCP 单独启动的新浏览器资料目录可能没有账号、Cookie 和机构登录状态。
- 对 IEEE，`stamp/stamp.jsp` 常是外层 HTML wrapper；真正 PDF 往往在页面里的 `iframe`、`embed` 或 `object`，例如 `stampPDF/getPDF.jsp?...`。保存时必须抓内层 PDF，并用 `%PDF-` 文件头确认。
- 页面机构名称须与本机配置对应；机构名称与 Shibboleth/CARSI entityId 从本机配置使用，不硬编码到公开技能。
- 机构登录已经接通后，后续 IEEE Xplore PDF 下载通常不需要二次登录；仍需逐篇确认拿到的是 `%PDF-`，不是 `stamp/stamp.jsp` 外层 HTML。
- 登录方式与需用户参与的步骤沿用上方机构授权边界。
- 授权中断时保留 MCP checkpoint，用户完成授权后用 `retry_authorized_download` 继续，不要重新搜索导致下载到错误版本。
- `download_with_authorization` 或浏览器代理返回 `502 Bad Gateway`，不等于 IEEE 授权失败；先以已登录浏览器页面的 `Access provided by <institution>` 和 PDF 入口可见性判断授权状态。
- 浏览器 PDF viewer 或下载按钮卡住时，按 `web-access` 的已授权同源文件取回流程处理；不导出 Cookie 到命令行或关闭证书检查。取回失败时保留当前状态并报告具体缺口。

## ScienceDirect / Elsevier

### 推荐路径

`文章页 -> 机构访问 / 验证 -> View PDF -> 浏览器 PDF 下载按钮`

### 经验

- 文章页验证码和 PDF 端点验证可能是两道不同风控。
- 文章页出现学校名称且 `View PDF` 可点时，说明机构访问已经接通。
- 如果页面显示与本机配置一致的机构名称及 `Full text access` 或 `View PDF`，优先走浏览器授权下载。命令行直接抓 PDF 端点可能因为缺少浏览器 Cookie 而中断或返回网页。
- `Ctrl+S`、页面另存或命令行直接抓 `pdfft`，有时会落成 HTML 包装页而不是真 PDF。
- 对 Elsevier，优先使用浏览器内 PDF 工具栏下载。
- ScienceDirect 文件常命名为 `1-s2.0-...-main.pdf`；入库沿用 Zotero 附件命名，明确本地交付时再按项目约定命名。

## Optica / OPG

### 开放获取

- 开放获取条目常直接提供 `directpdfaccess/...pdf`。
- 这类条目优先使用官方 `directpdfaccess` 路径，不必额外绕文章摘要页。

### 机构访问

推荐路径：

`China CARSI Member Access -> 学校 -> authorized copy / view_article.cfm -> directpdfaccess`

### 经验

- 常见路径是 `China CARSI Member Access -> Access through <configured institution> -> Continue -> directpdfaccess`。
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

## 命名与登记

- Zotero 为统一文献库，附件沿用库内命名设置。明确导出本地且无项目约定时用“年份-期刊名-标题名.pdf”。
- 同一篇多版本时加最小后缀：
  - `(official)`
  - `(accepted-manuscript)`
  - `(temporary-preprint)`
  - `(arXiv)`
- 默认在 Zotero 条目及附件中保留题名、DOI、来源和版本。有明确本地索引要求时才沿用索引，至少记录：
  - 题名
  - 本地文件名
  - DOI 或正式入口
  - 下载版本
  - 是否只是临时预印本
  - 备注
