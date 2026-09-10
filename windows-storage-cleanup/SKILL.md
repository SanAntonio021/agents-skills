---
name: windows-storage-cleanup
description: >
  Safely inspect and reclaim Windows disk space using WizTree or native tools, with risk classification,
  active-process protection, duplicate and backup verification, Recycle Bin staging, and post-cleanup checks.
  Use whenever the user says a Windows drive is full, asks what can be deleted, wants C/D drive cleanup,
  mentions WizTree or large files, asks whether local/cloud duplicates are safe to remove, or needs pagefile
  space advice. Trigger even when the user only asks to review candidates before deleting anything.
---

# Windows 存储空间清理

查明空间占用，列出具体候选，按一次准确确认完成本批清理并核对实际释放量。保留有价值的数据，不为凑够某个空间数值扩大删除范围。

## 操作约定

1. 先读取任务、当前文件和相关应用状态，复用已明确的目标盘、保护范围及授权。仅无法自行查明且会实质改变操作的问题才询问。
2. 从只读扫描开始，先列清单再清理。只读请求保持只读，不调用应用 cleanup、purge、vacuum 或 history-prune，不移动文件、卸载软件或修改系统设置。
3. 清单按来源和用途分点，写清路径、大小、理由、处理方式和能否恢复；准确确认覆盖同批必要步骤及验证，已有授权不重复询问。
4. 默认保护正在进行的工作、源码、用户历史、原始实验数据和唯一归档。个人及科研文件默认回收；明确列入同批的彻底删除按已批准范围执行。
5. 优先后台及官方清理方式，保留用户窗口和运行中的任务。锁定、归属不明或发生变化的项目保留，继续其他已授权项目。
6. 完成批准清单并交付实际结果即可结束，不等待最终签字，也不继续追逐零散小文件。用户要求停止时停止。

## 工作流程

### 1. 确定范围

从当前请求和本机情况确定目标驱动器、保护目录、相关应用以及只读或执行范围。普通清理优先检查占用大、确定无用的内容，不强制先询问“临时腾挪还是长期治理”。缓存会再增长时说明即可；用户明确要求解决反复占满时，再检查增长来源并提出缓存位置、保留期限等调整，按明确授权执行。

根据本地规则和当前文件系统确定用户真实的科研根目录。在明确审查前，将以下路径视为受保护路径：

- `<research-root>\Paper`
- `<research-root>\Program` 和 `<research-root>\ProgramFile` 下的实验路径或原始数据路径
- 活动的 VS Code、Claude、Office、Docker、浏览器和科研工具数据

### 2. 查明占用

先记录当前容量和可用空间。有 WizTree 时，优先用它发现空间热点，再用范围受限的系统原生命令调查具体候选项。

从 WizTree 导出时：

- 记录 WizTree 版本、扫描时间、驱动器和导出路径。
- 进程退出码只作参考。看似成功的退出码不能构成证明；WizTree 4.31 即使成功导出，也曾返回退出码 `1`。
- 使用 CSV 前，确认文件存在、非空、包含预期表头并且可以解析。
- 避免产生海量输出的无边界递归搜索。从最大文件夹开始，逐步缩小范围。

当 CSV 较大或需要同时拆分多个热点目录时，使用
[`scripts/Summarize-WizTreeCsv.ps1`](scripts/Summarize-WizTreeCsv.ps1) 流式读取，并通过 `-Roots` 和
`-Top` 限制为指定目录的直接子项。不要整表载入内存，也不要把全部命中行输出到聊天或日志。

有关扫描、官方清理、Recycle Bin 和页面文件的规则，读取 [references/windows-and-wiztree.md](references/windows-and-wiztree.md)。

### 应用自身清理边界

磁盘扫描与应用历史清理是两个独立步骤。扫描阶段只读取目录大小、文件元数据和已有审计材料；即使应用提供 `cleanup prepare` 这类只生成预案的命令，也不自动调用。

当某个应用的历史材料审查已明确纳入任务时：

1. 使用应用提供的在线 prepare/status 接口，保持其 daemon 或后台服务运行。
2. 遇到 runtime lock、`daemon_already_running`、`shutdown_blocked`、HTTP `409` 或任何 active/queued 状态时，将该项记为 `skipped_busy`。不得通过 `stop`、结束进程、重启服务或停止计划任务绕过。
3. prepare 产生候选清单，返回的 token 只用于接口调用，不代表用户授权。将具体历史范围、处理方式和恢复情况纳入清单。
4. 已有准确授权覆盖该项 purge 时继续执行，不追加单独批准；执行前由智能体重新检查没有 active/queued 工作。授权仅含审查时交付候选，忙碌时跳过该项，继续其他清理。

刷新 prepare 或 token 后复核候选仍属原批准范围；接口无法排除新增或变化项时保留该批历史，不扩大 purge。

对 `claude-codex-bridge`，普通 C 盘扫描不执行 `bridge cleanup prepare`、`bridge cleanup purge` 或 `bridge stop`。明确的 Bridge 历史审查可在线 prepare；具体 purge 复用上述批次授权，不为取得 daemon lock 停止 bridge。

### 3. 对候选项分类

采取操作前，将每个候选项归入以下四类之一：

- `official-cleanup-only`：Windows 组件、安装程序、驱动程序、软件包存储、页面文件和虚拟磁盘。
- `low-risk-after-preapproval`：可重建缓存、已完成的崩溃转储和少量卸载残留。
- `confirm-as-a-group`：安装包、旧应用版本、媒体文件、下载内容、聊天附件和重复项。
- `protected`：原始实验数据、源码仓库、唯一归档、活动应用数据和历史记录。

