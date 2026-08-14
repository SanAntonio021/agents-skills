# 工作流契约

## 基本约束

本契约用于两条方向：`Codex -> Claude Opus 5` 和 `Claude -> Codex`。每一轮的作者、审查者、
产物、哈希和 job ID 都必须可追溯；审查者只读，作者负责修改。

- 每个 `artifactId` 最多三轮，`round` 只能是 `1`、`2` 或 `3`，`maxRounds` 固定为 `3`。
- 已有活动 job 时只能查询该 job，不能重发、另开 job、使用 `--resume`/`--resume-last` 猜测上下文。
- 审查包和审查结果不是用户执行授权。正式计划通过互审后仍须用户明确确认。
- 审查者写入、输出格式错误、模型不匹配、通道异常、超时或取消立即失败关闭，不算“需修改”。
- 执行和返工可以由执行作者写入，但不是审查；重要执行交付物仍须在交付前走只读互审。

## 审查包

每轮使用如下 JSON 对象或同等字段的单行提示词。对 Opus 5，`artifactContent` 必须包含足以完成
审查的全文、摘录和证据，因为 bridge 没有工具；对 Codex，`artifactPath` 只能定位到已授权的
只读范围。

```json
{
  "artifactId": "stable-logical-artifact-id",
  "artifactType": "plan | deliverable",
  "author": "Codex | Claude",
  "reviewer": "Claude Opus 5 | Codex",
  "round": 1,
  "maxRounds": 3,
  "artifactName": "logical name or relative path",
  "artifactBytes": 0,
  "artifactSha256": "64 lower-case hex characters",
  "artifactContent": "full reviewable content or explicit permitted evidence",
  "artifactPath": "optional, only for authorized Codex read access",
  "priorRounds": [],
  "priorFindings": [],
  "openItems": [],
  "acceptanceCriteria": ["objective criterion"],
  "constraints": ["scope or safety boundary"],
  "reviewerAccess": "read_only"
}
```

`priorRounds.length` 必须等于 `round - 1`，其轮次连续且不重复。每条已知 finding 有来源轮次和
稳定编号；作者修订后仍未解决的项留在 `openItems`。`artifactSha256` 随作者修改更新，但
`artifactId` 不变。

Claude -> Codex 交给控制脚本时，提示词中只能有一个外层 ` ```json ... ``` ` 审查包；
`artifactContent` 作为 JSON 字符串序列化，允许它包含 Markdown 代码块。不要在审查包后追加第二个
JSON fence，以免把传输的内容与审查状态混淆。

## Claude 计划模式入口与状态

`ExitPlanMode` 的拒绝理由只是用户向 Claude 表达“先互审计划”的一种方式，不是 hook、环境变量或
可信的计划路径来源。理由明确要求 Codex 审查时，Claude 直接创建上面的 `artifactType: "plan"`
审查包；所有其他符合触发条件的正式计划也同样创建该包。没有可靠文件路径时不猜测，使用稳定
`artifactName` 和完整 `artifactContent`；有计划文件时把它写入 `artifactPath`。

Claude -> Codex 的每个活动审查必须由 `orchestration-control.mjs` 记录到
`CLAUDE_PLUGIN_DATA/orchestration/claims.json`。记录至少保留 `phase: "review"`、`artifactId`、
`artifactType`、`artifactPath`（如有）、`artifactSha256`、`round`、`jobId` 和 `targetRoots`。
脚本按目标根拒绝重叠活动 job；不得手改 state 或为绕过冲突另开 job。历史轮次仍由下一轮审查包的
`priorRounds` 与 `priorFindings` 传递，避免隐藏状态替代证据。

## 只读快照

在审查 job 启动前，为每个普通文件记录相对路径、字节数和 SHA-256，排除 `.git` 内部元数据；
Git 项目还记录 Git 状态。job 终态后再比较整个集合和全部哈希。

出现任何变化时：不接受审查意见、不由作者回滚后继续、不把它写成普通 finding；直接输出
`PEER_REVIEW_FAILURE_REPORT`，其中 `decisiveError` 为 `reviewer_write_detected`。

