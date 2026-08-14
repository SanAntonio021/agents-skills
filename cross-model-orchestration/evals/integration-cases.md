# 集成验收清单

以下验收在源码同步、相关客户端重启后进行。首次真实写入只使用可丢弃的隔离材料；真实 Opus 5
调用由 bridge 的 `test:live:opus5` 单独完成，不使用用户交付物。

## 自动触发与宿主

- 在 Claude Code CLI、Codex Desktop 和 Codex CLI 中分别输入需要本地材料、多步骤判断和正式计划的
  任务；都应自动加载本 Skill 并调用同一个 `claude-codex-bridge` MCP。
- 在已注册该 MCP 的 Claude Code CLI 中，Claude 方向请求为 `target=codex`；在 Codex Desktop/CLI
  中，请求为 `target=claude`。两端都不调用 `codex@openai-codex`、`codex exec` 或 `claude -p`。
- 在未注册 MCP 的宿主输入同类任务，流程应进入 `PEER_REVIEW_FAILURE_REPORT`，说明没有已验证通道。
- 输入纯聊天、简单解释和单条明确只读命令；不应创建 bridge job。

## Claude -> Codex review_repair

- Claude 形成正式计划或重要交付物后，用 `submit_peer(target=codex, operation=review_repair)`，
  提供完整审查包、`reviewerAccess=isolated_write`、目标根、最小 allowlist 和精确 `testCommands`。
- `await_peer` 超时后只用同一 job 的 `peer_result`；不得重发、猜测线程或调用旧插件。
- Codex 只能在 bridge 固定副本中检查、修复和测试。普通新增/修改自动同步；删除、重命名、权限或
  类型变化进入 `needs_attention`，列出 `pending_high_risk`。
- 固定副本应包含目标根的完整可读上下文并排除 `.git`；写入仍只能发生在作者给出的最小 allowlist。
- 用户批准完整 ID 集合后调用 `approve_peer_sync`；确认新的 `sync_request_id`、基线哈希、结果哈希和
  主项目文件集合。批准动作不重新调用 Codex。
- `awaiting_user` 期间尝试提交重叠目标根的新任务，应以 `retained_workspace_conflict` 拒绝，不能绕锁。
- Codex `ask` 应在专用空只读目录中运行，不能从 cwd 读取作者项目、daemon token 或其他 job 材料。

## Codex -> Opus 5

- 在 Codex Desktop 和 Codex CLI 用 `submit_peer(target=claude, operation=review_repair)`完成一次
  隔离计划审查和一次重要交付物审查；MCP 工具名优先使用 `submit_peer`/`await_peer`/`peer_result`。
- Opus 5 请求固定为 `claude-opus-5`。只接受终态 `succeeded`、正文契约合法、公共
  `review_model === "claude-opus-5"`，以及 `system/init.model` 精确匹配的结果。
- 需要 Bash 验证时只允许作者逐条给出的精确 `testCommands`；测试命令含重定向、管道、通配符或
  命令串联必须在提交前拒绝。任何 `permission_denials` 都使 job 失败，即使正文写“通过”。
- `ask` 模式验证 `--model claude-opus-5`、`--tools ""`、`--permission-mode default` 和空 init 工具；
  `review_repair` 模式验证受控工具、`acceptEdits`、固定 cwd/`--add-dir` 和副本哈希。
- 运行一次 `npm.cmd run test:live:opus5`。请求模型、init 回执模型、工具隔离、结果格式和临时运行时
  清理任一不符合即验收失败；不选择 fallback。

## 计划、三轮与用户门

- 保留 `PLAN_REVIEW` 五个固定组成部分（结论、已确认事项、问题与理由、必须修改、剩余风险），并新增
  同构 `DELIVERABLE_REVIEW`；缺少任一部分都应在同步前以 `peer_contract_error` 失败关闭。
- 第 1/2 轮 `需修改`由作者依据意见更新产物、字节数、SHA-256 和 prior findings；第 3 轮仍未通过时
  输出 `DISAGREEMENT_REPORT`，不发第 4 轮。
- 计划互审通过后，transcript 必须停在用户确认门；未获明确确认不得执行写入。
- 模拟模型不可用、超时、取消、格式错误、sandbox 拒绝、实际模型非 Opus 5 和主项目基线漂移；均输出
  `PEER_REVIEW_FAILURE_REPORT`，不得把失败改写成普通返工。
- 模拟 `review_repair` 返回 `DELIVERABLE_REVIEW - Blocked`、缺少结论，或失败测试却写成“通过”；
  bridge 应以 `peer_contract_error` 失败关闭，不同步审查副本，并保留失败报告证据。

## 作者验收与返工

- 原作者检查 bridge 同步后的主项目、测试、提交和验收标准；审查者对自己的修复不做最终签字。
- 对同一确认计划模拟三次独立验收失败；第三次后不得启动第四次返工，报告证据并等待用户决定。
- 任何副本越界写入、符号链接、路径穿越、`.git` 或 allowlist 扩大都停止，不回滚后继续接受结果。

## 运行时发布

- root 与 `skills` 仓库分别只暂存本次允许路径并推送，保留无关 dirty/untracked 改动。
- Skill 推送后，用 `Invoke-CcSwitchSkillSync.ps1` 传入精确 Skill 名和 40 位远端 SHA 定向同步；不点
  “全部更新”，不直接改 `.cc-switch`、`.claude`、`.codex` 或数据库。
- 核对源码、CC Switch、Claude、Codex 四层文件集合和 SHA-256；任一层不一致只报告“源码已推送，运行时未生效”。
