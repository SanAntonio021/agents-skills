# Claude–Codex Bridge v3 互审契约

## 适用面

已落盘的正式计划和用户明确要求审查的交付物使用 protocol v3。v3 让对端在真实项目中使用完整原生
工具，自行按路径读取并可直接修改；bridge 不复制文件正文。未落盘内容和旧调用方继续使用 v2 inline
兼容流程。

正式计划通过后仍需用户确认才能执行。普通执行、测试、提交和交付不自动追加互审。

## 入口与身份

主入口为 `http://127.0.0.1:43123/mcp`。Codex 和 Claude 均使用
`CLAUDE_CODEX_BRIDGE_TOKEN`；token 只认证 loopback 调用，不证明 `author`。

每次 v3 请求显式提供：

```json
{
  "author": "codex | claude",
  "target": "claude | codex（必须与 author 不同）",
  "projectRoot": "现有绝对目录",
  "artifactPath": "projectRoot 下现有普通文件的相对路径",
  "artifactId": "可选稳定标识",
  "artifactType": "plan | deliverable",
  "task": "本轮任务",
  "acceptanceCriteria": ["至少一项"],
  "constraints": [],
  "taskProfile": "可选 profile",
  "model": "目标侧精确白名单模型",
  "reasoningEffort": "可选合法强度"
}
```

`artifactContent`、`targetRoot`、`repairTargets`、`allowedPaths`、`testCommands`、sandbox 和工具
列表不是 v3 字段。出现额外字段时在创建 job 前拒绝。bridge 对 `projectRoot` 取 realpath，并拒绝
绝对 `artifactPath`、路径穿越、目录或不存在的主文件。

## 能力门

调用 `v3_peer_status` 后至少验证：

```text
protocol_version = 3
active = true
capabilities.pathReviews = true
capabilities.artifactContentAccepted = false
capabilities.realProjectCwd = true
capabilities.fullNativeTools = true
capabilities.directProjectWrites = true
capabilities.claudeTransport = cli
capabilities.codexTransport = app_server
```

Claude 子会话以真实 `projectRoot` 为 cwd，加载 user/project/local settings、项目规则、技能、插件、
MCP、网络和默认完整工具。Codex 使用 bundled App Server、真实 cwd、`runtimeWorkspaceRoots`、
`dangerFullAccess` 与临时 thread，同时保留原生配置、规则、技能、插件、MCP 和网络。两端只移除
bridge 的长期 MCP token，并以 `BRIDGE_CHILD=1` 阻止递归 bridge 调用。

不得把 v3 改成 read-only、safe mode、快照、固定副本、文件白名单或缩减工具集。

## 首轮

调用：

```text
v3_review_peer(完整 v3 请求)
[v3_await_peer(job_id, timeout_ms <= 45000) -> v3_peer_result(job_id)] 循环
```

对端先从磁盘读取最新主文件和必要项目上下文，可直接修改真实项目。bridge 在 dispatch 前后记录主
文件 SHA-256，并要求结果符合：

```json
{
  "kind": "final_review",
  "verdict": "pass | needs_changes | disagreement",
  "summary": "...",
  "confirmed": [],
  "findings": [
    {"summary": "...", "rationale": "...", "path": "可选", "line": 1}
  ],
  "requiredChanges": [],
  "risks": []
}
```

请求模型必须由对端运行时精确回报；缺失或不同即失败。单次 await 返回非终态时继续等待同一 job，
不另开 job、不换模型、不降档。

## 作者复查与终审

首轮成功后 phase 为 `awaiting_author`。原作者必须重新读取最新主文件、检查对端改动和 review，
并可自行修改。随后调用：

```json
{
  "author": "原作者",
  "seriesId": "首轮 series_id",
  "seriesVersion": "首轮最新 series_version",
  "latestJobId": "首轮 latest_job_id"
}
```

- `author_modified=false`：不再调用模型，直接向用户呈现最新文件和首轮结论；非 pass 也交给用户。
- `author_modified=true`：用首轮完全相同的身份、任务、验收、约束和路由字段，加 checkpoint
  返回的 `seriesId/seriesVersion/latestJobId` 再调用 `v3_review_peer`。

