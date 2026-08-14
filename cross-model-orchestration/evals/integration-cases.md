# 集成验收清单

以下验收在源码同步、相关客户端重启后进行。首次真实写入只使用可丢弃的隔离材料；最小真实
Opus 5 调用由 bridge 的 `test:live:opus5` 单独完成，不使用用户交付物。

## 自动触发与宿主

- 在 Claude Code CLI、Codex Desktop 和 Codex CLI 中分别输入一项需要本地材料、多步骤判断和
  正式计划的任务；本 Skill 都应自动加载。
- 在 Claude Desktop/Cowork 输入同类任务；流程应进入并输出 `PEER_REVIEW_FAILURE_REPORT`，说明
  没有已验证审查通道，不得静默绕过或要求用户改运行时副本。
- 输入纯聊天、简单解释和单条明确只读命令；不应创建 Codex companion 或 bridge job。

## Claude -> Codex 只读计划审查

- 在 Claude Code 的 `ExitPlanMode` 对话框拒绝执行并写“让 Codex 审查当前计划”；该理由应作为正式
  计划的普通互审请求，而不是依赖不可订阅的 hook、环境变量或隐式参数。计划路径必须来自作者明确
  写入审查包的 `artifactPath`；缺路径时只用稳定名称和完整内容，不能猜测。
- 审查必须经 `orchestration-control.mjs launch --review`。确认它拒绝 `--write`、缺失 JSON 包、
  `reviewerAccess != read_only`、第 4 轮和重叠目标根；`claims.json` 的活动记录包含 `phase`、
  `artifactId`、`artifactSha256`、`round`、`jobId` 和目标根。job 终态后必须显式 `release`，不得
  手改声明文件或改为直接调用 companion。
- 在隔离 Git 项目和非 Git 目录各完成一次 Claude 正式计划。Codex 审查命令必须为
  `--background --fresh`，**不得**带 `--write`、`--wait`、`--resume` 或 `--resume-last`。
- 审查前后比较每个普通文件的相对路径、字节数、SHA-256；Git 项目额外比较 Git 状态。任一差异
  使该轮失败，不能接受其“通过”正文。
- 验证输出保留 `PLAN_REVIEW` 的结论和五段结构。第 1/2 轮 `需修改` 时由 Claude 修订，第 3 轮
  仍未通过时停止并输出 `DISAGREEMENT_REPORT`。
- 计划审查通过后，确认 transcript 停在用户确认门；未获明确确认不得启动 `--write` 执行任务。

## Codex -> Opus 5 只读审查

- 在 Codex Desktop 和 Codex CLI 使用 `submit_claude`、`await_claude`、`claude_result` 完成一次
  隔离计划审查和一次重要交付物审查。MCP 工具名称不得变化。
- 审查包包含 `artifactId`、`artifactType`、作者/审查者、`round`、`maxRounds: 3`、字节数、
  SHA-256、可审查内容、前轮 findings、未解决项和验收标准。Opus 包必须有足够全文，不能让其
  “自行读文件”。
- 只接受终态 `succeeded`，正文符合 `PLAN_REVIEW` 或 `DELIVERABLE_REVIEW`，并且
  `review_model === "claude-opus-5"` 的结果。缺字段、`claude-sonnet-5` 或任意其他值都必须
  产生 `PEER_REVIEW_FAILURE_REPORT`，不能 fallback。
- 验证 bridge 启动参数同时存在 `--model claude-opus-5`、`--tools ""`、
  `--permission-mode default`，且重复/覆盖/`--fallback-model` 被单测拒绝。
- 在隔离材料运行一次 `npm.cmd run test:live:opus5`。PASS 仅限请求固定模型、实际回执模型都为
  `claude-opus-5`，空工具隔离、只读快照和临时运行时清理均通过；任何不匹配即验收失败。

## 作者修订、交付和验收

- 审查者不得修改文件。出现写入时，检查失败报告的 `decisiveError` 是
  `reviewer_write_detected`；不允许作者先回滚再接受审查。
- Codex 执行者在 Claude Code CLI 的已确认计划下可使用 `--write`；这只代表作者执行。每个重要
  执行产物在返回前由 Codex 的已注册 bridge MCP 取得 Opus 5 `DELIVERABLE_REVIEW`。
- 交付后由独立验收者检查实际文件、命令、测试、Git 提交、远端祖先关系和验收标准。空
  `git diff` 不能替代 `git show` 和本轮验证。
- 对任一 `artifactId` 确认同一时刻只有一个活动 review job；未终态时只能轮询，不得重发或另开。
- 对同一已确认计划，故意让独立验收连续三次失败；第三次后不得启动第 4 次返工，报告未满足的
  验收标准、证据、已完成内容和未完成范围，等待用户决定。这个止损不把普通验收失败写成通道故障。

## 故障与分歧

- 临时禁用 bridge、Codex plugin、认证，或模拟超时、取消、格式错误、sandbox 拒绝、模型缺失和
  `model_mismatch`；都必须输出 `PEER_REVIEW_FAILURE_REPORT` 并暂停。
- 给作者和审查者设置不能由事实消除的相反结论；验证 `DISAGREEMENT_REPORT` 使用实际角色和模型，
  不替用户选择方案。
- 验证第 3 轮仍为 `需修改` 时不发起第 4 轮；审查失败不被伪装成普通返工，也不由另一模型接管。

## 同步与运行时

- root 与 `skills` 仓库分别只暂存本次允许路径、提交并推送，保留无关工作区改动。
- Skill 推送后，用 `Invoke-CcSwitchSkillSync.ps1` 的精确 Skill 名和 40 位远端 SHA 定向同步；
  不点“全部更新”，不直接改 `.cc-switch`、`.claude`、`.codex` 或数据库。
- 只有源码、CC Switch、Claude、Codex 四层的文件集合和 SHA-256 一致，且 Codex 已看到 bridge MCP，
  才报告运行时生效；否则只能报告“源码已推送，运行时未生效”。