分类边界和示例见 [references/risk-classification.md](references/risk-classification.md)。

当稳定释放是成功标准时，按以下顺序审查候选：

1. 很少使用的应用和确认不再需要的旧版本，使用官方卸载机制；
2. 已完成卸载且通过完整核验的残留；
3. 一次性备份、安装介质和已核验的重复项；
4. 最后才考虑会重建的缓存，并明确它不计入稳定释放量。

不得仅凭目录名称或没有活动进程就把软件目录、厂商共享目录或运行库当作残留。详细核验见 [references/risk-classification.md](references/risk-classification.md)。剩余收益很小时说明并停止扩展；不设所有机器通用的 MB 门槛，不自动卸载新软件或修改配置来扩大收益。

### 4. 核验重复项和备份

不能凭同名或同大小认定重复。对以“已有副本”为清理理由的候选：

1. 检查文件类型或归档内容。
2. 找到准备保留的副本或云端记录。
3. 比较大小和 SHA-256；对归档或文件夹副本，核验每个必需成员。
4. 确认保留副本可读，并且属于预期项目和版本。
5. 确认云端行为：备份、同步和本地占位符的含义不同。
6. 当云端副本是唯一的其他副本，或尚未测试恢复时，保留一份本地工作副本。

涉及个人或科研文件时，读取 [references/backup-verification.md](references/backup-verification.md)。

### 5. 展示审查清单

默认使用关键词分点，不强制表格。每组写明：**位置、大小、清理理由、处理方式、能否恢复、预计能否实际释放空间**。不明项说明具体缺口；有对应副本时给出核验结果，可重建缓存说明重建依据，不要求为它额外制作备份。

一次确认可覆盖清单内以下操作，原范围内不追加确认：

- **个人和科研文件**：默认移入回收站，说明此时通常仍占用原盘空间。
- **可重建缓存、已核实卸载残留**：按清单写明的官方清理、直接删除或回收方式执行，提前说明恢复限制。
- **本批回收站条目**：需要实际释放空间时，可提前列明这些条目的永久删除并一并确认；只批准移入回收站时保留。精确匹配与核验方法见操作参考，其他条目保持原状。

“清理某盘”触发扫描和清单，不自动等于批准删除一切。已有准确清单及授权时直接续做；只有新增范围或改变已批准处理方式才需要新的决定。

### 6. 安全执行

每次操作前立即复核：

- 重新检查路径、类型、大小、修改时间、适用时的哈希，以及项目是否仍然存在。
- 解析绝对路径，确认它仍位于已批准的根目录下。
- 检查该操作是否会影响相关应用或服务中的工作；可安全在线执行的官方接口按其要求使用。
- 路径穿越、重解析点异常、哈希变化、必要副本缺失或文件数量变化只阻塞相关项；保留当前内容并继续其他已授权项。

对个人文件默认使用 Windows Recycle Bin APIs。本批条目的永久删除可包含在原批准清单内；精确条目无法匹配时保留该项，不改成清空整个回收站。整个回收站只有在明确授权覆盖全部内容时才处理。

对仍安装的应用，使用已注册卸载程序；随后核验残留归属，按清单指定方式处理。对 Windows 组件，使用 Settings Storage recommendations、Disk Cleanup 或已有文档说明的 DISM 命令。不为清理强停应用、重启服务或抢占焦点；需要用户处理的阻塞项单独列出。

在已有清单记录原路径、动作、字节数、核验依据、适用的保留副本和哈希、时间、结果及恢复方式。过程材料沿用共享规则的 `过程文件/任务主题/`，不默认增加其他日志或索引。

### 7. 验证结果

每个已批准批次完成后：

- 确认回收条目存在、准确批准的永久删除已完成，或官方清理已成功；只删除本批回收条目时核验其他条目未受影响。
- 按本批目标驱动器核对 Recycle Bin 状态；不得用 Windows Shell 的全局回收站条目数替代单盘状态。
- 重新检查可用空间。区分处理文件的大小与实际释放量，回收暂存不计作已释放；后台应用可能影响空间变化，差值不精确等于清单总大小时如实说明。
- 报告预期和实际释放的空间，以及所有跳过项。
- 隔离各项失败；不得为补偿某个失败目标而扩大清理范围。

## 页面文件问题

将页面文件大小调整视为系统配置问题，不得视为文件删除问题。

1. 读取实时 `Win32_PageFileSetting`、`Win32_PageFileUsage`、`AutomaticManagedPagefile`、RAM、commit behavior、`CrashDumpEnabled` 和可用空间。
2. 将崩溃转储的最低要求与保守的运行余量分开。
3. 不得声称 C 盘页面文件能够改善启动性能。相关理由是支持崩溃转储和 commit limit behavior。
4. 给出一项内部一致的建议，并明确标记与当前机器相关的数值。
5. 绝不能直接删除 `pagefile.sys`。使用受支持的设置，并明确说明何时需要完整重启 Windows。

## 受阻与完成

文件锁定、归属或副本不明、候选变化时先保留该项；只在无法自行查明且影响后续决定时提问。系统路径、页面文件、VHDX、软件包或驱动目录按专业接口核验，不因路径类别自动追加批准，也不直接删文件。批次完成后交付已完成和跳过项，不为弥补失败扩大范围；长期增长治理只按明确要求开展。

## 预期最终报告

报告以下内容：

- 清理前后的空间及时间戳；
- 已完成操作和涉及的字节数；
- 跳过项及理由；
- Recycle Bin 状态，以及空间是否已经释放；
- 个人或项目数据适用的副本与哈希核验结果；
- 仍需执行的重启或用户操作。
