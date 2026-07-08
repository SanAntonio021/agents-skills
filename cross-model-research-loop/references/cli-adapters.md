# 无头 CLI 适配器（2026-07-07 验证）

## 适配器 A：Claude 监督 → Codex 执行（默认形态）

命令模板（在 Claude Code 的 Bash 中，后台运行）：

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
4. 用后台方式运行（Claude Code 的 run_in_background），完成通知会自动唤醒监督者；输出日志路径在启动返回里，中途可读它查进度。
5. **会话不互通**：Codex Desktop 创建的会话无法用 CLI `codex exec resume <id>` 续接（版本/格式不兼容，报 "does not start with session metadata"）；CLI 创建的会话在 Desktop app 里不可见。跨入口续接的正确做法：新开 exec 会话，把上下文（文件路径 + 评审意见）写进任务指令——文件系统是共享的，会话不必共享。
6. 会话记录落盘位置：`~\.codex\sessions\<yyyy>\<MM>\<dd>\rollout-*.jsonl`，可解析出执行过程用于排查；终端里 `codex resume` 可列出并进入 CLI 会话。
7. 执行者的模型/推理档由 `~\.codex\config.toml` 决定，无需在命令里指定。

## 适配器 B：Codex 监督 → Claude 执行（镜像形态）

在 Codex 会话中调用 Claude Code 无头模式：

```bash
cd "<项目目录>" && claude -p "<任务指令>" \
  --permission-mode acceptEdits \
  --output-format text
```

要点：

1. `claude -p`（print/headless 模式）与 `codex exec` 机制对等：单次任务、跑完退出、stdout 返回结果。
2. 写文件权限用 `--permission-mode acceptEdits`；更高权限（跑命令）按需用 `--dangerously-skip-permissions`，仅限可信项目目录。
3. 长任务同样建议后台 + 轮询输出文件，Codex 侧用其后台 exec 能力。
4. 本形态下监督/评审职责移到 Codex（GPT）侧，Claude 变执行者——异族红线依然满足。

## 形态选择

| 场景 | 用哪个 |
| --- | --- |
| 日常（Claude Code 是驾驶舱） | A：Claude 监督 + Codex 执行 |
| Claude 额度耗尽 / 在 Codex 桌面版临时作业 | B：Codex 监督 + claude -p 执行 |
| 禁用 | 同族监督执行（Codex↔Codex、Claude↔Claude） |
