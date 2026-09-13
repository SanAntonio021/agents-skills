# Claude–Codex Bridge v3 互审契约

## 适用面

文件与消息材料统一使用 protocol v3。对端在真实项目中使用完整原生工具：file 分支按路径读取并可
直接修改，message 分支单轮交流，无须落盘。v2 inline 仅供明确指定旧协议或旧调用方兼容。

正式计划通过后，尚未获得执行授权时交给用户确认；已有授权继续有效。普通执行、测试、提交和交付
不自动追加互审。显式科研循环的里程碑继续条件见 [research-loop.md](research-loop.md)。

## 入口与身份

主入口为 `http://127.0.0.1:43123/mcp`。Codex 和 Claude 均使用
`CLAUDE_CODEX_BRIDGE_TOKEN`；token 只认证 loopback 调用，不证明 `author`。

每次 v3 请求显式提供：

```json
{
  "author": "codex | claude",
  "target": "claude | codex（必须与 author 不同）",
  "projectRoot": "现有绝对目录",
  "artifactPath": "可选；projectRoot 下现有普通文件的相对路径",
  "artifactContent": "可选；材料正文",
  "context": "可选；补充上下文",
  "artifactId": "可选稳定标识",
  "artifactType": "plan | deliverable；省略时 deliverable",
  "task": "本轮任务",
  "acceptanceCriteria": [],
  "constraints": [],
  "taskProfile": "可选 profile",
  "model": "目标侧精确白名单模型",
  "reasoningEffort": "可选合法强度"
}
```

`author/target/projectRoot/task/model` 必填；验收条件可省略或为空。`targetRoot`、`repairTargets`、
`allowedPaths`、`testCommands`、sandbox 和工具列表不是 v3 字段，不通过未知字段扩大执行能力。
bridge 对 `projectRoot` 取 realpath；有 `artifactPath` 即 file 分支，拒绝绝对路径、穿越、目录或
不存在的主文件；`artifactContent/context` 是补充内容，磁盘文件仍为主文件依据。无 `artifactPath`
即 message 分支，可直接传正文和上下文，也可只传完整任务，不因缺少文件、验收或类型而拒绝。

## 能力门

调用 `v3_peer_status` 后至少验证：

