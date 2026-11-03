---
name: zotero-workspace-library
description: 统一 Zotero 分类、归档、引用导出、PDF 分页阅读与笔记批注检索。Use when organizing workspace references, archiving verified metadata or PDFs, exporting BibTeX, inserting Markdown or LaTeX citations, reading PDF pages, searching notes or annotations, protecting reading content, pruning redundant attachments, or resuming unknown operations. Business skills provide identity, version, purpose and archive authorization.
---

# Zotero 工作区资料库

本技能是唯一的 Zotero 技能入口，同时负责工作区分类政策和 Zotero 后台执行。业务技能提交核实后的结构化参数；本技能内部完成连接、能力检查、查重、写入、集合关联、阅读内容保护、回读验收和结果未知时的续做。不得临时编写原生调用、读取 token、猜 Profile，或把鉴权失败改成 Connector 重放。

## 故障交接

接手“prefs.js 没有配置”“token 找不到”等旧助手结论时，先用本技能的统一命令核实当前目标连接。需要诊断时调用 `status --capabilities --json`；已有核实请求时可直接执行业务命令，由内部完成连接检查。保留任务指定的连接绑定和原 operation 编号，不因交接建议先关闭下载会话、切接口或要求重启。

业务执行中凭据只由内部连接模块读取；不打开 `prefs.js`、凭据会话文件、环境转储或认证头查找 token，不把认证值复制到命令、执行记录、报告或回复。诊断使用 `read_only_ready`、`local_api_write_supported`、`local_api_authorization_present` 和固定错误码；本次试跑的模拟认证值也按此处理。

当前检查成功只证明当前连接可用，不能据此断定上一位助手漏设环境变量、读错配置或使用了错误请求。历史原因缺少实际命令和回执时写明未知；当前确有缺口时报告命令返回的错误码、保留材料及未完成步骤。

## 业务边界

`paper-download`、`paper-search` 和 `lab-resources` 分别负责资料身份、目标版本、用途及归档授权。本技能负责把已核实请求安全地落实到目标 Zotero 资料库，并重新核对父条目、附件、集合和阅读内容。科学身份、版本关系和工作区分类意图不由执行层推断替代。

## 分类

按“工作区 → 资料类型 → 必要时再细分”归档。常用类型为“论文”“标准”“器件手册”；其他资料类型只在有实际资料需要时建立，不预建空集合。

- 论文先进入工作区的“论文”集合。同一研究方向的多篇论文共用该集合，不按单篇文章或一次检索任务建集合。只有出现多个稳定、相对独立的研究方向时，才在“论文”下建立方向子集合。
- 器件手册先进入“器件手册”；当器件类别确实有助于查找时，再建立有资料的类别子集合。
- 标准及其他资料按资料本身的类型归档；不按下载批次、检索任务或文章引用状态建集合。
- 只读查询、临时搜索候选和用户明确要求不写库的任务保持只读。进入工作区参考资料、用于持续设计或研究的外部资料按需归档，不把搜索结果数量当作归档目标。

## 资料归属

- 论文、正式标准、公开厂家资料，以及无保密或存储限制的供应商技术手册和规格书，归 Zotero。
- 项目自产的代码、数据、仿真、实验记录和报告留在项目。外部参考文件不在项目中长期保留第二份 PDF；项目材料记录 Zotero 条目或集合入口。已有本地副本保持原样，本技能不触发历史文件迁移或删除。
- 报价、询价邮件、采购往来等商务记录不作为 Zotero 参考资料归档；按项目现有商务记录规则处理。存在保密、许可或存储限制的供应商资料，在限制明确前不入库。
- 同一资料在同一 Zotero 资料库中只保留一个条目和一份附件。多个工作区需要该资料时，把同一条目加入各自集合，不复制条目或 PDF。
- 若工作区对应不同 Zotero 资料库，不能用跨库集合关联；不要自动复制，先说明限制并确定共用资料库或其他处理方式。

