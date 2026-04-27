# Publisher Download Playbook

更新时间：2026-04-27

## 用途

给 `paper-reading` 提供可复用的站点级下载经验，重点沉淀：

- 哪些站点优先用真实浏览器
- 哪些站点的“文章页可访问”不等于“PDF 端点可直接抓”
- 下载后如何快速判断拿到的是不是正文 PDF

## 统一检查顺序

1. 先补 DOI、出版社页和正式发表线索。
2. 先判断是否已有正式发表版本；已发表论文优先拿正式版。
3. 正式版暂时拿不到时，才用预印本兜底，并在索引里标 `temporary_preprint`。
4. 再判断 `open` / `institutional` / `request-only`。
5. 能公开直下的先下。
6. 受限站点优先接通学校或机构访问，再批量处理同站点条目。
7. 下载后先查文件头：
   - `%PDF-`：真 PDF
   - `<!doc` 或其他 HTML 开头：包装页、验证码页或错误页
8. 文件明显偏小但扩展名是 `.pdf` 时，优先怀疑不是正文。

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
- 登录页出现扫码、验证码、账号密码或二次确认时，只让用户本人完成这一步；不要替用户输入凭据，也不要绕过权限。
- 授权中断时保留 MCP checkpoint，用户完成授权后用 `retry_authorized_download` 继续，不要重新搜索导致下载到错误版本。

## ScienceDirect / Elsevier

### 推荐路径

`文章页 -> 机构访问 / 验证 -> View PDF -> 浏览器 PDF 下载按钮`

### 经验

- 文章页验证码和 PDF 端点验证可能是两道不同风控。
- 文章页出现学校名称且 `View PDF` 可点时，说明机构访问已经接通。
- `Ctrl+S`、页面另存或命令行直接抓 `pdfft`，有时会落成 HTML 包装页而不是真 PDF。
- 对 Elsevier，优先使用浏览器内 PDF 工具栏下载。
- ScienceDirect 官方文件常默认命名成 `1-s2.0-...-main.pdf`，下载后要立即重命名。

## Optica / OPG

### 开放获取

- 开放获取条目常直接提供 `directpdfaccess/...pdf`。
- 这类条目优先使用官方 `directpdfaccess` 路径，不必额外绕文章摘要页。

### 机构访问

推荐路径：

`China CARSI Member Access -> 学校 -> authorized copy / view_article.cfm -> directpdfaccess`

### 经验

- 若页面写着 `Please wait... Your PDF will open shortly` 且明确出现
  `Brought to you by <institution>`，说明学校授权已经成功。
- 某些条目授权成功后，浏览器会先出现 `.crdownload`，需要等待其转正。
- 对 Optica 受限条目，优先浏览器保存，不优先走命令行抓取。

## Nature Communications

- 开放获取条目通常可直接保存官方 `.pdf`。
- 优先保留 DOI 与期刊文章页，而不是只保留 PDF 直链。

## 仓储 / 学位论文

- 仓储全文要在索引里标明“仓储页面”或“学位论文 PDF”，避免误认为是期刊文章官方 PDF。

## Edge 下载面板

- 新版 `edge://downloads/hub` 的可见文字不一定完整。
- 某些情况下，下载实际上已经开始，但页面文字不直接显示文件名。
- `.crdownload` 存在时先等待，不要立即判定失败。
- 若浏览器停在 `保存 / 另存为 / 打开` 选择，优先让用户只做“点保存”这一步。

## 命名与索引

- 默认用“年份-期刊或会议全称-题名.pdf”。
- 同一篇多版本时加最小后缀：
  - `(official)`
  - `(accepted-manuscript)`
  - `(temporary-preprint)`
  - `(arXiv)`
- 建议索引至少记录：
  - 题名
  - 本地文件名
  - DOI 或正式入口
  - 下载版本
  - 是否只是临时预印本
  - 备注
