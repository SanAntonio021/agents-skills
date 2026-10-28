# 文件、媒体与 iframe 内容提取

先读 [CDP 文档入口](cdp-api.md)。本页只处理页面资源取回和内容类型核验；页面交互见 [交互参考](cdp-interaction.md)，task 收尾见 [生命周期参考](cdp-lifecycle.md)。

## 文件与媒体资源入口

- 公开 URL 或站点下载动作能返回目标资源时，保存服务器文件字节；登录资源优先用站点已有下载动作。
- 自有 tab 已到达文件 URL、却未产生可用下载时，按 [同源服务器文件字节提取](#同源服务器文件字节提取) 取回完整响应并校验。此方法只用于公开或当前已授权内容。
- 原件取不到而目标图片已完整加载时，按 [自然尺寸图片像素导出](#自然尺寸图片像素导出) 处理；canvas 重新编码与原始服务器字节分开标识。
- 页面状态或视频当前帧用 `/screenshot`；必要时经鉴权的 `/eval` 操作 `<video>` 后取帧。截图不能冒充图片原件。截图端点仅返回字节，调用方选择保存位置，不向 Proxy 传任意本机路径。

分块和总量边界、同源条件及完整性核验采用下方流程。交付按实际需要说明文件来源与限制，不把 Base64、token 或会话地址输出给用户。

## Screenshot

### `GET /v2/tabs/{targetId}/screenshot`

Query 可选 `format=png|jpeg`。响应是图片二进制；`file` query 被拒绝，保存位置由调用方决定。

## 同源服务器文件字节提取

PDF 统一通过 `POST /v2/tabs/{targetId}/download` 取回，由 `web-access` Broker 在当前 Edge 的 task 自有页面执行；业务技能不通过 `/eval` 再实现 fetch、Base64 分块或 CDP 下载。接口与头字段见 [下载契约](cdp-protocol.md#post-v2tabstargetiddownload)。本节保留原锚点，供已有引用继续使用；它不是绕过登录、付费或站点权限的方法。

1. 回读 task 自有页的最终 URL、访问状态及预期资源。默认使用当前 Edge 的已有会话；需要登录或验证时先调用 `/access`，按 [访问契约](cdp-protocol.md#post-v2tabstargetidaccess) 交给 `web-access` 处理。只在当前浏览器内复用会话，不复制 Profile、Cookie、密码或认证令牌。
2. 发送 Bearer task token、JSON body 与幂等键，body 包含准确 `url`、`timeoutMs`、`maxBytes`。同源须包含 scheme/host/port；跨源只允许已经确认的出版社 PDF 主机，通过 `allowedHosts` 传入。跳转及 wrapper 内层链接仍须校验，不猜签名参数、不先请求未确认主机。
3. Broker 在有限超时和大小预算内读取响应，检查 HTTP 状态、PDF 文件头及完整长度；HTML wrapper 只能用于定位受同一策略约束的实际 PDF，不能直接作为 PDF 返回。流中断、超限或超时取消请求并清理暂存，不写半截文件。上限以 `/capabilities.download` 为准，不在调用方复制另一套下载实现。
4. 只接收完整二进制与最终 URL、字节数、SHA-256。客户端 URL 解码 `X-Download-Final-Url`，复核 `%PDF-`、`X-Download-Bytes` 与 `X-Download-Sha256`；再按任务用 PDF 解析器检查页数、可读性及正文，论文身份/DOI/版本由 `paper-download` 核验。全部通过后才保存至目标位置，不能仅凭 MIME 或文件后缀认定成功。
5. 下载返回 `UNKNOWN_RESULT` 时保留同一 task 与幂等键，先查原请求/任务状态，不换 key 原样重放。401/403/429/418 或检查页保留站点原因；`not_pdf`、`incomplete`、`too_large`、`download_timeout` 保留文件原因，身份不匹配不能入库。不要把它们改写为 CDP 故障或学校无订阅。

这是完整服务器响应字节，不同于 canvas 重新编码或截图。最终 URL 可能含签名，只保留任务必需的内部元数据，不把认证参数、token 或二进制块输出到聊天、日志。非 PDF 媒体不冒用此 PDF 专用接口；使用站点现有下载或宿主已提供的资源接口，缺能力时说明，不在领域技能中新增通用字节提取器。

## 自然尺寸图片像素导出

仅在服务器文件字节无法取得、但目标图片已经在 task 自有页面中完整加载时使用。它通过 `/eval` 读取页面已解码像素，不是下载管理，也不能绕过资源权限。

固定顺序：

1. 用只读表达式返回目标元素的 `currentSrc`、`complete`、`naturalWidth`、`naturalHeight` 和解析后的资源 origin。`complete !== true` 或自然尺寸为 0 时先等待，不导出占位图。
2. 同源图片可以进入 canvas。跨域图片只有页面已使用明确 CORS 且探测画布保持 origin-clean 时才可继续；`drawImage` 或 `toDataURL` 抛出 `SecurityError` 时立即停止，不修改浏览器安全策略、不代理凭据。
3. 创建与自然尺寸相同的 canvas，执行 `drawImage(img, 0, 0)` 和 `toDataURL('image/png')`。把去掉前缀后的 Base64 暂存在页面内一个任务级随机键下；首次 `/eval` 只返回 MIME、宽高、编码字符数和可选 SHA-256，不返回整段内容。
4. 调用前固定边界。默认每块最多 `262144` 个 Base64 字符，总量最多 `67108864` 个字符；超过上限先停止并报告，不能无界取回。按偏移量逐块读取，校验块序号、总字符数和结尾，不把块内容打印到用户可见输出。
5. 在本地按顺序拼接并一次解码，复核 PNG 签名、宽高、文件大小和 SHA-256；随后用 `/eval` 清除页面暂存值。缺块、重复块、长度或哈希不符时丢弃候选，不用不完整数据补图。

canvas 结果必须标为“浏览器像素导出并重新编码”。只有直接取得服务器响应字节时，才可标为原始文件字节。`/eval` 返回 `UNKNOWN_RESULT` 时，先用新的只读表达式检查随机键和已生成元数据；不得换幂等 key 原样重跑创建动作。分块读取的不确定结果使用原幂等 key 重放，仍无法确认时停止。

## iframe 正文读取

在任务自有页面正文位于跨域 iframe 时，先用 `GET /v2/tabs/{id}/frames`（Bearer task token）列出该页面主文档的直接 iframe，再用 `POST /v2/tabs/{id}/frame-text`，JSON 为 `{"frameId":"列表中的 frameId"}`，带同一 token 与新幂等键读取标题、当前 URL 和最多 100000 字符正文。

此回退只读取文本，不接受任意表达式、坐标或点击。每次重新验证 frame 属于当前 task 自有页；跨进程 iframe 使用子 session 的隔离 world，同进程 iframe 使用页面 session 的对应 world。列表不覆盖嵌套 iframe 或 shadow root，未加载 frameId 为 null；目标改变或不可用时重新列举，不猜 target ID。登录与访问限制统一交给 `/access` 和 `web-access` 页面动作；图形/滑块/邮箱验证不默认 handoff，真正短信、动态口令、刷脸或系统验证才交还用户。iframe 可读不证明授权成功或已完成身份验证。
