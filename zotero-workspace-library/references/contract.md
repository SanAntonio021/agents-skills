# Zotero 执行接口契约

## 引用与导出

`export --keys <key...>` 输出实际 BibTeX 和 item key／citation key 映射；可用 `--output <绝对路径.bib>` 合并。读取默认个人库，群组用 `--group`。保留已有内容，只追加缺失项；同键不同内容返回 `state=conflict` 及差异，退出码 2。

`cite --request` 接受下例，所有字段必填，不接收凭据或代码。`target.path` 与 `bibliography` 必须为绝对路径；`anchor` 必须在文稿中只出现一次，`placement` 为 `before/after`，`style` 为 `markdown/latex`。

```json
{
  "schema": 1,
  "library": {"type": "user"},
  "keys": ["ABCD1234"],
  "style": "markdown",
  "target": {"path": "<绝对路径>/draft.md", "anchor": "<!--reference-->", "placement": "after"},
  "bibliography": "<绝对路径>/references.bib"
}
```

引用键逐条取实际导出结果，插入 `[@key]` 或 `\cite{key}`，多项保持请求顺序。重复请求检查同一锚点相邻引用；不重复追加。不改已有 `.bib` 条目。UTF-8 BOM 与文稿换行保留；文件被修改时停止覆盖。先合并 `.bib` 再插文稿，若第二步受阻，保留已导出的条目，重试同一请求即可。

LaTeX 使用正文位置或以 `%` 开头的完整注释锚点配合 `placement=before`；插入点位于行注释中时返回 `citation_position_commented`，文稿和 `.bib` 均不写入。

## 分页阅读与阅读内容检索

`read --key <论文或PDF附件key> [--attachment <key>] [--pages 1-3,6] [--max-chars 30000]` 返回论文、附件、物理页码、页标签、文字、截断、OCR 状态及未读页数。默认前十页，每次最多一百页；多份 PDF 需明确选定。`ocr_required` 退出码 2；扫描件不静默返回空全文。未安装 PDF 依赖返回 `pdf_dependency_missing`。

`search --query <文字> --scope all/notes/annotations/fulltext [--limit 100]` 中 `all` 表示笔记与批注。阅读检索返回所属论文、附件、物理页码及页标签，未知项为 null；`fulltext` 复用 Zotero 的已有全文索引并说明覆盖范围。

## 官方写入与旧操作兼容

唯一连接路线是固定 CLI → Python `zotero_library` → Zotero 官方 Local API。新回执含 `executor_version=2`、`backend=local_api`、`database_id`、固定 `api_keys`、`api_stages` 和阅读内容快照。第一次网络写入前保存意图，确认后记录阶段完成；上传 key、上传地址和授权值只留内存。

授权使用 `/api/local/authorize`，长期凭据存 Windows 凭据管理器。一次授权被消费后，下次写入另行申请。401 清除该客户端凭据但不自动重放；403、结果未知或数据库切换同样停止当前步骤。凭据目标仍由连接绑定与数据库身份计算。

PDF 采用 imported_file 占位、上传准备、原始字节、登记四步；协议 MD5 与文件 SHA-256 分别核实。未知结果先查固定对象与文件，已完成步骤不再执行；缺项仅在固定 key、版本条件及文件状态能保证安全时补做。旧完成回执只读回验；未派发操作迁移；旧未知操作核实原进程身份及库内结果，不能恢复旧桥执行器。

## 安装与连接

先安装 `zotero-workspace-library`，再更新三个业务技能。Python 3.10+，PDF 检查依赖 `requirements.txt`；只读状态与元数据查询不依赖 PDF 解析器。

Profile 从 `profiles.ini` 选择唯一候选，只读取 API 启用与端口配置。端口优先级：显式参数、`ZOTERO_LOCAL_BASE_URL`、Profile 端口、默认候选。只使用一个 HTTP 回环地址，无代理、无重定向、无端口扫描。根响应和 schema 核实身份；每次响应检查稳定数据库标识。错误仅返回固定代码。

所有命令接受 `--profile`、`--base-url`、`--timeout`、`--state-dir`、`--policy`；`--policy` 仅保留兼容，不读策略。`--timeout` 为单次请求等待（0 到 10 秒，不含 0）；授权弹窗请求最多 120 秒。超时不证明服务器操作结束，须查询原编号。默认回执目录为 `%LOCALAPPDATA%/ZoteroLibrary/operations`。同库公共锁与未决记录位于固定的本机数据库协调目录，不随 `--state-dir` 变化。

