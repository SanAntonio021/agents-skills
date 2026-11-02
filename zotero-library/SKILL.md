---
name: zotero-library
description: Zotero 后台公共执行层。查询条目、附件、笔记、批注和集合，按结构化请求查重归档、添加集合关系、保护阅读内容、回收已核实冗余附件及恢复结果未知的操作。paper-download、paper-search、zotero-workspace-library 和 lab-resources 的 Zotero 执行均使用本技能；科学身份、版本、归档授权及工作区分类由业务技能决定。
---

# Zotero 公共执行层

本技能持有唯一连接和执行实现。业务技能提交核实后的数据，正常流程直接调用命令；连接检查、查重、自动抓取保护、保存、回读和设置恢复都在命令内部完成。不得临时编写原生调用、读取 token、猜 Profile 或把鉴权失败改成 Connector 重放。

## 命令

先定位已安装的本技能目录，Python 3.10+；PDF 结构检查依赖 `requirements.txt`。缺失时明确报告依赖，不能恢复业务技能中的独立旧实现。

```powershell
$zl = '<已解析的 zotero-library 目录>/scripts/zotero_library.py'
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

## 业务请求

完整字段、示例与恢复约定见 [接口契约](references/contract.md)。请求只接受白名单 JSON，不接受凭据、偏好代码或任意 JavaScript。`identity.evidence`、PDF `version/evidence` 由业务技能提供；执行层复核父条目身份、文件结构、SHA-256、归属及持久化结果，不替业务层认定科学内容或正式版本。

`find --request` 返回 `matched/not_found/review_required`，显式 key 不匹配时只报告差异。DOI 规范化、完整题名、作者年份及缺 DOI 的独立证据共用同一规则；多个匹配或未决冲突阻止写入。下载交接自动纠错由 `paper-download` 判断，公共层不自行换目标。

集合只增加。`collections` 可指定已核实 key，或需要建立的实际路径；不按搜索批次新建集合。同库复用条目和文件，跨库不自动复制。已有可读目标版本但字节不同时，由业务层核实版本等价后以 `reuse_pdf` 指定附件；不能仅凭版本名或标题判定等价。

## 失败与恢复

写入前把操作编号和非凭据回执写入本机操作目录。命令返回 `running/unknown` 或退出码 2 时，保存原编号和 PDF，先查询同一操作；只有原操作确已终止才允许 `resume` 补缺。同一编号不同请求拒绝。原进程仍在但内存标记丢失时保持未知；进程结束后先查持久化结果。设置恢复未知或存在外部修改时保留现状并报告 `recovery_required`。

原生任务在 Zotero 进程内串行，识别旧 `__paperDownloadBatches` 标记；迁移期间不能同时运行旧脚本。HTTP 超时不终止任务、不提前恢复设置、不更换接口。Local API 用于库内读取，Debug Bridge 用于固定原生操作。当前没有提供满足同等保护的 Connector 写入适配器。

插件自动抓取保护使用现场插件版本与核实的布尔偏好。未知插件默认阻止新增，`status --capabilities` 给出清单；内部策略文件只记录版本、全局偏好名和核实依据，不保存凭据。其格式与审查边界见接口契约，不能为通过检查把未知插件写成“没有自动抓取”。

业务任务只能复用维护时已审核的策略。出现 `automatic_fetch_policy_unverified` 时报告缺口并保留文件，不临时创建或修改策略；插件名称、功能介绍和版本清单不能证明不存在自动抓取处理器。策略维护需另行检查该版本源码与处理器，再留下可追溯依据。

## 阅读内容与验收

归档保留父条目元数据、标签、原集合、已有附件及其文件、批注和笔记；用户源文件复制导入。原生回读后再通过 Local API 和文件解析器核对条目、附件、集合、哈希和可读性，设置恢复另行核实。

`prune` 只接受业务层已核实的冗余候选。同版本重复文件可直接列入；不同版本必须提供明确的 `superseded` 判断及依据。执行层重新核对父条目、保留文件、候选哈希、原生及 PDF 内嵌批注、笔记和关联阅读内容。版本未知或存在阅读内容的候选保留，返回原因。只调用原生回收站，不永久删除、不改 storage、不修改笔记。

隔离模拟通过与真实 Zotero 写入验收分别报告；历史验证见 [兼容与历史](../paper-download/references/zotero-storage.md)。
