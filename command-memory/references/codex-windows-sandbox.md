# Codex Windows Permissions And Sandbox Recovery

## 策略拒绝与许可变更

先判断失败发生在哪一步，再决定如何重试：

| 已有证据 | 可得结论与下一步 |
| --- | --- |
| 工具在 shell 启动前返回 `Rejected: blocked by policy` | 该调用内的命令未执行。只凭这句话无法确定具体规则或审核组件，不归因于 Windows、杀毒软件或某个目录的固定保护策略。 |
| shell 已启动，受限执行返回 `Access denied` / `Permission denied` | 只能确认本次访问失败；核对当前沙箱范围和目标，再判断是否需要受支持的审批。尚不能认定为 Windows ACL 或文件占用。 |
| 当前允许的审批执行仍失败，且日志、ACL 或占用者检查给出具体证据 | 按已确认的 ACL、sandbox setup 或占用问题处理；升级执行本身不保证管理员权限，也不保证解除文件锁。 |

用户说已更改许可并要求重试时：

1. 重新读取当前 turn 提供的 sandbox 模式、可写目录、审批策略和工具参数；全局配置或上一轮权限不能代替当前执行约束。用户对任务的授权继续有效，但不等于工具已放行。
2. 复查原动作及准确绝对路径。删除前重新确认目标仍可清理、没有正在使用的文件，以及解析后的目标没有越出已确认范围；只读验收与删除分开调用。
3. 当前工具明确支持且策略允许时，通过 `exec_command` 的 `sandbox_permissions="require_escalated"` 提交同一范围的动作，用 `justification` 说明具体目标和用途。这是工具审批请求，不是 Windows UAC 提权；不要虚构其他工具拥有这些参数。
4. 审批不可用或再次拒绝时，停止依赖该权限的操作，保留原始错误并说明受阻动作；继续独立检查。不得用换 shell、换 API、改账户或自行放宽 ACL 来规避拒绝。更安全的替代动作也须在既有授权内，不能把原动作换个接口执行。
5. 审批通过且命令完成后，独立检查实际文件状态和验收结果。用户说许可已改、审批通过或一次退出码成功，都不能单独证明清理完成。

回收站和空间释放的判定沿用 `windows-storage-cleanup`；这里不重复清理流程。只有出现下面列出的 setup / ACL 子错误时，才进入对应恢复步骤。

## Sandbox ACL 刷新失败

适用：Codex 在 Windows 的 `workspace-write` 模式下读取正常，但第一次写入前失败，错误包含：

```text
windows sandbox failed: helper_unknown_error: setup refresh had errors
```

也适用于日志里的 `read ACL run had errors` 或 `SetNamedSecurityInfoW failed: 5`。

## 先分清两种 sandbox

- Codex 原生 Windows sandbox 有两种实现。`elevated` 使用专用低权限 sandbox 用户、
  文件权限边界、防火墙规则和本地策略；`unelevated` 使用当前用户派生的 restricted
  token、ACL 文件边界和环境级离线控制。官方说明见
  [Windows sandbox](https://developers.openai.com/codex/codex-manual.md#windows-sandbox)。
- Windows 可选功能“Windows Sandbox”是虚拟机。上述两种 Codex 原生实现都不依赖它，
  不要看到 `windows sandbox failed` 就启用 `Containers-DisposableClientVM`。
- 在 Codex CLI 0.144.1 的本次实测中，`codex doctor --json` 的 `sandbox.helpers` 只返回
  `sandbox configuration is readable`，没有实际测试 `workspace-write` ACL refresh。
  因此显示 `ok` 不能排除本故障；其他版本先查看 doctor 的实际检查项，不做跨版本假定。

## 定位决定性子错误

1. 先确认实际 turn 是 `workspace-write`，不要只看全局 `sandbox_mode`。Claude Code
   Plugin 的 `--write` turn 可以覆盖全局默认。
2. 读取最新 `%USERPROFILE%\.codex\.sandbox\sandbox.YYYY-MM-DD.log`，搜索：

```powershell
rg -n "setup refresh|granting write ACE|SetNamedSecurityInfoW|read ACL run" `
  "$env:USERPROFILE\.codex\.sandbox\sandbox.*.log"
```

3. 在对应 rollout 的 `turn_context` 里检查 permission profile 是否含 `:slash_tmp` 和
   `:tmpdir`，以及 `exclude_slash_tmp` 的值。
4. 检查失败目录的 owner 和当前用户是否有 `WRITE_DAC`。`Modify` 允许改文件，不代表
   可以改 ACL。

## 已验证根因和优先修复

Codex CLI 0.144.1 的一次实测中，`workspace-write` permission profile 同时加入
`:slash_tmp` 和 `:tmpdir`。`:slash_tmp` 在 Windows 按当前工作目录盘符解析成
`C:\tmp` 或 `D:\tmp`。这两个目录由 `BUILTIN\Administrators` 拥有，普通进程无权为
sandbox group 和 capability SID 刷新 ACL，于是整个写入前置 setup 失败。

优先在全局 `config.toml` 保留用户临时目录、排除 `:slash_tmp`：

```toml
[sandbox_workspace_write]
exclude_slash_tmp = true
```

这不是绕过 sandbox。工作目录和用户 `TMPDIR` 仍受 `workspace-write` 约束，只移除不必要
且无法维护 ACL 的盘符根 `\tmp`。

## 验证

1. 在可丢弃目录准备一个 marker 文件。
2. 不带临时 `-c` 覆盖，运行一次真实 `codex exec -s workspace-write` 写入探针。
3. 检查 marker 的字节数、SHA256 和目录文件集合。
4. 检查当天 sandbox 日志：
   - setup 行为 `errors=[]`；
   - 不再出现 `granting write ACE to C:\tmp` 或 `D:\tmp`；
   - 没有新的 `setup refresh completed with errors`。
5. 如果故障来自 Claude Code Plugin，再新开 Claude 会话跑一次实际 Plugin 写入，不用
   直接 CLI 探针代替最终集成验证。

## 不要这样处理

- 不用 `--yolo`、`--dangerously-bypass-approvals-and-sandbox` 或同类参数掩盖失败。
- 不因错误文本包含 Windows sandbox 就启用 Windows Sandbox 虚拟机功能。
- 不先对 `C:\tmp`、`D:\tmp` 执行递归 `takeown` 或 `icacls`。这会扩大权限影响面。
- 不把 `codex sandbox windows --help` 当子命令；当前 CLI 会把 `windows --help` 当作
  要在 sandbox 内启动的程序。
- 不只看 `codex doctor` 或 `/v1/models` 就宣布修复。

如果当前 Codex 版本不再支持 `exclude_slash_tmp`，或业务必须写盘符根 `\tmp`，再考虑经
用户确认后由管理员做目录本身的最小 ACL 修复；先记录 owner、现有 ACE、回滚方法和重启
要求，不递归扩大授权。
