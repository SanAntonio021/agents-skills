# Windows 与 WizTree 操作

<a id="read-only-capacity-snapshot"></a>
## 只读容量快照

使用 CIM 获取稳定的字节数：

```powershell
Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:' OR DeviceID='D:'" |
    Select-Object DeviceID, Size, FreeSpace
```

记录时间戳。应用运行时容量可能变化。

<a id="wiztree-export-validation"></a>
## WizTree 导出核验

WizTree CLI 的细节可能因版本和许可而不同。先发现本机 CLI 语法，不要凭假设调用。导出后直接核验导出文件：

1. 等待 WizTree 进程结束，或等待导出文件稳定；
2. 确认文件存在且长度非零；
3. 读取生成版本行和 CSV 表头；
4. 在处理完整导出前先解析小样本；
5. 在审计记录中保存扫描时间和目标盘。

不要只相信 `$LASTEXITCODE`。本机的 WizTree 4.31 曾经在返回退出码 `1` 的同时生成有效 CSV。

对于大型导出，使用 [Summarize-WizTreeCsv.ps1](../scripts/Summarize-WizTreeCsv.ps1)，不要用 `Import-Csv` 一次性加载完整文件，
也不要打印所有匹配项。该脚本会核验版本标记和必要列，使用结构化 CSV 解析器流式读取行，只选择明确指定根目录的直接子项，
并对每个根目录限制 `-Top` 结果数量。目录行已经包含 WizTree 的聚合大小，因此不能再次把选中直接子项下面的后代相加。

<a id="windows-cleanup-order"></a>
## Windows 清理顺序

优先使用受支持的机制：

1. 设置 > 系统 > 存储 > 清理建议或临时文件；
2. 应用缓存控制项或注册的卸载程序；
3. 适用时使用磁盘清理；
4. 按官方文档使用 DISM 进行 Windows 组件存储维护。

Official references:

- [Free up drive space in Windows](https://support.microsoft.com/en-us/windows/free-up-drive-space-in-windows-85529ccb-c365-490d-b548-831022bc9b32)
- [Clean up the WinSxS folder](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/clean-up-the-winsxs-folder)
- [Determine the appropriate page file size](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/how-to-determine-the-appropriate-page-file-size-for-64-bit-versions-of-windows)
- [Windows memory dump file options](https://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/memory-dump-file-options)

<a id="application-history-cleanup"></a>
## 应用历史清理

当任务包含某个应用的历史审查或清理时，读取本节。普通磁盘扫描只读取目录大小、文件元数据和已有审计材料；
不会仅因为 `cleanup prepare` 能生成计划就调用它。

1. 对明确要求的历史审查，使用应用支持的在线 prepare/status 接口，并保持其 daemon 或服务运行；
2. 将运行时锁、`daemon_already_running`、`shutdown_blocked`、HTTP `409` 或活动／排队任务视为 `skipped_busy`。
   保留该项并继续其他独立的已批准工作；不要停止进程、服务或计划任务，也不要为了取得锁而重启它们；
3. prepare 只产生候选项，其 token 是接口参数，不是删除授权。将准确的历史范围、处理方式和恢复限制写入现有清理清单。
   只审查任务交付该清单；
4. 如果已有准确授权覆盖 purge，重新确认当前没有活动或排队任务后直接使用，不再追加确认。先前的忙碌结果不会撤销未变化的授权；
5. 刷新 prepare 或其 token 后，将候选项与已批准范围比较。保留新增或发生变化的项目；如果接口无法排除这些项目，推迟受影响批次，
   不要扩大 purge 范围。

对于 `claude-codex-bridge`，普通 C 盘扫描既不调用 `bridge cleanup prepare`，也不调用 `bridge cleanup purge` 或 `bridge stop`。
明确要求 Bridge 历史审查时可以在线执行 prepare；准确授权的 purge 按上述检查执行，不为 daemon 锁停止 Bridge。

<a id="recycle-bin-staging"></a>
## 回收站暂存

对已批准的个人文件，使用 Windows Shell 支持的回收站，不要使用 `Remove-Item`。一种 PowerShell 方式是使用
`Microsoft.VisualBasic.FileIO.FileSystem` 和 `RecycleOption.SendToRecycleBin`。

移动前：

- 解析并验证绝对目标路径；
- 除非已明确理解，否则拒绝重解析点；
- 重新核对预期大小和哈希；
- 记录保留副本和恢复方式；
- 每个批准项目独立处理，避免一个失败扩大操作范围。

同一次批准可以同时覆盖同一准确批次的回收暂存和永久删除。只批准暂存不等于批准永久删除。
清空整个回收站需要明确覆盖全部内容的范围；批准一个批次绝不能推导出清空整个回收站的授权。

<a id="reporting-one-drives-recycle-bin-state"></a>
### 报告单个盘的回收站状态

当清理或报告范围限定为一个盘时，解析该盘的 `$Recycle.Bin\<SID>` 目录，并盘点其中的 `$I` 元数据和 `$R` 负载配对。
排除 `desktop.ini` 等非条目控制文件；一个 `$I`/`$R` 配对计为一个逻辑项目，并根据匹配负载计算占用字节数。

`Shell.Application.Namespace(10).Items()` 是跨盘合并视图。它可以用于明确标注为全局的盘点，但不能用其项目数量判断某个盘的回收站为空或非空。
如果某条目实际解析到其他盘，应从目标盘状态中排除，不能把它当作目标盘中的无关条目。

<a id="permanently-removing-one-staged-candidate"></a>
### 永久删除一个已暂存候选

对于准确的已暂存候选，如果批准清单或后续请求已经明确包含永久删除，就使用现有授权，不要仅因暂存完成而重复询问。
保留所有无关回收站条目：

1. 解析候选所在盘的 `$Recycle.Bin\<SID>` 目录，只读盘点其元数据；
2. 找到一条准确的 `$I` 元数据记录，确认解码后的原路径和原始字节数与批准路径一致。对同一路径的重复条目，使用删除时间区分；
3. 只与后缀完全相同的 `$R` 负载配对。目录还要将当前负载的文件数和总字节数与暂存审计比较；文件只需核对负载字节数；
4. 先记录无关回收站条目的名称和大小，然后只永久删除这两个准确的字面路径。单候选批准不得使用通配符、前后缀匹配或 `Clear-RecycleBin`；
5. 验证原路径和准确的 `$I`/`$R` 配对已经消失、无关条目未变化，并且实际可用空间发生合理变化。部分删除应记录为失败，不要扩大清理范围。

如果元数据路径、大小、后缀配对、文件数或暂存审计不能完全匹配，保留该候选并继续其他已核验的批准项目。
不要退回到清空整个回收站。清空整个回收站是独立范围，不能从批准一个候选或批次推导出来。

<a id="pagefile-inspection"></a>
## 页面文件检查

```powershell
$automatic = (Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile
$settings = Get-CimInstance Win32_PageFileSetting |
    Select-Object Name, InitialSize, MaximumSize
$usage = Get-CimInstance Win32_PageFileUsage |
    Select-Object Name, AllocatedBaseSize, CurrentUsage, PeakUsage
```

同时检查内存、系统提交行为、`CrashDumpEnabled` 和盘符可用空间。启动盘上的小页面文件可能满足部分转储要求，
但这个最小值不是普遍适用的性能建议。将系统管理的页面文件放在空间更充足的盘上通常更保守，最终应根据实时证据决定。

给出一个内部一致、包含本机具体数值的建议。C 盘页面文件不能用来提升启动速度；相关因素是崩溃转储和提交限制。
区分转储所需的最小值和保守运行余量。

绝不要把 `pagefile.sys` 当普通文件删除。说明新布局是否需要完整重启 Windows 才能生效，并在重启后核对设置和使用情况。
