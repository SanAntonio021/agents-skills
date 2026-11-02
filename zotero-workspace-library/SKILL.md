---
name: zotero-workspace-library
description: 统一 Zotero 工作区分类、参考资料归属、跨工作区关联和后台执行。Use when deciding where an external reference belongs in Zotero, querying entries or collections, archiving verified metadata or PDFs, protecting reading content, pruning verified redundant attachments, or resuming an operation with an unknown result. Business skills provide identity, version, purpose, and archive authorization; this skill owns connection, deduplication, writes, collection relations, readback, and recovery.
---

# Zotero 工作区资料库

本技能是唯一的 Zotero 技能入口，同时负责工作区分类政策和 Zotero 后台执行。业务技能提交核实后的结构化参数；本技能内部完成连接、能力检查、查重、写入、集合关联、阅读内容保护、回读验收和结果未知时的续做。不得临时编写原生调用、读取 token、猜 Profile，或把鉴权失败改成 Connector 重放。

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
python $zl archive --request '<归档请求.json>'
python $zl prune --request '<核实后的清理请求.json>'
python $zl operation status --id '<原操作UUID>'
python $zl operation resume --id '<原操作UUID>'
```

`status` 沿用原状态字段与退出码，0 只表示可读。`--capabilities` 增补原生能力、进程身份、活动插件及自动抓取保护缺口，不改变旧状态语义。写入无需另跑状态命令。读取默认个人库，群组用 `--group <群组ID>`；请求中的群组 ID 不是原生 libraryID。

任务提供了连接参数时，全程保留该目标，包括下载 `finalize` 和 operation 查询。可用同一进程环境 `ZOTERO_PROFILE`、`ZOTERO_LOCAL_BASE_URL`、`ZOTERO_LIBRARY_STATE_DIR` 绑定 Profile、地址和回执目录；显式命令参数优先。配置无效就停止，不探测默认文库。

## 请求与执行

完整字段、示例与恢复约定见 [接口契约](references/contract.md)。请求只接受白名单 JSON，不接受凭据、偏好代码或任意 JavaScript。`identity.evidence`、PDF `version/evidence` 由业务技能提供；执行层复核父条目身份、文件结构、SHA-256、归属及持久化结果。

`find --request` 返回 `matched/not_found/review_required`，显式 key 不匹配时只报告差异。DOI 规范化、完整题名、作者年份及缺 DOI 的独立证据共用同一规则；多个匹配或未决冲突阻止写入。下载交接自动纠错由 `paper-download` 判断，本技能不自行换目标。

集合只增加。`collections` 可指定已核实 key，或需要建立的实际路径；不按搜索批次新建集合。同库复用条目和文件，跨库不自动复制。已有可读目标版本但字节不同时，由业务层核实版本等价后以 `reuse_pdf` 指定附件；不能仅凭版本名或标题判定等价。

每个写入命令内部完成：连接检查、原操作核实、查重、自动抓取保护、保存、回读验收和设置恢复核实。原生任务在 Zotero 进程内串行，识别旧 `__paperDownloadBatches` 标记；迁移期间不能同时运行旧脚本。Local API 用于库内读取，Debug Bridge 用于固定原生操作。

## 失败与恢复

写入前把操作编号和非凭据回执写入本机操作目录。命令返回 `running/unknown` 或退出码 2 时，保存原编号和 PDF，先查询同一操作；只有原操作确已终止才允许 `resume` 补缺。同一编号不同请求拒绝。原进程仍在但内存标记丢失时保持未知；进程结束后先查持久化结果。设置恢复未知或存在外部修改时保留现状并报告 `recovery_required`。

HTTP 超时不终止任务、不提前恢复设置、不更换接口。当前没有提供满足同等保护的 Connector 写入适配器。出现 `automatic_fetch_policy_unverified` 时报告缺口并保留文件，不临时创建或修改策略；业务任务不得根据插件名称生成空偏好列表或虚构已审核依据。

## 阅读内容与清理

归档保留父条目元数据、标签、原集合、已有附件及其文件、批注和笔记；用户源文件复制导入。原生回读后再通过 Local API 和文件解析器核对条目、附件、集合、哈希和可读性，设置恢复另行核实。

`prune` 只接受业务层已核实的冗余候选。同版本重复文件可直接列入；不同版本必须提供明确的 `superseded` 判断及依据。本技能重新核对父条目、保留文件、候选哈希、原生及 PDF 内嵌批注、笔记和关联阅读内容。版本未知或存在阅读内容的候选保留，合格候选仅进原生回收站，不永久删除、不改 storage、不修改笔记。

## 执行交接

本技能决定分类并执行归档。使用 `collections` 查询实际集合，使用 `archive --request` 创建或复用父条目、补附件和增加集合关系；已有条目传 `parent_key`，不复制条目或 PDF。业务技能提供身份、版本、用途和授权，写后按 key 回读。

Zotero 暂不可用时继续独立的研究工作，并说明尚未完成的归档项；不以项目内长期 PDF 副本替代 Zotero，也不声称已完成归档。

隔离模拟通过与真实 Zotero 写入验收分别报告；原有 Zotero 参考文档保留兼容链接。
