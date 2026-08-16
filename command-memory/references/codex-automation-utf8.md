# Codex 自动任务迁移与 UTF-8

用途：只在 Codex 自动任务需要在 `heartbeat` 与 `project cron` 间迁移，或中文、符号等非 ASCII 名称/提示经过 PowerShell、Python 或其他子进程传给自动任务 API 后损坏时读取。

## 先保留原配置

迁移或修复前，先用只读 API 状态或现有配置记录以下字段：名称、提示、schedule、status、model、reasoning effort、execution environment 和 target。迁移的目标是改变任务类型或 target，不是顺手改变这些语义。

- 不要手改 `automation.toml`。通过宿主提供的 `codex_app__automation_update` 更新；TOML 只可作为写后核验的只读证据。
- 已经乱码的文本不能靠再次转码可靠恢复。先从原始来源、上一次正确配置或保存的 UTF-8 Base64 值找回正确文本。
- 先确认要修复的是传输损坏，不要把终端显示乱码直接当作配置本体已经损坏。

## 用 ASCII 通过子进程边界

PowerShell 的 `OutputEncoding` 对人读终端输出有帮助，但不能证明“子进程 -> PowerShell -> 工具调用”这条多跳链路会保住 Unicode。把准确文本作为 UTF-8 Base64（只含 ASCII）通过子进程边界，再在实际调用自动任务 API 的环境中解码。

```powershell
$originalText = Get-Content -LiteralPath <SOURCE_FILE> -Raw -Encoding UTF8
$utf8Base64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($originalText))
$utf8Base64
```

- 子进程只输出 `$utf8Base64`，不要把 `$originalText` 再经 stdout、JSON 字符串或 here-string 传一遍。
- 调用工具的一侧从 Base64 按 UTF-8 解码后，直接把得到的 Unicode 值传给 `codex_app__automation_update`；不要从终端渲染结果复制名称或提示。
- 写后把 API/TOML 读回的名称和提示重新编码为 UTF-8 Base64，与原始 Base64 逐字相等才算修复成功。只看“显示正常”不够。

## 迁移步骤

1. 先读出旧任务并保存上述字段；确认归档安全目标和所需 `project` target。
2. 优先原地把任务转为目标类型。若 API 不支持原地转换，先构造一个未激活的替代任务，并在不影响旧任务的状态下核验其完整字段。
3. 替代任务核验通过后，再暂停旧任务并激活替代任务；不要让两个每周任务同时处于 ACTIVE。
4. 最后重新读取全部自动任务，确认只剩一个对应的 ACTIVE 周检。

归档当前 task 后仍需保留的周检，最终状态至少应满足：

- `kind=cron`
- `target.type=project`，且 project 与预期一致
- schedule、model、reasoning effort、execution environment 与保存的基线一致
- 没有 `target_thread_id`
- 只有一个 ACTIVE 的同类周检

若替代任务无法先以非 ACTIVE 状态创建或核验，停止并说明 API 限制；不要为了赶迁移而留下两个 ACTIVE 周检，也不要靠手改 TOML 绕过限制。

## 完成判据

一次修复或迁移只有同时满足以下条件才算完成：自动任务 API 已成功写入、读回状态满足目标类型与 target、名称和提示的 UTF-8 Base64 与原始值完全一致、ACTIVE 周检数量为一。任何一项缺失，都保留当前状态并报告缺的证据，不宣称迁移完成。
