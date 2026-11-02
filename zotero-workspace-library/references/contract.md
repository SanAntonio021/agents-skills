# Zotero 执行接口契约

## 安装与连接

四个技能作为同一发布集合，先安装 `zotero-workspace-library`，再更新其余三个业务技能。安装 PDF 依赖：`python -m pip install -r <zotero-workspace-library>/requirements.txt`。使用与下载 CLI 相同 Python 环境时已有 `pypdf==6.21.2` 可复用。只读状态和查询不依赖 PDF 解析器。

连接实现从 `profiles.ini` 定位唯一 Profile，只读取必要偏好；端口按显式参数、环境 `ZOTERO_LOCAL_BASE_URL`、Profile、默认候选顺序选取一个地址。只允许 HTTP 回环地址，无代理、无重定向、无端口扫描。通过 Local API 身份与 schema 核实后才向该地址发送内存中的桥接凭据。错误只返回固定代码，不回显服务器错误或认证头。

所有命令可附 `--profile`、`--base-url`、`--timeout`（0 到 10 秒，不含 0）；扩展命令还可附 `--state-dir`、`--policy`。旧状态兼容入口保留原参数。操作目录默认 `%LOCALAPPDATA%/ZoteroLibrary/operations`，本地回执包含请求、身份依据和结果，不上传仓库。每次执行等待原生任务最多 30 秒，每次 HTTP 最多 10 秒；未知则返回，后续按原编号查询。

可用 `ZOTERO_PROFILE`、`ZOTERO_LOCAL_BASE_URL`、`ZOTERO_LIBRARY_STATE_DIR` 为同一任务绑定连接与回执位置，`finalize` 同样继承；命令显式参数优先。已设置但无效的 Profile 或地址不回退默认目标。隔离执行必须同时绑定 Profile 和地址，不能混用真实 Profile 与模拟端点。

## archive 请求

```json
{
  "schema": 1,
  "operation_id": "12345678-1234-4234-8234-123456789abc",
  "library": {"type": "user"},
  "identity": {
    "title": "Verified article title",
    "doi": "10.1234/example",
    "evidence": ["Publisher record and PDF first page checked"]
  },
  "metadata": {"itemType": "journalArticle", "date": "2026"},
  "collections": [{"path": ["Workspace", "论文"]}],
  "pdf": {
    "path": "C:/task/article.pdf",
    "version": "official",
    "evidence": ["Publisher layout and volume checked"]
  }
}
```

`schema/library/identity` 必填；`operation_id` 可省略，由连接目标与规范请求生成稳定 UUID。`library` 也可为 `{"type":"group","id":123}`。已有父条目用 `parent_key`。无 DOI 时至少提供官方 `url` 或 `creators+date`，并核实完整题名；相同题名但身份冲突或多个匹配条目会停止合并。`identity` 支持 `title/doi/url/date/creators/evidence`，作者格式沿用 Zotero creator JSON。

`metadata` 只用于新父条目，不覆盖既有条目。允许的 itemType 和字段以 `scripts/zotero_library/request.py` 白名单为准；当前支持论文、报告、标准、手册等常用资料类型。无对应原生类型的手册使用 `document`，型号、版次保留在准确题名和 evidence 中。未知字段拒绝，不静默忽略。

`collections` 默认为空；每项是 `{"key":"ABCD1234"}` 或 `{"path":["工作区","器件手册"]}`。路径中每级重名会报告歧义，不任选一个。

`pdf.sha256` 可选，执行层计算并核对；路径必须绝对路径。PDF 版本保留 `official/accepted_manuscript/preprint/temporary_preprint/unresolved`。版本证据不明时仍可如实保存 `unresolved`，不能据此宣布正式版完成。已有等价版本使用 `reuse_pdf` 替代 `pdf`，字段为 `key/sha256/version/evidence`。不传两者是仅元数据或分类归档，仍执行保护流程。

## 身份定位与交接

`find --request <请求.json>` 按相同契约只读返回 `matched/not_found/review_required`，提供候选及冲突原因。显式 key 只核实该条目，不静默换目标；未提供 key 时结合 DOI、完整题名及作者查找候选。DOI 空结果后仍查询题名与作者，不能只凭第一次空结果新建。

DOI 去首尾空白、`doi:` 与 `http(s)://(dx.)doi.org/` 前缀并转小写，保留 DOI 本体字符。完整题名按 NFKC、空白和大小写规范化后相等；请求指定作者或日期时还必须分别匹配规范姓名、角色与顺序及年份。DOI 相同但题名、作者或年份冲突仍拒绝。任一方缺 DOI 时，完整题名外须有相同官方 URL 或相同作者与年份；双方都有不同 DOI 时不能靠其他字段绕过。

