# Codex Windows Sandbox ACL Recovery

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
