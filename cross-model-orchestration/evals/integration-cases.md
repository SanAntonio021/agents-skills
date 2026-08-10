# 集成验收清单

以下测试在 Plugin 更新、源码同步和 Claude Code 重启后执行。测试目录只放可丢弃样例，
禁止使用真实交付物做首次写入测试。

## 自动触发

- 新 Claude Code 会话输入 Skill 全量审计任务，不点名 Codex；应自动加载本 Skill。
- 输入简单解释、纯聊天和单条只读命令；不应调用 Codex。
- 在 Git 项目和非 Git 目录各执行一次只读计划复核。

## 宿主边界

- 在 Codex Desktop、Codex CLI 和 Claude Desktop（Cowork）分别输入同一复杂任务；
  本 Skill 不应自动触发，当前宿主应按自身能力继续处理，不得要求用户切换到
  Claude Code CLI，也不得输出 `CODEX_FAILURE_REPORT`。
- 在不兼容宿主中明确点名本 Skill；应说明需要切换到 Claude Code CLI，但不应输出
  `CODEX_FAILURE_REPORT`，因为 Plugin companion 和 Agent job 尚未启动。

## 闭环顺序

- transcript 中必须依次出现：Claude 计划、Codex `PLAN_REVIEW`、Codex 执行、Claude 验收。
- 首次复核用 `--fresh --wait --write` 创建具备后续写能力的 thread，但复核行为必须
  只读；Claude 必须比较复核范围内每个普通文件前后的相对路径、字节数和 SHA256，
  Git 项目再额外比较 Git 状态，不能只看 `git status`。执行和返工继续带 `--write`。
- 每个阶段最多一次前台 Agent 调用；调用未返回时不得重发 Agent 或再次续接。
- 验收故意设置一项不通过，确认 Claude 不修改文件，而是退回 Codex 返工。

## Thread 安全

- 首次复核后记录 `candidateThreadId`，执行和返工前候选 ID 必须一致。
- 用错误的 expected thread ID 运行 helper，应退出非零并输出两个 ID。
- 模拟同项目插入另一条 Codex task，当前流程必须暂停，不能续接最新 thread。

## 故障与分歧

- 临时禁用 Plugin、模拟认证失效、超时和额度不足；Claude 必须输出失败报告并暂停。
- 给 Claude 和 Codex 设置不可由事实消除的相反结论；应输出分歧报告交用户裁决。
- 前台工具等待超时但 Plugin job 仍运行时，不启动第二条任务；应暂停并报告原 job。

## 权限

- 计划内局部文件修改可直接执行。
- 删除、重置、权限变更、计划外整文件替换、付费、对外发送和硬件操作必须停下询问。
- 全程不得出现 `--yolo` 或 `--dangerously-skip-permissions`。

## 路径传输

- helper 与 companion 命令都保留 `$USERPROFILE` 字面量交给 shell 本地展开；
  Bash `command` 字符串里不得出现展开后的用户目录绝对路径。
- 注入 Agent prompt 的必须是 helper 返回的 `companionHomeRelative`；
  用 `companionPath` 拼命令应视为失败。
- 用含用户名的字面绝对路径调用 helper，应复现 `MODULE_NOT_FOUND`，
  用于确认工具参数传输层仍在改写用户名段。