唯一匹配且无未决冲突才可复用，无候选才可新建；多个匹配或尚未排除的冲突候选均停止该写入。实际内容写入前重新核对父项身份及 key，随后回读沿用相同规则。错误请求不修改库内条目、附件或集合；操作与失败回执可保留。

下载业务通过 [zotero_archive.py](../../paper-download/scripts/zotero_archive.py) 或机构 `finalize` 提交，支持 `--parent-key-source user|assistant` 和 `--required-version`。默认保护用户指定目标；只有助手交接错误、请求 PDF 身份与同库正确父项均确认且唯一时才自动纠正，返回原 key、新 key 和依据。版本要求不匹配或 PDF 身份无法确认时保留文件并返回待核状态。文本匹配是辅助检查，不能代替业务对作者、版次、出版标记和可靠来源的核实；复用已有附件同样须由业务核实内容。

纠正前查原请求回执，未知或进行中的原操作不能换 key 或编号重放。只有明确终止、设置恢复完成且确认尚未开始内容写入，才允许以新请求编号继续；旧回执不删除。默认编号取自规范化的原请求，补算文件哈希不会改变编号；同一编号不同输入拒绝。

## prune 请求

`schema/operation_id/library/identity/parent_key` 同上，另传 `keep` 和非空 `candidates`；每项均为 `key/sha256/version/evidence`。同版本冗余正文默认按 `duplicate` 处理。不同版本只有业务层确认已被目标版本替代、提供核实依据并在候选中指定 `"disposition":"superseded"` 时才可提交；执行层不替业务层判定版本关系。`keep` 不接受 disposition。版本未知或补充材料不进入候选。保留文件必须可读且哈希一致；任何候选状态未知则保留并返回 `skipped`。有父条目笔记时保守保留候选，引用该附件的独立笔记同样阻止清理。

## 回执与续做

写入返回 `operation_id/kind/state/native/readback_verified` 等字段，退出码 0 表示回读及设置恢复通过，2 表示待续或失败终态，1 表示请求、连接或依赖错误。`native.trashed` 与 `native.skipped` 分开，成功归档不等于去重全部完成。

同一操作锁防止客户端并发，Zotero 内存批次锁负责跨操作串行。相同编号与不同请求哈希拒绝。第一次网络写入前落盘，未知结果不重发。`operation status` 只查原任务与持久化结果；`resume` 在已确认终态后使用新内部 attempt 编号，重新查重补缺，保留同一公共 operation 编号。完成操作再次调用会核实原结果，不重新导入。

若原进程已结束且曾暂停偏好，回执为 `recovery_required`：设置恢复依据已丢失，不能覆盖用户现值。人工核实设置与已有结果后另立业务请求；不要删回执制造重试。活动原进程中丢失标记同样不自动重发。

## 已知插件偏好处理

随附策略记录已知插件版本及需要临时关闭的自动抓取偏好。例如：

```json
{
  "schema": 1,
  "addons": [{
    "id": "reviewed-addon@example.invalid",
    "version": "1.2.3",
    "preference_keys": ["extensions.zotero.reviewed.automatic_pdf_download"],
    "evidence": "Reviewed this installed version: this boolean gates all automatic new-item fetches"
  }]
}
```

策略接受完整全局偏好名；拒绝 token、auth、password 等字段。执行时读取实际布尔值，监听同步偏好通知，仅恢复仍归本次所有的临时设置；外部变化停止后续写入并保留当前值。

未提供 `--policy` 时，执行层使用技能随附的 `references/automatic_fetch_policy.json`；显式指定时使用该策略。只有插件 ID 和版本都匹配时才应用对应偏好键。未知插件、插件新增或版本变化不会阻止写入，也不会推断或读取未知偏好；这些插件不受此项临时偏好控制。原生写入仍检查目标条目、文件、集合、批次所有权和回读结果。

## 实现依据与限制

原生 API 根据 Zotero 官方源码的 `server_localAPI.js`、`data/item.js`、`prefs.js` 和 `plugins.js` 核对：Local API 个人库路径使用 `users/0`，群组转换使用真实 library 对象；偏好观察器接收完整全局键时使用 `global=true`。文件哈希使用原生 SHA-256 文件流，PDF 嵌入批注由 Python 解析。真实插件可能移动文件或改变条目时，回读不一致会报告失败，不伪装成功或覆盖原内容。
