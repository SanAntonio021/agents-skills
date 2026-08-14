# Bridge 适配与排错（2026-08-14）

## 运行入口

科研里程碑不直接启动 `codex exec`、`claude -p` 或 `codex@openai-codex`。当前唯一运行入口是
`claude-codex-bridge` MCP：

```text
submit_peer(target=codex|claude, operation=task|review_repair,
  targetRoot=<绝对共同根>, allowedPaths=<最小相对路径列表>, artifactId=<稳定 ID>,
  testCommands=<逐条精确测试命令>)
await_peer(job_id, timeout_ms<=45000)
peer_result(job_id)
```

Claude -> Codex 使用 bridge 的 SDK 适配器（`workspace-write`、`approvalPolicy=never`、网络和搜索关闭、
无额外目录）。Codex -> Claude 固定 `claude-opus-5`；`ask` 用空工具和默认权限，`review_repair` 只
开放 `Read,Edit,Write,Bash`、`acceptEdits` 和固定副本。模型、权限和 sandbox 参数不能由提示词覆盖。
Claude 方向的 Bash 不做通配授权；`testCommands` 不得含引号、变量、通配符、重定向、管道或命令串联，
且任何 permission denial 都使本轮失败。
这里的 `workspace-write` 是 bridge 向 SDK 发出的请求，不是外层宿主权限的独立回执；必须用实际文件
与同步哈希证明写入成功。Codex `ask` 另用专用空只读目录，不能从 cwd 读取项目或 bridge 状态。

## 里程碑请求模板

```json
{
  "target": "codex",
  "operation": "task",
  "question": "完成 M2，跑完停下等评审；返回命令、退出码、结果文件和限制。",
  "artifactId": "research-m2",
  "targetRoot": "D:\\BaiduSyncdisk\\Project",
  "allowedPaths": ["src", "results\\m2", "logs\\m2"],
  "acceptanceCriteria": ["results/m2/summary.json 存在且可解析"],
  "testCommands": ["npm.cmd test"]
}
```

完成后另发 `operation=review_repair`，提供 `artifactType=deliverable`、完整内容/证据、当前哈希、
前轮 findings 和相同 allowlist。不要把执行任务和验收任务合并成同一模型回合。

## 长任务、取消与恢复

- 每次 `await_peer` 最多 45 秒；超时只用同一 job 的 `peer_result` 或 `peer_status`。
- `cancel_peer` 只请求并确认目标进程取消；不要删除固定工作区或丢弃线程 ID。
- `resume_peer` 必须给出明确的原 job ID 和 bridge 记录的线程 ID；不得用“最新会话”猜测。
- 删除、重命名、权限或类型变化会返回 `needs_attention`；用户批准精确高风险 ID 后用
  `approve_peer_sync`，这一步不重新调用模型。
- `awaiting_user` 期间固定副本锁继续保留；新的重叠目标根任务应以 `retained_workspace_conflict` 停止。

## 历史 CLI 资料

旧版 `codex exec` 的 `sandbox_mode`、stdin EOF、PowerShell 引号和 Desktop/CLI 会话不互通问题只供
排查旧日志和迁移材料参考。它们不是本工作流的可执行步骤；发现调用方仍依赖旧命令时，停止并迁移到
bridge，而不是增加 `--dangerously-skip-permissions`、网络或额外目录。