## Codex -> Claude Opus 5 调用

调用方只使用 bridge 现有 MCP 工具名：`submit_claude`、`await_claude`、`claude_result`、
`bridge_status`、`cancel_bridge_job`。提交仅传入审查包、`route: "headless"` 和必要的会话标识；
不得传入、拼接或覆盖模型、工具、权限参数。

bridge 的固定参数和验收条件如下：

```text
--model claude-opus-5 --tools "" --permission-mode default
system/init.model == claude-opus-5
system/init.tools.length == 0
public result.review_model == claude-opus-5
```

`await_claude` 的一次等待最多 45 秒。未完成时用 `claude_result` 查询同一 job；不得创建替代
请求。只在 `state: succeeded`、`review_model` 精确匹配且正文契约合法时接受。模型不存在、不同、
重复参数、回退参数、timeout、取消、bridge 不可用或 `model_mismatch` 都输出失败报告并暂停；
不存在 fallback model。

### Opus 5 审查提示词

```text
角色：Claude Opus 5，只读审查者。不得修改、执行或请求工具。
审查包：<完整 JSON 或完整结构化内容>
任务：检查完整性、可执行性、证据边界、遗漏风险、范围和验收标准。
输出：artifactType 为 plan 时严格按 PLAN_REVIEW；为 deliverable 时严格按 DELIVERABLE_REVIEW。
```

## Claude -> Codex 调用

此方向只允许 Claude Code CLI 的已启用 `codex@openai-codex` companion。每轮必须由控制脚本以
`--review` 启动；这个模式要求完整 JSON 审查包、拒绝 `--write`、持久化活动状态，并拒绝第 4 轮：

```bash
node "$USERPROFILE/.claude/skills/cross-model-orchestration/scripts/orchestration-control.mjs" launch --review --cwd "<共同祖先目录>" --target-roots "<逗号分隔的受控目标根>" "<含完整 ```json 审查包的单行只读提示词>"
```

`launch` 返回 `jobId` 与 `ownerToken` 后，用相同脚本的 `verify-request --review` 和作者发送前记录的
完整 prompt 字节数、SHA-256 校验实际 job 收到的内容与信封；省略任一预期值即取消该 job，未验证不得
接受任务。随后只轮询 `status <jobId>`，用
`result <jobId>` 的 `rendered` 读取正文，不用 `.log` 兜底。终态后先调用 `candidate` 绑定 job、目标根
和声明，再完成前后快照对比，最后以同一 job ID 调用 `release --owner-token`。控制器会再次确认该 job
为终态才释放声明。启动 cwd 必须是全部目标路径的共同祖先；
`$USERPROFILE` 必须保留为 shell 本地展开的字面量，不替换成用户名绝对路径。Claude Desktop/Cowork、
插件不可用、控制脚本/权限失败、认证失败、超时、锁冲突或无效正文都失败关闭；不得退回到直接调用
companion 的方式。

### Codex 审查提示词

```text
角色：Codex，只读审查者。不得修改文件、运行写操作或执行计划。
审查包：<完整单行审查包>
只可读取包中列出的材料；比较计划/交付物与验收标准、证据边界和范围。
artifactType 为 plan 时严格按 PLAN_REVIEW；为 deliverable 时严格按 DELIVERABLE_REVIEW。
```

## PLAN_REVIEW

保留本格式和五段结构以兼容既有调用：

```text
PLAN_REVIEW
结论：通过 | 需修改 | 实质分歧
已确认事项：
- ...
问题与理由：
- <问题；理由；证据或待核事实>
必须修改：
- ...
剩余风险：
- ...
```

`通过` 仍写剩余风险；没有问题时写“无”。`需修改` 必须有可执行的修改项。方向、价值判断或证据
无法消除的冲突使用 `实质分歧`。

## DELIVERABLE_REVIEW

交付物使用与 `PLAN_REVIEW` 同构的格式：

```text
DELIVERABLE_REVIEW
结论：通过 | 需修改 | 实质分歧
已确认事项：
- ...
问题与理由：
- <问题；理由；文件或证据>
必须修改：
- <作者可执行的修订>
剩余风险：
- ...
```

审查者不得把修订直接写进交付物；`需修改` 后作者更新交付物、证据、字节数和 SHA-256，再进入
下一轮。

## 作者修订与第三轮止损

作者只根据当前审查包中的 findings 修订，不扩大到未授权范围。第 1 或第 2 轮的 `需修改` 可进入
下一轮；第 3 轮仍为 `需修改` 时不再发起审查，直接输出分歧报告。对同一异议没有新证据时，也
不空转，按实质分歧处理。

正式计划通过后，展示最终计划、轮次结论、已解决项和剩余风险，等待用户明确确认执行。执行 prompt
才可使用 `--write`，并必须明确允许修改范围、验收标准和高风险停止条件。

对已确认计划，执行作者最多进行三次“返工 -> 独立验收”循环。每次验收不通过都必须给出具体文件、
证据和通过判据；第三次仍不通过时停止，报告未满足的验收标准、已完成内容和未完成范围，等待用户
决定。只有审查通道本身失败时才用 `PEER_REVIEW_FAILURE_REPORT`，不能把普通验收失败伪装成模型故障。

## DISAGREEMENT_REPORT

只整理双方已有判断和证据，不推荐、代选或发明折中方案。输出后暂停等待用户裁决。

```text
# 需要用户裁决

