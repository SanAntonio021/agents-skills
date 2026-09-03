# Bridge 适配与排错（2026-09-03）

## 两类入口

科研循环有两种用途，不能混淆：

1. 已有兼容任务接口可继续下发执行任务：

```text
submit_peer(target=codex|claude, operation=task, taskProfile=research, ...)
await_peer(job_id, timeout_ms<=45000)
peer_result(job_id)
```

2. 已落盘里程碑统一使用 v3 审查：

```text
v3_review_peer(
  author, target,
  projectRoot=<真实项目绝对路径>, artifactPath=<主文件相对路径>,
  artifactType=deliverable, task, acceptanceCriteria,
  model, reasoningEffort
)
v3_await_peer(job_id, timeout_ms<=45000)
v3_peer_result(job_id)
v3_author_checkpoint(...)
```

旧任务接口的范围和测试字段只属于执行任务。v3 审查不接收 `artifactContent`、`allowedPaths`、
`repairTargets`、`testCommands`、sandbox 或工具列表；Claude CLI 和 Codex App Server 都以真实项目为 cwd，
加载完整工具并可直接修改。

## 里程碑模板

```json
{
  "author": "claude",
  "target": "codex",
  "projectRoot": "D:\\BaiduSyncdisk\\Project",
  "artifactPath": "results/m2/summary.md",
  "artifactId": "research-m2",
  "artifactType": "deliverable",
  "task": "核对 M2 的代码、原始数据、统计和物理结论，必要时直接修复项目。",
  "acceptanceCriteria": ["summary.md 的结论可由保存的数据和脚本复现"],
  "model": "gpt-5.6-sol",
  "reasoningEffort": "max"
}
```

正文、数据和日志留在项目中。请求只写任务和判据，不复制文档全文或秘密值。

## 等待、审批和恢复

- 每次等待最多 45 秒；pending 时继续查询同一 job。
- 502/503/504/524 由 v3 内部在同一 job 和会话额外重试一次，调用方不重发。
- `awaiting_approval` 只批准或拒绝 bridge 展示的精确 action、targets、fingerprint 和 approval ID。
- 批准、拒绝或超时后都继续查询原 job；拒绝或超时只取消该动作，不把审批决定本身写成终态失败。
- 同一真实项目的 v3 job 串行，不同项目可并行。
- 作者验收后调用 `v3_author_checkpoint`；作者改过主文件才运行一次只检查终审。

## 历史 CLI 资料

原生 `codex exec`、`claude -p`、旧 companion、固定副本 sandbox 和 v2 `review_repair` 只用于排查历史
日志或继续既有 job，不是新里程碑审查入口。迁移时保留旧记录，不把 v3 权限降为只读或白名单。
