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

默认先充分扫描和核验，再汇总一份清单、一次批量确认，按准确授权连续完成清理并核对实际释放量。内部扫描与执行可以分批，不把内部批次变成多轮用户确认。下列流程按任务使用；执行专项操作前读取对应参考章节，不为普通占用查询加载全部资料。

## 范围与授权

先读取当前任务、文件和相关应用状态，复用已确定的目标盘、保护范围和清单。“清理某盘”先形成候选，不等于批准删除一切；准确授权覆盖同批处理及必要验证，仅新增范围、改变处理方式或无法自行查明的实质问题需要用户决定。

只读扫描只读取容量、目录大小、文件元数据和已有材料；不调用应用 `cleanup prepare`、`purge`、`vacuum` 或 `history-prune`，不移动文件、卸载软件或修改设置。明确要求应用历史审查时，按下方专项入口处理。

## 工作流程

### 1. 查明占用

记录目标盘当前容量、可用空间和时间；先做目标盘的占用总览，有 WizTree 时优先用它发现热点，再用范围受限的原生命令调查主要热点及缓存、安装包、旧版本、重复文件和实验结果候选。整盘先查元数据，只对候选深入检查和计算哈希，避免无边界递归或海量输出。

提交清单前，主要热点须已有可清理、需保留或暂时无法判断的结论；未查清项写明具体原因，独立的可查项继续调查。不要每找到几个文件就停下来询问；扫描期间只报进度，不设凑数量、凑容量的指标。用户缩小范围、已有准确清单或要求停止时，沿用该边界，不为满足扫描流程扩大任务。

