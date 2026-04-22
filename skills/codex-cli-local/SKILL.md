---
name: codex-cli-local
description: 为当前 Windows 机器上的 Codex CLI 提供本地调用规则。Use when the user wants to run `codex exec`, `codex exec resume`, or `codex exec review` here; prefer this over `vendor/codex` when PowerShell、路径、工作目录或本地环境约束会影响实际执行。
---

# Codex CLI Local

## 作用

这个 skill 负责把 `vendor/codex` 的通用能力，转换成当前 Windows / PowerShell 环境下可直接执行的本地做法。

重点不是重复上游全文，而是补三类本地差异：

- 当前机器上的 CLI 可用性检查
- PowerShell 下的命令写法和路径安全
- `exec / resume / review` 的入口选择

## 流程

1. 先读取上游基线：[../../vendor/codex/SKILL.md](../../vendor/codex/SKILL.md)
2. 执行前先确认本地 CLI 形态：
   - `codex --version`
   - `codex exec --help`
   - 需要续跑时再看 `codex exec resume --help`
3. 根据目标选入口：
   - 新任务执行：`codex exec`
   - 接着上一轮继续：`codex exec resume --last`
   - 审查现有实现：`codex exec review`
4. 明确工作目录；只有目录不是 git 仓库，或用户明确要求绕过检查时，才加 `--skip-git-repo-check`
5. 根据任务风险选 sandbox：
   - `read-only`
   - `workspace-write`
   - `danger-full-access`
6. 涉及 PowerShell 命令、路径或外部 CLI 时，优先叠加：
   - [../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
   - [../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)

## 常用命令

```powershell
codex exec --sandbox read-only -C "D:\path\to\repo" "Review this repository"
```

```powershell
codex exec review --base main
```

```powershell
codex exec resume --last "Continue with the next step"
```

## 边界

- 不把这个 skill 当成新的上游规范；它只是 `vendor/codex` 的本地规则层
- 不为了“看起来像多 agent”就强行新开 `codex exec` 进程
- 如果当前会话已经足够完成任务，优先留在当前会话
- 不把 CLI 版本号、模型快照名或一次性命令细节写死在正文里

## 相关技能

- 上游基线：[../../vendor/codex/SKILL.md](../../vendor/codex/SKILL.md)
- 命令模式复用：[../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
- Windows 终端护栏：[../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)
- 本地子对话分流：[../ziduihua-diaodu/SKILL.md](../ziduihua-diaodu/SKILL.md)

## 维护

- 上游 `vendor/codex` 更新时，优先同步上游，再检查本地差异是否还成立
- 正文只保留本地可执行差异，不复制上游长段说明
- 当 `codex exec --help` 或 `codex exec resume --help` 明显变化时，再回收这里的命令示例
