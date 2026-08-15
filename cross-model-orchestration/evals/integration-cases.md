# 集成验收清单

以下验收在源码同步、相关客户端重启后进行。首次真实写入只使用可丢弃的隔离材料；真实 Opus 5
调用由 bridge 的 `test:live:opus5` 单独完成，不使用用户交付物。

## 自动触发与宿主

- 在 Claude Code CLI、Codex Desktop 和 Codex CLI 中分别形成一份准备提交给用户确认的正式计划；
  都应自动加载本 Skill 并调用同一个 `claude-codex-bridge` MCP。
- 在已注册该 MCP 的 Claude Code CLI 中，Claude 方向请求为 `target=codex`；在 Codex Desktop/CLI
  中，请求为 `target=claude`。两端都不调用 `codex@openai-codex`、`codex exec` 或 `claude -p`。
- 在未注册 MCP 的宿主准备提交正式计划，流程应进入 `PEER_REVIEW_FAILURE_REPORT`，说明没有已验证通道。
- 输入复杂调研、代码/文档修改、命令、测试、提交、已确认计划的执行或最终汇报，但不形成待确认的
  正式计划；不应创建 bridge job。
- 使用内部 Todo、`update_plan`、执行清单或状态更新管理进度；不应把它们当作正式计划。
- 用户明确要求 Opus/Codex 审查计划或交付物时，应按显式请求进入本 Skill。

## Claude -> Codex review_repair

- 默认质量 job 的公共状态和受保护详情应记录 `requested_model=gpt-5.6-sol` 与
  `requested_reasoning_effort=max`；其他 job 必须与其已解析 profile/显式选择一致。任一缺失或不匹配
  都不得验收，且不能继承用户全局模型或推理档位。
- Claude 形成正式计划时自动用 `review_repair_peer(target=codex)`；交付物只有在用户明确要求或明确
  启用专用循环时才显式调用。两类请求都提供完整正文、名称，正式文件同时提供路径，并在调用前从
  完整 `artifactContent` 重新计算 UTF-8 字节数和 SHA-256；目标根、最小非空 allowlist、非空验收标准
  和显式 `testCommands` 数组齐全。工具固定隔离写权限和三轮上限。
- `await_peer` 超时后只用同一 job 的 `peer_result`；不得重发、猜测线程或调用旧插件。
- Codex 只能在 bridge 固定副本中检查、修复和测试。普通新增/修改自动同步；删除、重命名、权限或
  类型变化进入 `needs_attention`，列出 `pending_high_risk`。
- 固定副本应包含目标根的完整可读上下文并排除 `.git`；写入仍只能发生在作者给出的最小 allowlist。
- 用户批准完整 ID 集合后调用 `approve_peer_sync`；确认新的 `sync_request_id`、基线哈希、结果哈希和
  主项目文件集合。批准动作不重新调用 Codex。
- `awaiting_user` 期间尝试提交重叠目标根的新任务，应以 `retained_workspace_conflict` 拒绝，不能绕锁。
- Codex `ask` 应在专用空只读目录中运行，不能从 cwd 读取作者项目、daemon token 或其他 job 材料。
- Windows 子进程应同时记录 `environment_context_enabled=true` 与
  `windows_sandbox_mode=unelevated`，并证明实际命令 cwd 是固定副本；不得修改用户全局 Codex 配置。
- 模拟原生补丁失败后用 shell 写入 allowlist 文件；同步前仍须通过全量 manifest。对同一精确测试命令
  模拟“失败后通过”和“通过后失败”，前者终态通过，后者终态拒绝，受保护事件均保留全部尝试。
- 运行一次 `npm.cmd run test:live:codex`，确认 `gpt-5.6-sol` 请求、`max` 推理强度、真实写入及同步哈希、取消、同线程恢复、CLI 版本、
  `workspace-write`、`approvalPolicy=never` 和 Windows sandbox 证据同时成立。

## Codex -> Claude

- 在 Codex Desktop 和 Codex CLI 用 `review_repair_peer(target=claude)` 完成一次
  自动正式计划审查，再用用户明确请求完成一次显式交付物审查；MCP 工具名优先使用
  `review_repair_peer`/`await_peer`/`peer_result`。
- 默认质量请求为 `claude-opus-5` / `max`。只接受终态 `succeeded`、正文契约合法、公共
  `review_model` 与本 job 所选模型相同，以及 `system/init.model` 精确匹配的结果。
- 需要 Bash 验证时只允许作者逐条给出的精确 `testCommands`；测试命令含重定向、管道、通配符或
  命令串联必须在提交前拒绝。任何 `permission_denials` 都使 job 失败，即使正文写“通过”。
- 分别提交 `testCommands=[]` 和非空数组：前者 init 工具必须严格为 `Read,Edit,Write` 且没有 Bash
  allowlist，后者才可增加 `Bash`，并只允许给定精确命令。额外 Bash 调用以 `isolation_breach` 失败。
