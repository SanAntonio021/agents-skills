# 无头 CLI 适配器（2026-07-07 首验；要点 8-13 条 2026-07-11 增补）

## 使用边界

Claude Code 已加载 `cross-model-orchestration` 时，不使用本文件直接启动 Codex。
每个科研里程碑都通过官方 `codex:codex-rescue` 进入通用编排的复核、执行和验收闭环。
本文件只供没有 Claude Code Plugin 的独立无头环境使用，或用于排查底层 CLI 问题。

## 适配器 A：独立无头 Claude 监督 → Codex 执行（兜底）

命令模板（由独立无头调度器在后台运行）：

```bash
cd "<项目目录>" && codex exec --skip-git-repo-check \
  -c sandbox_mode="workspace-write" \
  - <<'EOF'
<多行任务指令，里程碑为单位，结尾写"跑完停下等评审">
EOF
```

要点与坑（均实际踩过）：

1. `--skip-git-repo-check`：目标目录不是受信任 git 仓库时必加，否则退出码 1 报 "Not inside a trusted directory"。
2. `-c sandbox_mode="workspace-write"`：**codex exec 默认 read-only**，执行者建目录/写文件会被 "rejected: blocked by policy" 拦下且任务看似正常退出。凡任务要产出文件必加此参数。
3. heredoc 用 `<<'EOF'`（单引号），防止任务文本里的 `$`、反引号被 shell 展开。
3a. 反爬站点的事实核验任务（查官网、核对官方名称等），在任务书里指明走 `web-access` 技能的 CDP 通道——执行者经用户真实浏览器实访，能过 403 反爬；监督者侧的 WebFetch/无头抓取会被同一站点挡住，此时监督者旁证改用搜索引擎快照（2026-07-11 验证：厂商官网 403 挡 WebFetch，CDP 实访正常）。
4. 用后台进程和日志轮询管理；不要与 Claude Code Plugin 的 job 管理混用。
5. **会话不互通**：Codex Desktop 创建的会话无法用 CLI `codex exec resume <id>` 续接（版本/格式不兼容，报 "does not start with session metadata"）；CLI 创建的会话在 Desktop app 里不可见。跨入口续接的正确做法：新开 exec 会话，把上下文（文件路径 + 评审意见）写进任务指令——文件系统是共享的，会话不必共享。
6. 会话记录落盘位置：`~\.codex\sessions\<yyyy>\<MM>\<dd>\rollout-*.jsonl`，可解析出执行过程用于排查；终端里 `codex resume` 可列出并进入 CLI 会话。
7. 执行者的模型/推理档由 `~\.codex\config.toml` 决定，无需在命令里指定。
8. **参数形态传 prompt 时的 stdin 阻塞**：不用 heredoc、把任务文本当参数传时，若调用方的 stdin 是打开的非 TTY 管道（后台运行、harness 调度都属此类），codex 打印 `Reading additional input from stdin...` 后永久等 EOF。必须显式关闭：Bash 结尾加 `</dev/null`，PowerShell 用 `$null | codex exec ...`。heredoc 形态天然无此问题。
9. **PowerShell 5.1 会拆坏参数**：prompt 含 ASCII 双引号会被从引号处拆成多段（报 `unexpected argument`）；`-c key=["a","b"]` 数组值的内层引号会被吃掉（TOML 报 expected a sequence）。解法：这类调用改用 Git Bash 发起；或把 prompt 写入 UTF-8 文件、确认无内嵌 ASCII 双引号后 `$p = Get-Content -Raw -Encoding UTF8` 再传参。
10. **resume 的选项顺序**：断线后 `codex exec resume <session-id> "<新指令>"` 可完整恢复上下文（中转 502 断后同一 session id 实测有效）；但全局选项（`--sandbox`、`-c`、`--cd`、`--output-last-message`）必须放在 `resume` 子命令**之前**，放后面报 `unexpected argument`。续跑前先盘点落盘状态（git status + 目标文件清单），分清哪些改动已落地，避免半成品误判。
11. **workdir 之外定向开写权**：`--sandbox workspace-write -c 'sandbox_workspace_write.writable_roots=["C:/path1","C:/path2"]'`，比 `danger-full-access` 收敛；启动 banner 会回显生效的可写目录清单，据此确认。
12. **`--output-last-message <file>`**：执行者最终消息落盘成文件，监督者直接读文件验收，不用从 stdout 日志里扒。
13. **执行者的 apply_patch 包装坑**：执行者在 PowerShell 里用 here-string 包 `apply_patch` 会破坏补丁末行校验（报 `The last line of the patch must be '*** End Patch'`）。任务书里提醒执行者用原生 apply_patch，或改用 `(Get-Content -Raw) -replace` + `Set-Content -Encoding utf8`，写完读回验证。

## 适配器 B：Codex 监督 → Claude 执行（镜像形态）

在 Codex 会话中调用 Claude Code 无头模式：

```bash
cd "<项目目录>" && claude -p "<任务指令>" \
  --permission-mode acceptEdits \
  --output-format text
```

要点：

1. `claude -p`（print/headless 模式）与 `codex exec` 机制对等：单次任务、跑完退出、stdout 返回结果。
2. 写文件权限用 `--permission-mode acceptEdits`；需要运行命令时只开放任务所需的最小 `--allowedTools` 范围。不要使用 `--dangerously-skip-permissions`。
3. 长任务同样建议后台 + 轮询输出文件，Codex 侧用其后台 exec 能力。
4. 本形态下监督/评审职责移到 Codex（GPT）侧，Claude 变执行者——异族红线依然满足。

## 形态选择

| 场景 | 用哪个 |
| --- | --- |
| 日常（Claude Code 是驾驶舱） | 使用 `cross-model-orchestration` + 官方 Plugin，不用本文件适配器 |
| Claude 额度耗尽 / 在 Codex 桌面版临时作业 | B：Codex 监督 + claude -p 执行 |
| 禁用 | 同族监督执行（Codex↔Codex、Claude↔Claude） |