- 产物：<artifactId / 名称>
- 阶段：计划复核 | 交付物复核
- 轮次：<1 | 2 | 3>

## 已达成共识
- ...

## 作者的判断
- 角色和模型：<实际作者>
- 结论：...
- 理由：...
- 证据：...

## 审查者的判断
- 角色和模型：<实际审查者>
- 结论：...
- 理由：...
- 证据：...

## 实质分歧
- ...

## 需要决定
- <一个明确问题及各选项影响>
```

## PEER_REVIEW_FAILURE_REPORT

本报告同时覆盖两条方向。报告后停止，不重试、不换模型、不换审查者、不由另一方代写或接管。

```text
# 互审已暂停

- 审查方向：Codex -> Claude Opus 5 | Claude -> Codex
- 产物与阶段：<artifactId；计划复核 | 交付物复核>
- 轮次：<1 | 2 | 3>
- 请求审查者：<模型或通道>
- 实际模型：<claude-opus-5 | 其他 | 缺失 | 不适用>
- job ID：<已知 ID；未知则写未知>
- decisiveError：<最短决定性错误>
- 已完成内容：<文件、结果或无>
- 未完成内容：<范围>
- 恢复条件：<明确的用户动作或环境条件>
```

Codex -> Opus 5 的实际模型不是 `claude-opus-5` 时，`decisiveError` 必须为 `model_mismatch`；
审查文件发生变化时必须为 `reviewer_write_detected`。Claude -> Codex 的控制器拒绝审查包、`--write`、
重叠 job 或状态读取时，分别记录 `malformed_review_envelope`、`reviewer_write_requested`、
`orchestration_conflict` 或相应状态错误。缺模型字段和超时同样失败，不得以旧结果、普通 Claude、其他
Opus 别名或本地推测替代。

## CODEX_FAILURE_REPORT（兼容）

保留给已经启动 Claude Code CLI companion 后的执行阶段失败；新的审查失败优先使用上面的
`PEER_REVIEW_FAILURE_REPORT`。

```text
# Codex 协作已暂停

- 失败阶段：计划复核 | 执行 | 返工
- 关键错误：<最短决定性错误>
- job ID：<已知 ID；未知则写未知>
- expectedThreadId：<已记录 ID；未记录则写未知>
- candidateThreadId：<当前候选 ID；查不到则写未知>
- 已完成内容：<文件、结果或无>
- 未完成内容：<范围>
- 恢复条件：<登录、额度、重试或可靠续接条件>
```
