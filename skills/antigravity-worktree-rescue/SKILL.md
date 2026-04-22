---
name: antigravity-worktree-rescue
description: "排查 Antigravity 在 Git worktree 目录里的兼容问题，并给出低风险恢复路径。Use when 用户提到 Antigravity 发不出消息、`Cannot call write after a stream was destroyed`、`core.repositoryformatversion does not support extension: worktreeconfig`，或主仓库可用但 `.codex/worktrees/...` 里失效；prefer 先回主仓库验证，再决定是否清理 worktree 或改配置。"
---

# Antigravity Worktree 救援

## 作用

这份 skill 处理一类很具体的兼容问题：

- Antigravity 在普通仓库目录能工作
- 但在 `.codex/worktrees/...` 这类 Git worktree 目录里，agent 发不出消息、规则加载失败，或日志提示 `worktreeconfig`

目标不是上来就改 Git 配置，而是先把“症状”和“根因”分开，再给出最低风险的恢复路径。

## 先判断是否命中

下面这些信号一起出现时，优先认为命中了这类问题：

- 用户提到 `Cannot call write after a stream was destroyed`
- 日志里出现 `core.repositoryformatversion does not support extension: worktreeconfig`
- 日志里出现 `Failed to resolve workspace infos`、`workspace infos is nil`、`Error fetching rules`
- 当前目录明显位于 `.codex/worktrees/`

## 流程

1. 先查日志，不先改 Git。
   优先看 `Antigravity.log`，再看同批次的 `agent-window-console.log`；需要时再补看 `Codex.log`。
2. 把症状和根因分开。
   `Stopping server failed`、`Cannot call write after a stream was destroyed` 更像表层症状；
   `worktreeconfig`、`workspace infos is nil` 这类信息更接近根因。
3. 确认当前目录是不是 Git worktree。
   先读当前目录下的 `.git`，再看它是否指向主仓库 `.git/worktrees/...`；必要时检查主仓库 `.git/config` 是否启用了 `extensions.worktreeConfig=true`。
4. 默认先走最低风险恢复。
   让用户彻底退出 Antigravity，改为打开主仓库目录，而不是 `.codex/worktrees/...`，再验证 agent 是否恢复。
5. 如果用户不熟悉 worktree，就用一句白话解释。
   它只是同一仓库的额外工作目录，不是坏仓库，也不是独立 clone；这次是兼容问题，不是用户操作错误。
6. 只有用户同意清理时，才做 worktree 清理。
   先 `git worktree list --porcelain`，再逐个看 `git status --short`；有未提交修改先备份，再移除；确认目标目录安全后才允许 `git worktree remove --force "<path>"`。
7. 只有当用户明确要求“必须让 Antigravity 在 worktree 里也能用”时，才进入配置改造。
   先备份主仓库 `.git/config`，再讨论是否关闭 `extensions.worktreeConfig`，以及怎样把仍需保留的配置并回主配置。

## 命令护栏

- 只要要跑 Windows 命令，先复用 [../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)。
- 再用 [../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md) 检查路径、引号和删除动作。
- 删除 worktree 前，必须先确认绝对路径仍在预期根目录内。

## 默认输出

默认按下面顺序汇报：

1. 这是不是 `worktreeConfig` 兼容问题
2. 哪些日志是症状，哪条日志更像根因
3. 当前最低风险恢复动作是什么
4. 如果需要，再补一句 worktree 的白话解释
5. 只有用户同意后，再继续做清理或更深入修复

## 边界

- 不把通用 Git worktree 教程写进这里；通用用法交给 [../../vendor/git-advanced-workflows/SKILL.md](../../vendor/git-advanced-workflows/SKILL.md)。
- 不把一次路径猜错当成产品根因。
- 不默认修改主仓库 Git 配置。
- 不在未检查未提交修改前直接删除 worktree。
- 不把“当前会话占用目录导致删不掉”误判成 Git 删除失败。

## 相关技能

- 通用 Git worktree：[../../vendor/git-advanced-workflows/SKILL.md](../../vendor/git-advanced-workflows/SKILL.md)
- 系统化调试：[../superpowers-systematic-debugging/SKILL.md](../superpowers-systematic-debugging/SKILL.md)
- Windows 命令复用：[../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
- Windows 命令护栏：[../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)

## 维护

- 如果以后 Antigravity 官方修掉了 `worktreeConfig` 兼容问题，要收紧触发词和判断条件，不要继续把它当默认根因。
- 新增经验时，优先补“日志签名”和“最低风险恢复动作”，不要把正文扩成泛用 IDE 排障手册。
