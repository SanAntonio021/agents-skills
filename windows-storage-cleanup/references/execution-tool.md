# 通用文件执行工具

供智能体调用；Windows + PowerShell 7，不提供界面、提权、进程终止或通用强删开关。
沿用用户对具体范围和动作的授权，不要求用户抄写哈希或再次批准已明确的步骤。
工具只能检查清单一致性，不能自行证明用户授权，也不能判断材料的业务价值。

## 调用

```powershell
pwsh -NoProfile -File <skill>/scripts/Invoke-StorageCleanup.ps1 `
  -Mode Check -ManifestPath <absolute-manifest.json>

# 用户已批准清单后执行；状态位置由智能体按本机环境明确选择。
pwsh -NoProfile -File <skill>/scripts/Invoke-StorageCleanup.ps1 `
  -Mode Execute -ManifestPath <absolute-manifest.json> -StateDirectory <absolute-local-state>
```

`Check` 为默认模式，只读。`Resume` 对账后继续，`Verify` 只读核验，二者使用原清单及原状态目录。
标准输出为 JSON，错误为结构化标准错误；退出码 0 表示本次模式检查或处理成功，2 表示有保留/待处理项，1 表示整批受阻。
不要仅根据退出码声称永久删除成功，须读取每项状态和对应处理方式。

状态目录须位于明确确认不参与同步的本地普通目录；与清单源、保留副本和归档位置隔离。
不要使用网盘目录、待删目录或在两个位置之间自动切换状态。清单路径不应落在任何待处理子树内。
工具对已知同步位置作防护，但不能发现所有第三方同步软件；位置确认仍是调用者职责。

## 清单 v1

UTF-8 JSON，`schemaVersion: 1`，稳定 `batchId`，`approvedRoots` 为获准处理的绝对根目录，`items` 为准确条目。
以下仅为结构示例，路径、时间和哈希须由实际只读盘点产生，不能直接执行示例：

```json
{
  "schemaVersion": 1,
  "batchId": "example-batch",
  "approvedRoots": ["C:\\ExampleSource"],
  "items": [{
    "id": "export-01",
    "source": "C:\\ExampleSource\\old-export.bin",
    "kind": "file",
    "action": "archive_then_purge",
    "bytes": 1024,
    "lastWriteTimeUtc": "2026-01-01T00:00:00.0000000Z",
    "sha256": "<64 hexadecimal characters from the source>",
    "archiveDestination": "D:\\ExampleArchive\\old-export.bin"
  }]
}
```

动作：

- `recycle`：移入系统回收站并核验，保留条目，不把处理字节当作已释放空间。
- `recycle_then_purge`：同一授权覆盖回收和永久删除本批准确条目。
- `archive_then_purge`：归档完整核验后，回收源并永久删除本批对应条目；归档目的地必须明确。

每个文件必须记录大小、UTC 修改时间、SHA-256。删除依据是独立副本时，还需 `retainedCopy`；工具对照源清单验证副本可读、内容一致并独立于源。
目录使用 `kind: "directory"`，`bytes` 为所有成员文件大小之和；`members` 必须列出每个后代，包括空目录：

```json
[
  {"relativePath":"data", "kind":"directory", "bytes":0,
   "lastWriteTimeUtc":"2026-01-01T00:00:00.0000000Z"},
  {"relativePath":"data\\result.bin", "kind":"file", "bytes":1024,
   "lastWriteTimeUtc":"2026-01-01T00:00:00.0000000Z", "sha256":"<SHA-256>"}
]
```

清单不得包含通配符、替代数据流、重复或父子重叠目标。目录盘点和哈希计算时不跟随链接、不下载占位文件。
使用完整盘符路径；首版保守拒绝短文件名别名、网络路径、系统维护目录和安装目录。硬链接的全部别名须在本批明确成员中，否则保留该项。
只读 `Check` 通过不表示批准：将准确范围、方式、恢复限制和物理释放估计展示给用户；批准后冻结清单原始字节。
SHA-256 绑定的是清单原始字节，重排 JSON 或改空白也会改变批次；不得为了通过续作而修改旧状态哈希。

## 续作与结果解释

状态保存动作前意图和动作完成后的核验结果。回收站配对、归档归属和已清除项均从同一批次证据恢复，不能仅凭源文件消失判成功。
归档冲突不覆盖；仅属于本批且核验一致的中间产物允许继续。日志持久化失败停止后续破坏动作；日志损坏或证据不足保留现场并报告，不手工补写“已完成”。

`Resume` 不重新扫描扩大范围，不重写清单，不重跑整批临时脚本。变化、占用、权限不足或未知重解析点只保留相关项；无法可靠记账或清单不匹配则整批停止。
永久删除前必须准确识别当前卷、SID 下本批产生的回收记录与负载，歧义不能按“最近一条”猜测。
部分永久删除必须对账，不能清空全站作为补救。其他用户或任务的回收站变化与本批变化分开报告。

硬链接按实际文件对象去重；只删除其中部分别名通常不释放数据空间。
报告分别展示处理逻辑字节、预计可释放字节及每盘实测变化；后台活动会改变实测值。
预计释放量按源文件对象计算，不包含归档目的盘新增占用；跨盘净变化须同时查看源盘和目的盘。断点续作时，逻辑处理量只反映本次重新检查的源，最终完成范围以逐项结果为准。
首次使用新机器或回收站格式不支持时，先在隔离样本确认，不能拿用户资料试探。

## 验收

使用 `tests/Test-StorageCleanup.ps1` 创建的隔离样本运行测试；不调用真实业务清单做验收。
运行 `pwsh -NoProfile -File <skill>/tests/Test-StorageCleanup.ps1`；跨卷测试另传 `-CrossVolumeRoot <existing-local-directory-on-another-drive>`。
测试自行在给定根下创建随机命名的样本子目录，不将根目录作为清理目标；保留样本和准确回收记录供核验，不清空系统回收站。
保持已有 WizTree 汇总和应用官方清理能力；本工具首版不替代系统维护、卸载、数据库整理或云端备份核验。