- 容量读取见 [容量快照](references/windows-and-wiztree.md#read-only-capacity-snapshot)。
- 使用 WizTree 前读 [导出核验](references/windows-and-wiztree.md#wiztree-export-validation)，核验 CSV 实际内容而非只看退出码。大表使用现有 [流式汇总脚本](scripts/Summarize-WizTreeCsv.ps1)，保留 `-Roots`、`-Top` 接口。

### 2. 判断候选

处理具体候选前读 [风险分类](references/risk-classification.md)，保留四类名称：`official-cleanup-only`、`low-risk-after-preapproval`、`confirm-as-a-group`、`protected`。分类本身不增加批准轮次；软件残留需核对安装归属、共享依赖及用户数据，不能凭名称或没有活动进程认定。

以保留副本为删除依据，或涉及个人、科研文件时，先读 [副本与云端核验](references/backup-verification.md)。重复项先核对卷与文件标识、硬链接关系，再验证内容并计算物理可释放空间；同一文件对象的多个路径不算独立副本，不能重复计量。核对大小、SHA-256、必要成员、保留副本可读性、项目版本及备份／同步／占位符语义；同名、同大小或云端列表不足以认定可删。

提交清单前完成适用的归属、活动进程、文件占用及副本核验，把锁定或证据不足项排除或单列；执行前仍须复核。唯一资料和原始实验数据默认保留，不能仅凭“旧”“预实验”等名称判断无用。

普通清理优先处理占用大且确定无用的内容。明确要求稳定释放或解决反复占满时，按 [稳定释放与增长治理](references/risk-classification.md#stable-reclaim-and-recurring-growth) 判断；一次清理不自动扩展为长期配置调整。

### 3. 展示清单

集中展示一份按来源、用途和处理方式分组的可决策清单，每组写明 **位置、数量、逻辑大小、删除依据、处理方式、恢复限制及预计物理释放量**，按盘汇总。展示推荐删除、仅回收及保留／待判断项，避免逐文件堆砌；准确路径和核验依据保存在清单中。副本给出核验结果，可重建缓存说明重建依据，无需额外备份。

- 按内容推荐处置：已核实可重建的缓存、确认无用且不在使用的安装包及有完整独立副本的重复项，可推荐明确范围的永久删除；应用缓存和系统组件仍使用适用的官方清理接口。推荐不等于授权。
- 仍有恢复价值的候选可推荐仅回收；价值不明的唯一资料、原始实验数据保留并单列。仅回收通常不释放原盘空间，预计物理释放量记为零。
- 用户可一次批准全部推荐项或指定保留某些组；同时确认准确范围和处理方式。已明确批准的本批回收条目永久删除包含在同一次授权内，无需先回收后再问；只批准回收时保留，整个回收站仍需授权覆盖全部内容。
- 准确清单获批后，先写只含 `batchId`、`approvedRoots`、`source`、`action` 及适用副本/归档路径的 selection JSON，再用 [清单生成器](references/execution-tool.md#manifest-generation)补齐成员、空目录、时间和哈希。生成器只生成清单，不执行删除，也不能替代批准。

### 4. 执行与保护

整份清单获批后连续完成已授权项，不按内部执行批次逐组索取确认；只有新增范围、改变处理方式或无法自行查明的实质问题才需要用户决定。

普通文件或目录的回收、精确永久删除、跨盘归档，优先使用 [通用执行工具](references/execution-tool.md)，不为每批重新拼写删除脚本。默认 `Check` 只读；批准清单固定后使用 `Execute`，中断后先用 `Status` 查看持久阶段，再使用同一清单和状态目录 `Resume`，以 `Verify` 核对实际结果。`Status` 只是阶段诊断，不能替代内容复核或完成验收。应用缓存、会话历史、系统组件和卸载仍走对应官方接口，不套用通用文件工具。

超过 1,000 个成员的 `Execute`/`Resume` 会每 5 秒向 stderr 输出一条不含文件路径的 JSON 进度；stdout 仍只保留最终结果。永久删除时，工具只对已重新核验的本批回收站载荷清除 ReadOnly 属性；仍需为被进程锁定、内容变化或归属不明项保留现场。

保护正在进行的工作、源码、用户历史、原始实验数据、唯一归档及活动应用数据；从本地规则和文件系统确认科研根目录。每次操作前复核绝对路径及批准根目录、类型、大小、修改时间、适用的哈希、文件数量、项目与依赖状态、必要副本及恢复方式。

优先安全的后台及官方接口，保留用户窗口和运行任务，不为清理强停应用、重启服务或抢占焦点。文件锁定、归属不明、路径穿越、重解析点异常或内容变化时保留该项，继续独立的已授权项。专项操作前读取：

- **应用历史**：[在线审查与清理](references/windows-and-wiztree.md#application-history-cleanup)，区分扫描、prepare 与 purge，处理忙碌状态及候选刷新。
- **系统组件与软件卸载**：[官方处理方式](references/windows-and-wiztree.md#windows-cleanup-order)；已安装软件使用注册卸载程序，残留按风险参考核验。
- **回收与永久删除**：[回收操作](references/windows-and-wiztree.md#recycle-bin-staging)，使用 Windows 回收接口；按目标盘精确匹配条目并保护其他条目，不能用清空整个回收站替代本批删除。
- **页面文件**：[页面文件检查](references/windows-and-wiztree.md#pagefile-inspection)，作为系统配置处理，保留实时配置、内存提交及崩溃转储判断。

在已有清单记录原路径、动作、字节数、核验依据、适用副本和哈希、时间、结果及恢复方式。过程材料沿用 `过程文件/任务主题/`，不默认增加日志或索引。

### 5. 核验与交付

核对批准动作的实际结果：回收条目存在、准确永久删除完成或官方清理成功；涉及回收站时按目标盘核对，确认非目标条目未受影响。重新读取可用空间，区分处理字节数与实际释放量，回收暂存不计作释放；后台应用造成的空间差异如实说明。

分点交付清理前后空间及时间、完成操作和处理量、跳过项及原因、适用的回收站状态与副本核验、仍需的重启或用户操作。只读任务交付调查和候选，不报清理成功。

批准批次完成并核验后结束，不等待最终签字，不为凑释放量、弥补失败或追逐零散小文件扩大清理；用户要求停止时停止。