- `ask` 模式验证解析出的 `--model`、`--effort`、`--tools ""`、`--permission-mode default` 和空 init 工具；
  `review_repair` 模式验证受控工具、`acceptEdits`、固定 cwd/`--add-dir` 和副本哈希。
- 默认发布验收不运行 `npm.cmd run test:live:opus5`，只执行确定性测试。只有用户以后单独明确授权
  真实 Opus 复验时，才可创建一次验收 job；请求模型、init 回执模型、工具隔离、结果格式和临时
  运行时清理任一不符合即验收失败，不选择 fallback。

## 路由与恢复

- 不传路由字段时分别得到 Opus 5/max 与 Sol/max；公共状态同时带 `task_profile=quality`、
  `routing_source=default` 和版本化 rule ID。
- `taskProfile=writing` 与 `creative_writing` 仍路由 Opus 5/max；不得按旧印象自动改为 Opus 4.6。
- `balanced` 分别路由 Sonnet 5/high 与 Terra/max；`high_volume` 分别路由 Sonnet 5/medium 与 Luna/max。
- 显式 `model=claude-opus-4-6, reasoningEffort=max` 可通过；Opus 4.6/xhigh、Claude 模型发往 Codex、
  Luna/ultra 等非法组合必须在创建 job 前拒绝。
- 同一记录线程尝试换模型、强度或 profile 必须失败；`resume_peer` 缺少完整路由证据或带不同覆盖值也
  必须失败。新路由只能使用新的 `bridge_thread_id`。
- 任一 profile 或显式模型不可用时停止，不退回质量默认、其他模型或较低强度。

## 计划、三轮与用户门

- 默认正式计划保留 `PLAN_REVIEW` 五个固定组成部分（结论、已确认事项、问题与理由、必须修改、
  剩余风险）；显式交付物审查使用同构 `DELIVERABLE_REVIEW`。缺少任一部分都应在同步前以
  `peer_contract_error` 失败关闭。
- 第 1/2 轮 `需修改`由作者依据意见更新产物、字节数、SHA-256 和 prior findings；第 3 轮仍未通过时
  输出 `DISAGREEMENT_REPORT`，不发第 4 轮。
- 在完整正文缺失、字节数错误或 SHA-256 不匹配时验证 `review_repair_peer` 不创建 job；旧
  `submit_peer(operation=review_repair)` 返回列出全部缺失项的 `missing_fields`，job 目录保持不变。
- 计划互审通过后，transcript 必须停在用户确认门；未获明确确认不得执行写入。
- 模拟模型不可用、超时、取消、格式错误、sandbox 拒绝、实际模型不是本 job 所选模型和主项目基线漂移；均输出
  `PEER_REVIEW_FAILURE_REPORT`，不得把失败改写成普通返工。
- 模拟 `review_repair` 返回 `DELIVERABLE_REVIEW - Blocked`、缺少结论，或失败测试却写成“通过”；
  bridge 应以 `peer_contract_error` 失败关闭，不同步审查副本，并保留失败报告证据。

## 作者验收与返工

- 原作者检查 bridge 同步后的主项目、测试、提交和验收标准；审查者对自己的修复不做最终签字。
- 已确认计划的普通执行、验收、返工和最终汇报不自动创建新的 peer job；显式跨模型执行工作流除外。
- 对同一确认计划模拟三次独立验收失败；第三次后不得启动第四次返工，报告证据并等待用户决定。
- 任何副本越界写入、符号链接、路径穿越、`.git` 或 allowlist 扩大都停止，不回滚后继续接受结果。
- 公共 `isolation_violation` 只含事件序号、工具、原因码和最多 256 字符的脱敏预览；工作区绝对路径
  显示为 `<workspace>`，控制字符转义，原始事件只存在于受保护详情。

## 运行时发布

- Claude 与 Codex 都通过 `http://127.0.0.1:43123/mcp` 连接同一 daemon，Header 从
  `CLAUDE_CODEX_BRIDGE_TOKEN` 解析；并发连接下不得出现 stdio wrapper 或第二个 daemon。
- endpoint、health、`bridge_status` 和 job 证据的 `version=0.4.0`、`build_id`、协议版本必须一致。
- root 与 `skills` 仓库分别只暂存本次允许路径并推送，保留无关 dirty/untracked 改动。
- Skill 推送后，用 `Invoke-CcSwitchSkillSync.ps1` 传入精确 Skill 名和 40 位远端 SHA 定向同步；不点
  “全部更新”，不直接改 `.cc-switch`、`.claude`、`.codex` 或数据库。
- 核对源码、CC Switch、Claude、Codex 四层文件集合和 SHA-256；任一层不一致只报告“源码已推送，运行时未生效”。