第二次 peer job 的 stage 为 `final_check`，只能检查，不能修改。主文件在终审中变化时 job 失败。
终审的 pass、needs_changes 或 disagreement 都直接交给用户，不继续循环。

bridge 在可交付结论上保存 `conclusion_sha256`。每次 `v3_peer_result` 都重读主文件：
`conclusion_valid=true` 才能引用旧结论；文件变化或消失时 `stale=true`，旧结论失效。

## 高风险动作批准

普通可见工具调用自动允许，包括删除项目内一个普通文件。以下明确动作暂停：

- 多目标、递归、通配符、目录、项目外删除；
- 远程删除；
- `git reset --hard`、`git clean`、`git restore`、`git checkout --`、清空 stash 等丢弃修改；
- DROP、TRUNCATE 或无条件 DELETE 等数据库清空。

public job 在 `awaiting_approval` 时返回：

```text
approval_id
action
action_fingerprint
targets = 完整规范化目标清单
created_at
expires_at
state
```

一次只向用户确认该精确动作。批准或拒绝时把 `jobId`、`approvalId`、fingerprint 和完整 targets
不变地传给 `v3_resolve_approval`。缺少、增加、重排或改写目标均拒绝。批准有效期 24 小时；拒绝
或超时取消该动作。相同 job 内再次出现相同规范化 action+targets 才可复用批准。

该门只覆盖 hook 或 App Server 事件中明确的工具名和参数。普通程序内部未显式暴露的删除不在保证
范围内，报告中不得声称已检测。

## 稳定性、会话和并发

对完整 502/503/504/524 失败，bridge 仅额外重试一次。重试保持同一 job、模型、项目、文件和会话，
保留前次已完成修改，并要求重新读取最新文件。调用方不叠加重试或切供应商。

同一个 realpath `projectRoot` 同时只运行一个 v3 job；其他项目可并行，总活动 job 不超过 bridge
全局限制。排队、运行和等待批准都纳入 health/status 的 v3 activity，并阻止停机、token 轮换和路由
配置变更。

Claude session 或 Codex ephemeral App Server process 保留到本轮、审批和单次外层重试结束。bridge
先清理会话和 transient session ID，再发布 terminal job。daemon 重启会把未终态 job 标为失败并清理
已记录的精确 Claude session ID。

## 记录与秘密

长期 v3 记录只保存清理后的任务、路径、模型、路由、各轮哈希、耗时、尝试/重试计数、审批元数据、
结构化结果和错误。不得保存文件正文、完整 prompt、transcript、原始工具参数或工具输出。

密码、API key、token、Cookie、session 值、私钥、认证头和设备登录值不得主动写入 prompt、日志或
报告。输入任务、模型结果、错误和审批目标在持久化或公开前脱敏。bridge 长期 MCP token 不进入 peer
环境；内部 hook 只收到本 job 临时 token。

## v2 inline 兼容

没有可靠落盘路径时，可调用：

```text
v2_review_peer(
  author,
  artifactType,
  artifactMode=inline,
  artifactContent,
  artifactBytes,
  artifactSha256,
  acceptanceCriteria,
  constraints,
  model/reasoningEffort
)
v2_await_peer -> v2_peer_result
```

v2 inline 固定 zero-tool 和只读，继续使用 `completion_receipt`。旧 v2 workspace、
`v2_review_repair_peer`、CAS、同步和批准工具保持兼容，但保存文件的新流程不得默认使用。v3 失败
不能自动回退 v2，也不能通过旧协议绕过高风险审批。

## 用户门与失败

互审结果只是用户决策材料。向用户报告 peer 是否修改、作者是否修改、终审是否运行、最终主文件
SHA-256 是否仍有效，以及 pass、未决问题或分歧；获得明确确认后才能执行正式计划。

路径无效、MCP 不可达、精确模型缺失、结果 schema 错误、会话清理失败、审批拒绝/过期或终审写入
都保留原 job/series 和清理后的错误。pending 不是失败也不是最终答复。不得伪造 completion、扫描
其他 job、降低模型、创建重复 job 或替用户裁决。
