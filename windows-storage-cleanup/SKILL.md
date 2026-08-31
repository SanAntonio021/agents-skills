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

将清理工作视为以证据和批准为基础的工作流。可用空间目标只是软目标；绝不能仅为达到某个数值而删除有价值的数据。用户要求“删除后不要再自动增长”时，把稳定释放而非短期账面释放作为成功标准。

## 操作约定

1. 提出操作前，先检查本地规则、当前磁盘状态、活动进程和可用审计材料。
2. 在保护边界和预期结果明确前，每次只问一个问题。只有用户明确要求直接推进时，才跳过后续提问。
3. 从只读检查开始。发现阶段不得删除、移动、卸载、停止服务、更改系统设置，也不得调用应用自身的 cleanup、purge、vacuum 或 history-prune 命令。
4. 默认保护正在进行的工作、源代码、用户历史、原始实验数据和唯一的项目归档。
5. 按相同来源和用途归组确认项，并说明大小、理由、风险和恢复方法。
6. 只执行已批准的组。只有用户明确委托时，才允许自动处理低风险项。
7. 对系统和应用数据，优先使用官方清理或卸载机制。将已批准的个人文件移入 Recycle Bin，不得永久删除。
8. 用户表示结果已经足够，或剩余候选只会带来很小、风险更高或很快回补的收益时，停止大范围清理。此后不要继续罗列或处理零散小文件。

## 工作流程

### 1. 确定范围

确认目标驱动器、紧迫程度、受保护根目录、活动应用，以及用户只要审查还是要实际清理。将当前目标与期望达到的可用空间目标分开；同时确认用户重视的是临时腾挪，还是不会因应用重建缓存而很快消失的稳定释放。

根据本地规则和当前文件系统确定用户真实的科研根目录。在明确审查前，将以下路径视为受保护路径：

- `<research-root>\Paper`
- `<research-root>\Program` 和 `<research-root>\ProgramFile` 下的实验路径或原始数据路径
- 活动的 VS Code、Claude、Office、Docker、浏览器和科研工具数据

### 2. 收集证据

先记录当前容量和可用空间。有 WizTree 时，优先用它发现空间热点，再用范围受限的系统原生命令调查具体候选项。

从 WizTree 导出时：

- 记录 WizTree 版本、扫描时间、驱动器和导出路径。
- 进程退出码只作参考。看似成功的退出码不能构成证明；WizTree 4.31 即使成功导出，也曾返回退出码 `1`。
- 使用 CSV 前，确认文件存在、非空、包含预期表头并且可以解析。
- 避免产生海量输出的无边界递归搜索。从最大文件夹开始，逐步缩小范围。

有关扫描、官方清理、Recycle Bin 和页面文件的规则，读取 [references/windows-and-wiztree.md](references/windows-and-wiztree.md)。

### 应用自身清理边界

磁盘扫描与应用历史清理是两个独立步骤。扫描阶段只读取目录大小、文件元数据和已有审计材料；即使应用提供 `cleanup prepare` 这类只生成预案的命令，也不自动调用。

当用户另行批准审查某个应用的历史材料时：

1. 使用应用提供的在线 prepare/status 接口，保持其 daemon 或后台服务运行。
2. 遇到 runtime lock、`daemon_already_running`、`shutdown_blocked`、HTTP `409` 或任何 active/queued 状态时，将该项记为 `skipped_busy`。不得通过 `stop`、结束进程、重启服务或停止计划任务绕过。
3. prepare 只产生候选清单，不构成删除批准。不得把 prepare 返回的一次性 token 自动交给 purge。
4. purge 必须作为单独的用户批准批次，并在执行前重新确认没有 active/queued 工作；若空闲门不成立，跳过该项，不扩大清理范围。

对 `claude-codex-bridge`，普通 C 盘扫描不得执行 `bridge cleanup prepare`、`bridge cleanup purge` 或 `bridge stop`。只有用户明确批准 Bridge 历史材料审查后，才可在线运行 `bridge cleanup prepare`；不得为取得 daemon lock 先停止 bridge。

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