`ZOTERO_PROFILE`、`ZOTERO_LOCAL_BASE_URL`、`ZOTERO_LIBRARY_STATE_DIR` 也绑定下载 `finalize`，显式参数优先；无效配置不回退。隔离执行同时绑定 Profile 和地址。`status` 不弹窗，分别报告 `read_only_ready/local_api_write_supported/local_api_authorization_present`；旧桥字段为 null、不再适用。

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

## 既有集合移动或改名

`collection plan/update --request` 管理一个已存在的集合。请求必须固定用户库或群组库、集合 key，以及执行前读到的版本、名称和父集合；`false` 表示顶层。`name` 和 `parentCollection` 是可选目标字段，至少提供一项。计划命令只读，检查目标父集合存在、没有同级重名和循环引用；执行命令使用 Zotero 集合更新接口提交并按 key 回读。

```json
{
  "schema": 1,
  "library": {"type": "user"},
  "key": "ABCD1234",
  "expected_version": 42,
  "expected_name": "Old collection name",
  "expected_parent": false,
  "name": "论文",
  "parentCollection": "EFGH5678"
}
```

更新只改这一个集合的名称和/或父集合；不修改其中的条目关联、附件、笔记、标签或子集合。执行前若集合版本、名称或父集合与请求不符，返回 `collection_state_changed_requires_review`；遇到同级重名或循环引用则拒绝写入。相同目标再次执行为幂等无操作。先运行 `collection plan` 检查回执，再使用相同请求运行 `collection update`。

`pdf.sha256` 可选，执行层计算并核对；路径必须绝对路径。PDF 版本保留 `official/accepted_manuscript/preprint/temporary_preprint/unresolved`。版本证据不明时仍可如实保存 `unresolved`，不能据此宣布正式版完成。已有等价版本使用 `reuse_pdf` 替代 `pdf`，字段为 `key/sha256/version/evidence`。不传两者是仅元数据或分类归档，仍执行保护流程。

## 身份定位与交接

历史父条目缺作者、日期、URL 时，读取其原 PDF 并核实题名、型号与版本后，可在 archive 请求中用已有附件作为独立证据：

```json
{
  "parent_key": "ABCD1234",
  "identity": {"title": "Exact existing title", "evidence": ["Existing PDF and supplied manual first pages checked; exact model and document identity match."]},
  "parent_pdf_evidence": {
    "key": "EFGH5678",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "evidence": ["Existing PDF cover identifies the manufacturer and exact model; metadata fields are absent."]
  }
}
```

这是完整请求中的字段片段；仍需 `schema`、`library` 等字段。只能绑定显式父 key，且题名仍须一致。执行层重读原附件，验证 PDF 类型、未删除状态、所属父条目、SHA-256 与可读性，只补足缺少的独立证据；真实的题名、DOI、作者和年份冲突仍拒绝。不会自动补写厂家或发布日期。已有参数不同的 PDF 保留，新附件在同一父条目下另存并回读，不覆盖原文件或批注。

`find --request <请求.json>` 按相同契约只读返回 `matched/not_found/review_required`，提供候选及冲突原因。显式 key 只核实该条目，不静默换目标；未提供 key 时结合 DOI、完整题名及作者查找候选。DOI 空结果后仍查询题名与作者，不能只凭第一次空结果新建。

DOI 去首尾空白、`doi:` 与 `http(s)://(dx.)doi.org/` 前缀并转小写，保留 DOI 本体字符。完整题名按 NFKC、空白和大小写规范化后相等；请求指定作者或日期时还必须分别匹配规范姓名、角色与顺序及年份。DOI 相同但题名、作者或年份冲突仍拒绝。任一方缺 DOI 时，完整题名外须有相同官方 URL 或相同作者与年份；双方都有不同 DOI 时不能靠其他字段绕过。

唯一匹配且无未决冲突才可复用，无候选才可新建；多个匹配或尚未排除的冲突候选均停止该写入。实际内容写入前重新核对父项身份及 key，随后回读沿用相同规则。错误请求不修改库内条目、附件或集合；操作与失败回执可保留。