## 工作区入口

工作区 `README.md` 可在对应集合建立后提供 Zotero 入口。先核实当前 Zotero 环境支持的集合链接形式；只有读回确认有效后才写可点击链接。若没有经验证的链接形式，写明集合层级名称和 Zotero 内检索方式，不猜 URI 或 key。

论文工程中的 `.bib`、DOI、引用键及具体章节用途仍留在论文工程或研究材料中；Zotero 集合用于资料归属，不代表条目已被某篇稿件引用。

## 命令入口

先定位已安装的本技能目录，Python 3.10+；PDF 结构检查依赖 `requirements.txt`。缺失时明确报告依赖，不能恢复业务技能中的独立旧实现。

```powershell
$zl = '<已解析的 zotero-workspace-library 目录>/scripts/zotero_library.py'
python $zl status --json
python $zl status --capabilities --json
python $zl find --doi '10.1234/example'
python $zl find --query '完整题名或作者'
python $zl find --request '<核实后的归档请求.json>'
python $zl get --key ABCD1234
python $zl collections
python $zl export --keys ABCD1234 --output '<绝对路径>/references.bib'
python $zl cite --request '<明确文件和插入位置的引用请求.json>'
python $zl read --key ABCD1234 --pages '1-3,6'
python $zl search --query '检索词' --scope annotations
python $zl archive --request '<归档请求.json>'
python $zl prune --request '<核实后的清理请求.json>'
python $zl operation status --id '<原操作UUID>'
python $zl operation resume --id '<原操作UUID>'
```

`status` 保留原退出码，0 只表示可读；同时分别返回官方写入支持与已有授权状态，不弹出授权窗口。旧桥字段均为 null，并标记 `debug_bridge_applicability=not_applicable`。写入无需另跑状态命令。读取默认个人库，群组用 `--group <群组ID>`。`--policy` 仅保留参数兼容，不读取或执行插件策略。

任务提供了连接参数时，全程保留该目标，包括下载 `finalize` 和 operation 查询。可用同一进程环境 `ZOTERO_PROFILE`、`ZOTERO_LOCAL_BASE_URL`、`ZOTERO_LIBRARY_STATE_DIR` 绑定 Profile、地址和回执目录；显式命令参数优先。配置无效就停止，不探测默认文库。

## 请求与执行

完整字段、示例与恢复约定见 [接口契约](references/contract.md)。请求只接受白名单 JSON，不接受凭据、偏好代码或任意 JavaScript。`identity.evidence`、PDF `version/evidence` 由业务技能提供；执行层复核父条目身份、文件结构、SHA-256、归属及持久化结果。

`find --request` 返回 `matched/not_found/review_required`，显式 key 不匹配时只报告差异。DOI 规范化、完整题名、作者年份及缺 DOI 的独立证据共用同一规则；多个匹配或未决冲突阻止写入。下载交接自动纠错由 `paper-download` 判断，本技能不自行换目标。

集合只增加。`collections` 可指定已核实 key，或需要建立的实际路径；不按搜索批次新建集合。同库复用条目和文件，跨库不自动复制。已有可读目标版本但字节不同时，由业务层核实版本等价后以 `reuse_pdf` 指定附件；不能仅凭版本名或标题判定等价。

每个写入命令内部完成：核对目标、查重、记录操作、保存缺项、回读条目、集合和文件。Python 直连 Zotero 10+ 官方 Local API，所有日常命令均不依赖 Debug Bridge；不查桥 token、不修改插件偏好、不运行进程内批次代码。

首次写入使用 Zotero 官方授权弹窗。弹窗由用户亲自确认，助手不使用 Computer Use 打开、点击或检查窗口。用户确认完成后，继续等待原 CLI／Local API 请求并核验回执；若原命令已超时或退出，按原 operation ID 查询并安全续做。授权仍未生效时依据实际错误报告，不另建请求、不换接口。长期授权只存 Windows 凭据管理器；一次授权仅用于一次写请求，多步归档可能需要多次授权。诊断和回执不含凭据。固定数据库身份，换库时停止原操作；认证失败不换接口重放。外部插件新增附件时保留并报告，不自动清理。