不得仅凭目录名称或没有活动进程就把软件目录、厂商共享目录或运行库当作残留。详细核验见 [references/risk-classification.md](references/risk-classification.md)。当剩余项只有几百 MB、会自动重建或需要承担明显更高风险时，说明边际收益已不值得继续并停止扩展候选清单。

### 4. 核验重复项和备份

不得把同名或同大小视为重复项证据。对删除候选项：

1. 检查文件类型或归档内容。
2. 找到准备保留的副本或云端记录。
3. 比较大小和 SHA-256；对归档或文件夹副本，核验每个必需成员。
4. 确认保留副本可读，并且属于预期项目和版本。
5. 确认云端行为：备份、同步和本地占位符的含义不同。
6. 当云端副本是唯一的其他副本，或尚未测试恢复时，保留一份本地工作副本。

涉及个人或科研文件时，读取 [references/backup-verification.md](references/backup-verification.md)。

### 5. 展示审查清单

使用以下紧凑表格：

| 组 | 路径或来源 | 大小 | 证据 | 风险 | 建议操作 |
| --- | --- | ---: | --- | --- | --- |
| `<purpose>` | `<path>` | `<size>` | `<why it is safe or uncertain>` | low/medium/high | keep/recycle/official cleanup |

风险为 medium 或 high 时，每次只请求一个决定。用户委托低风险操作后，也只能执行已核验保留副本和恢复路径的项目。

### 6. 安全执行

每次操作前立即复核：

- 重新检查路径、类型、大小、修改时间、适用时的哈希，以及项目是否仍然存在。
- 解析绝对路径，确认它仍位于已批准的根目录下。
- 检查相关应用或服务是否处于活动状态。
- 遇到路径穿越、重解析点异常、哈希变化、保留副本缺失或文件数量变化时，拒绝执行。

对个人文件使用 Windows Recycle Bin APIs。除非用户明确要求且现行规则允许，否则不得实施永久删除。未经单独批准，不得清空整个 Recycle Bin。

对应用程序，先运行已注册的卸载程序并核验卸载记录，再把剩余文件移入 Recycle Bin。对 Windows 组件，使用 Settings Storage recommendations、Disk Cleanup 或已有文档说明的 DISM 命令。

写入操作清单，包含 original path、action、bytes、evidence、retained copy、hash when used、timestamp、result 和 recovery method。

### 7. 验证结果

每个已批准批次完成后：

- 确认移动的项目已出现在 Recycle Bin 中，或官方清理已成功完成。
- 重新检查可用空间。移入 Recycle Bin 不会释放物理空间，清空后才会释放。
- 报告预期和实际释放的空间，以及所有跳过项。
- 隔离各项失败；不得为补偿某个失败目标而扩大清理范围。

## 页面文件问题

将页面文件大小调整视为系统配置问题，不得视为文件删除问题。

1. 读取实时 `Win32_PageFileSetting`、`Win32_PageFileUsage`、`AutomaticManagedPagefile`、RAM、commit behavior、`CrashDumpEnabled` 和可用空间。
2. 将崩溃转储的最低要求与保守的运行余量分开。
3. 不得声称 C 盘页面文件能够改善启动性能。相关理由是支持崩溃转储和 commit limit behavior。
4. 给出一项内部一致的建议，并明确标记与当前机器相关的数值。
5. 绝不能直接删除 `pagefile.sys`。使用受支持的设置，并明确说明何时需要完整重启 Windows。

## 安全停止条件

遇到以下情况时停止并询问用户：

- 候选项可能是原始数据、源代码、历史记录或项目唯一的本地副本；
- 备份证据只有同名文件或云端列表；
- 应用处于活动状态或文件已锁定；
- 涉及系统路径、页面文件、VHDX、软件包存储或驱动程序目录；
- 候选项在审查后发生变化；
- 操作将变成永久操作，而非可恢复操作。

## 预期最终报告

报告以下内容：

- 清理前后的空间及时间戳；
- 已完成操作和涉及的字节数；
- 跳过项及理由；
- Recycle Bin 状态，以及空间是否已经释放；
- 个人或项目数据的备份/哈希证据；
- 仍需执行的重启或用户操作。