同厂家、同年份只用于找候选，不能据此认定两份型号手册相同。业务层读取双方原件、确认是不同资料后，可在 archive 请求中加入下列字段；`find --request` 的候选摘要提供准确的 `version`。助手自行完成核验，不把可从原件确定的问题交回用户。

```json
{
  "distinct_candidates": [{
    "key": "ABCD1234",
    "version": 42,
    "title": "Manufacturer A100 bare-die datasheet",
    "evidence": ["Both PDF first pages checked: existing A100 bare die and requested M100 module have distinct model numbers and interfaces."]
  }]
}
```

这不是通用忽略开关。每项必须有具体依据和固定版本，且必须仍是本次查询中的候选；执行层重读确认题名及版本未变，只能排除题名不同且没有相同 DOI 或 URL 的候选。候选已变化返回 `distinct_candidate_changed_requires_review`，相同身份返回 `distinct_candidate_identity_conflict`。同 key 重复、空依据及与显式 `parent_key` 混用会在写入前拒绝。未列入的候选照常核查，原条目及其附件不修改。请求及回执的 `native.distinctCandidates` 保留排除依据与对象关系。

先查原失败操作；确认未开始内容写入后，带核验结论生成新请求，保留旧操作编号及失败回执。同编号不同请求仍拒绝；写入结果未知或已开始写入时先按原操作续查，不通过新请求绕过。

下载业务通过 [zotero_archive.py](../../paper-download/scripts/zotero_archive.py) 或机构 `finalize` 提交，支持 `--parent-key-source user|assistant` 和 `--required-version`。默认保护用户指定目标；只有助手交接错误、请求 PDF 身份与同库正确父项均确认且唯一时才自动纠正，返回原 key、新 key 和依据。版本要求不匹配或 PDF 身份无法确认时保留文件并返回待核状态。文本匹配是辅助检查，不能代替业务对作者、版次、出版标记和可靠来源的核实；复用已有附件同样须由业务核实内容。

纠正前查原请求回执，未知或进行中的原操作不能换 key 或编号重放。只有明确终止且确认尚未开始内容写入，才允许以新请求编号继续；旧回执不删除。默认编号取自规范化的原请求，补算文件哈希不会改变编号；同一编号不同输入拒绝。

## prune 请求

`schema/operation_id/library/identity/parent_key` 同上，另传 `keep` 和非空 `candidates`；每项均为 `key/sha256/version/evidence`。同版本冗余正文默认按 `duplicate` 处理。不同版本只有业务层确认已被目标版本替代、提供核实依据并在候选中指定 `"disposition":"superseded"` 时才可提交；执行层不替业务层判定版本关系。`keep` 不接受 disposition。版本未知或补充材料不进入候选。保留文件必须可读且哈希一致；任何候选状态未知则保留并返回 `skipped`。有父条目笔记时保守保留候选，引用该附件的独立笔记同样阻止清理。

## 回执与续做

返回 `operation_id/kind/state/native/readback_verified` 等兼容字段；`native` 只是历史结果字段名。退出码 0 表示回读通过，2 表示待续或失败终态，1 表示请求、连接或依赖错误。`native.trashed/skipped` 分开，归档完成不等于候选全部清理。

同操作锁与公共数据库锁协调本机写入；未决操作保留原回执路径，换目录不能绕过。同编号不同请求哈希拒绝。`operation status` 只读核实持久结果；`resume` 在核实后补缺，保留公共编号和对象 key。完成操作再次调用会回读，不重新导入。安装位置不参与身份计算。

## 清理与并发边界

普通归档保留外部新增附件，不改插件设置。`prune` 检查原阅读内容与文件，只对核实候选以库版本及对象版本条件更新 `deleted=true`。不执行永久删除。回收后再次检查，确认属于本操作的回收遇到并发变化时按对象版本恢复；恢复无法确认则 `unknown`。多次读取与更新无法合为一个官方事务，不承诺跨客户端原子性。

## 实现依据与限制

对照 Zotero 官方 Local API 文档、写请求文档与 `server_localAPI.js`、`data/item.js` 实现。个人库使用 `users/0`；PDF 哈希和嵌入批注由 Python 检查。外部客户端和插件仍可能并发修改；回读不一致报告未完成，不覆盖原内容或伪装成功。