## 引用、阅读与检索

`export` 默认输出实际 BibTeX；指定 `--output` 时只合并缺失条目，保留已有 `.bib` 内容。引用键取自逐条导出，不自行推测。相同键对应不同内容时返回 `conflict` 和差异，不覆盖。

`cite --request` 明确论文 key、Markdown／LaTeX、文稿路径、唯一锚点、前后位置及 `.bib` 路径；格式见[接口契约](references/contract.md#引用与导出)。只在指定位置插入，重复执行不重复追加。接受 UTF-8 文本，保留已有 BOM 与换行；目标变化时停止覆盖。如果 `.bib` 已写好而文稿插入受阻，修正冲突后重复同一请求即可。

`read` 从库内 PDF 读取物理页码及 PDF 页标签，默认前十页；超过一份 PDF 时必须用 `--attachment` 选定。返回截断、未读页数和 OCR 状态；扫描页明确标记 `needs_ocr`，不能把没有文字层当作没有内容。

`search --scope all/notes/annotations` 搜索笔记正文、批注文字、评论与标签，返回所属论文、附件、物理页码及页标签；无页码的笔记保持未知。`--scope fulltext` 复用 Zotero 已有索引检索，不承诺覆盖未索引或扫描页，不建立独立索引服务。三个上游的参考范围与许可见[功能来源](references/feature-sources.md)。

## 失败与恢复

写入前保存操作编号、固定对象 key、数据库身份和非凭据回执。操作编号算法、连接绑定、凭据绑定及回执目录保持兼容。新回执记录 `executor_version=2` 与 `api_stages`。同一数据库使用公共本机锁及未决记录串行协调，不因更换回执目录绕过。

结果未知时先查同一操作、固定对象和文件。已完成阶段只确认；仅在固定 key、版本条件及文件状态足以安全续做时 `resume` 补缺。无法核实就保留 `unknown`，不重新创建对象。同一编号不同请求拒绝。旧已完成回执只读回验，未派发操作可迁移；旧未知操作结合原进程身份与持久化结果核实，不恢复桥接执行器或旧偏好设置。

## 阅读内容与清理

归档保留父条目元数据、标签、原集合、已有附件及文件、批注和笔记。PDF 复制导入，保留源文件；Python 核对库内 SHA-256 和可读性。普通归档不顺手清理。

`prune` 只处理业务层已核实的候选与保留附件，不自动清扫全库。同版本重复文件可列入；不同版本必须提供 `superseded` 及依据。执行层重新检查同一父条目、文件哈希、版本依据、Zotero 批注、PDF 内嵌批注、附件笔记、父条目笔记及引用该附件的独立笔记。存在阅读内容或未知项就保留。

合格候选通过带库版本和对象版本条件的官方更新设置 `deleted=true`，进入回收站；不调用永久删除接口。写前复查、写后回读，确认本次回收后发现并发变化时按版本条件恢复；无法确认恢复则报告 `unknown`。官方 API 不能把全部检查和回收合为一个事务，这个边界保留在验收记录中。

## 执行交接

本技能决定分类并执行归档。使用 `collections` 查询实际集合，使用 `archive --request` 创建或复用父条目、补附件和增加集合关系；已有条目传 `parent_key`，不复制条目或 PDF。业务技能提供身份、版本、用途和授权，写后按 key 回读。

Zotero 暂不可用时继续独立的研究工作，并说明尚未完成的归档项；不以项目内长期 PDF 副本替代 Zotero，也不声称已完成归档。

隔离模拟通过与真实 Zotero 写入验收分别报告；原有 Zotero 参考文档保留兼容链接。