```text
protocol_version = 3
active = true
capabilities.pathReviews = true
capabilities.artifactContentAccepted = true
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

file 对端先读取最新主文件与必要项目上下文，可直接修改真实项目；bridge 在 dispatch 前后记录主文件
SHA-256。message 不建主文件、不计算主文件哈希、不进入作者 checkpoint 和终审；单轮结果交主模型处理。

两分支均接受普通文本、Markdown、代码块和不完整 JSON。公开结果返回完整、已脱敏的 `responseText`
与 `interpretationRequired`；主模型读取实际意见并结合证据判断。`succeeded` 只表示交互成功，不表示
审查通过。不得从“通过”等关键词、字段缺失或宽松解析自动推断 pass，也不为格式问题启动整理轮、
返工、额外模型请求或审批。以下旧结构仅用于可提取时的兼容，不是回复的强制格式：

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

仅 file 首轮成功后 phase 为 `awaiting_author`。原作者必须重新读取最新主文件、检查对端改动和回复，
并可自行修改。随后调用：

```json
{
  "author": "原作者",
  "seriesId": "首轮 series_id",
  "seriesVersion": "首轮最新 series_version",
  "latestJobId": "首轮 latest_job_id"
}
```

- `author_modified=false`：不再调用模型，呈现最新文件和首轮结论，按下述主模型收尾规则处理意见；
  已授权科研里程碑按科研分支继续。
- `author_modified=true`：用首轮完全相同的身份、任务、验收、约束和路由字段，加 checkpoint
  返回的 `seriesId/seriesVersion/latestJobId` 再调用 `v3_review_peer`。

第二次 peer job 的 stage 为 `final_check`，只能检查，不能修改。主文件在终审中变化时 job 失败。
终审后不追加审查阶段，也不另开 series。原作者重读最新文件和结果，依据证据采纳、修正或不采纳
needs_changes 或 disagreement 中的意见，完成相关验证。小问题和技术分歧自行处理；只有目标、范围
或重要取舍需要用户决定时暂停依赖步骤。科研里程碑按科研分支继续条件处理。

bridge 在可交付结论上保存 `conclusion_sha256`。每次 `v3_peer_result` 都重读主文件：
`conclusion_valid=true` 才能引用旧结论；文件变化或消失时 `stale=true`，旧结论失效。主模型收尾后
再次读取结果，分别报告“对端结论”和“主模型修正及验证结果”，不得把旧哈希的通过写成对端对新文件
通过。验证失败或证据不足如实保留，不能强行宣布完成。

## 权限与历史审批兼容

新任务不产生桥接器审批记录，不按删除数量、递归、目录、远程操作、Git 丢弃修改或数据库清空等
命令形式触发 `awaiting_approval`。执行模型依据任务授权、实际目标和文件保护规则行动，超出授权时
自行询问用户。认证、项目路径检查、终审只读、并发和会话清理约束继续生效。

历史审批记录、类型和 `v3_resolve_approval` 接口保留。迁移后的历史审批可接受用户明确的精确 resolve，
只在 schema 4 保存决策，不改写 schema 3、不恢复执行。以下同会话继续语义仅用于切换前旧 daemon。
发布前等待活动任务结束，不自动批准旧的待审批动作。旧 public job 在 `awaiting_approval` 时返回：

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
或超时只取消该动作。处理审批后继续查询同一 job；bridge 保留同一会话，获批时重试原动作，拒绝
或过期时绕过该动作继续。只有对端随后返回终态失败，整轮才失败。相同 job 内再次出现相同规范化
action+targets 才可复用批准。

历史接口不用于给新任务另建逐项审批、审批例外清单或宽松模式。

## 稳定性、会话和并发

对完整 502/503/504/524 失败，bridge 仅额外重试一次。重试保持同一 job、模型、项目、文件和会话，
保留前次已完成修改，并要求重新读取最新文件。调用方不叠加重试或切供应商。

同一个 realpath `projectRoot` 同时只运行一个 v3 job；其他项目可并行，总活动 job 不超过 bridge
全局限制。排队、运行和旧任务等待批准都纳入 health/status 的 v3 activity，并阻止停机、token 轮换和路由
配置变更。

Claude session 或 Codex ephemeral App Server process 保留到本轮和单次外层重试结束，旧任务还包括历史审批。bridge
先清理会话和 transient session ID，再发布 terminal job。daemon 重启会把未终态 job 标为失败并清理
已记录的精确 Claude session ID。

## 记录与秘密

长期 v3 记录保存输入元数据、路径、模型、路由、file 各轮哈希、耗时、尝试/重试计数、审批元数据、
结果和错误；完整最终回复可以保留，其中允许正文、代码和修订稿。新输入
`task/acceptanceCriteria/constraints/artifactContent/context` 正文只在当前会话使用，长期仅存
`inputMetadata`；完整 prompt、transcript、原始工具参数和输出不长期留存，旧记录原样保留。

密码、API key、token、Cookie、session 值、私钥、认证头和设备登录值不得主动写入 prompt、日志或
报告。输入任务、模型结果、错误和审批目标在持久化或公开前脱敏。bridge 长期 MCP token 不进入 peer
环境；内部 hook 只收到本 job 临时 token。
脱敏以真实凭据值和明确认证上下文为依据，不因普通 `session/token` 字段名遮盖技术文字、路径、公式或
代码。普通字段与最终回复不静默截断；总请求及输出上限仍有效，超限必须明确报错。

新 v3 记录使用独立的 schema 4 存储，协议和工具前缀仍为 v3。旧 schema 3 只读保留，读取、展示或
显式迁移只在新存储建立记录，不原地更新旧记录、恢复旧活动任务或自动批准旧动作。切换前仍等待活动
任务结束；回滚不能让旧程序写入新 schema 4 记录。

## v2 inline 兼容

明确指定旧协议或兼容旧调用方时，可调用：

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
不能自动回退 v2，不得扩大旧协议的执行能力。

## 用户门与失败

互审结果只是用户决策材料。file 报告 peer 是否修改、作者是否修改、终审是否运行、主文件 SHA-256
是否仍有效；message 报告单轮回复与主模型解读，不虚构文件有效性。两者均保留真实意见、未决问题或
分歧；正式计划执行复用已有授权，未授权时再交给用户确认。

路径无效、MCP 不可达、精确模型缺失、空回复、真实运行失败、会话清理失败或终审写入
都保留原 job/series 和清理后的错误。普通格式差异不是失败；旧审批拒绝/过期只取消对应动作，不自行
变成 job 终态。pending 不是失败也不是最终答复。不得伪造 completion、扫描
其他 job、降低模型、创建重复 job 或替用户决定目标、范围及重要取舍。
