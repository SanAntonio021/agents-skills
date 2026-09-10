# Publisher Download Playbook

更新时间：2026-09-10（流程调整；历史站点事实未重新实测）

## 用途

给 `paper-download` 提供可复用的站点级下载经验，重点沉淀：

- 哪些站点优先用真实浏览器
- 哪些站点的“文章页可访问”不等于“PDF 端点可直接抓”
- 下载后如何快速判断拿到的是不是正文 PDF

## 统一检查顺序

1. 先查 Zotero 已有条目和附件，复用 DOI、出版社页和核实结果；缺少所需版本才下载。
2. 先判断是否已有正式发表版本；已发表论文优先拿正式版。
3. 正式版暂时拿不到时，才用预印本兜底，在 Zotero 附件标题和版本说明中标 `temporary_preprint`。
4. 再判断 `open` / `institutional` / `request-only`。
5. 能公开直下的先下。
6. 受限站点优先接通学校或机构访问，再批量处理同站点条目。
7. 下载后先查文件头：
   - `%PDF-`：真 PDF
   - `<!doc` 或其他 HTML 开头：包装页、验证码页或错误页
8. 文件明显偏小但扩展名是 `.pdf` 时，优先怀疑不是正文。

## 机构授权边界

- 复用浏览器已有登录态和自动填充；真实机构页面、账号与机构已明确且填充就绪时，继续点击登录及授权入口，不读取输入值、不导出密码、Cookie 或令牌。
- 手工凭据输入、扫码、验证码、短信/邮箱验证由用户完成；购买、申请全文或新增权限绑定另按具体授权处理。
- 如果工具新开的浏览器没有登录态，不要直接判定失败；先改用已登录浏览器会话，或让用户在这个浏览器里完成一次授权。
- 授权成功后仍要验证文件头。机构网页能打开，不等于命令行直抓的文件就是真 PDF。

## IEEE Xplore

### 推荐路径

`文章详情页 -> Institutional Sign In -> Access Through <institution> -> stamp/stamp.jsp -> PDF`

使用 `paper-search-mcp` 时优先路径：

`DOI/文章详情页 -> download_with_authorization -> 机构 WAYF -> 已登录浏览器会话 -> stamp/stamp.jsp -> iframe 中的 stampPDF/getPDF.jsp`

### 经验

- 若文章详情页还显示 `You do not have access to this PDF`，说明学校权限还没真正挂上。
- `Access provided by <institution>` 是是否真正接通权限的高价值信号。
- 对受限条目，命令行直抓 `stampPDF/getPDF.jsp` 常被风控或返回包装页；浏览器内下载更稳。
- `IEEE Access` 虽然是开放获取，也优先通过文章页确认官方 PDF 链接后再下载。
- 若本机日常浏览器已经有学校登录态，优先复用该浏览器会话；MCP 单独启动的新浏览器资料目录可能没有账号、Cookie 和机构登录状态。
- 对 IEEE，`stamp/stamp.jsp` 常是外层 HTML wrapper；真正 PDF 往往在页面里的 `iframe`、`embed` 或 `object`，例如 `stampPDF/getPDF.jsp?...`。保存时必须抓内层 PDF，并用 `%PDF-` 文件头确认。
- 如果页面显示 `Access provided by: University of Electronic Science and Tech of China`，说明电子科大机构权限已经接通，可以继续点 `PDF` 或让 MCP 抓内层 PDF。
- 已验证的电子科大 Shibboleth/CARSI entityId 是 `https://idp-lib.uestc.edu.cn/idp/shibboleth`。这是机构入口配置，不是账号密码。
- 机构登录已经接通后，后续 IEEE Xplore PDF 下载通常不需要二次登录；仍需逐篇确认拿到的是 `%PDF-`，不是 `stamp/stamp.jsp` 外层 HTML。
- 登录页已由浏览器自动填充且账号机构明确时可继续点击登录；只有需要手工凭据输入、扫码、验证码或二次验证时交给用户。
- 授权中断时保留 MCP checkpoint，用户完成授权后用 `retry_authorized_download` 继续，不要重新搜索导致下载到错误版本。
- `download_with_authorization` 或浏览器代理返回 `502 Bad Gateway`，不等于 IEEE 授权失败；先以已登录浏览器页面的 `Access provided by <institution>` 和 PDF 入口可见性判断授权状态。
- 浏览器 PDF viewer 或下载按钮卡住时，按 `web-access` 的已授权同源文件取回流程处理；不导出 Cookie 到命令行或关闭证书检查。取回失败时保留当前状态并报告具体缺口。

## ScienceDirect / Elsevier

### 推荐路径

`文章页 -> 机构访问 / 验证 -> View PDF -> 浏览器 PDF 下载按钮`

### 经验

- 文章页验证码和 PDF 端点验证可能是两道不同风控。
- 文章页出现学校名称且 `View PDF` 可点时，说明机构访问已经接通。
- 如果页面显示 `University of Electronic Science and Technology of China`、`Full text access` 或 `View PDF`，优先走浏览器授权下载。命令行直接抓 PDF 端点可能因为缺少浏览器 Cookie 而中断或返回网页。
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

- 对电子科大，常见路径是 `China CARSI Member Access -> Access through 电子科技大学 -> Continue -> directpdfaccess`。
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
