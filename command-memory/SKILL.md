---
name: command-memory
description: 复用已验证的 Windows 和 PowerShell 命令写法，减少路径、引号、编码和外部 CLI 写错的概率。只要任务要用到 `shell_command`、PowerShell 或 Windows 命令行，尤其是处理路径、编码、搜索、压缩解压、规则文件不同步、软链修复，或刚经历“先失败后成功”的高风险命令场景，就优先使用这份技能；如果已经有现成模式，先来这里复用，再考虑自己临时拼命令。
---

# 命令模式记忆

## 作用

这份技能负责在执行前优先复用已经证明可行的 Windows 命令形态。

它关注的不是“这条命令做什么业务”，而是“这条命令在当前 Windows 环境下应该怎么写才稳”。

## 何时使用

下面这些情况优先进入这里：

- 路径包含空格、中文或很深的目录
- 需要外部 CLI
- 需要 PowerShell 下的 Python 单行命令
- 涉及搜索、遍历、压缩解压、文件移动或复制
- 规则文件没同步上，需要分清源文件、软链和旧副本
- 需要修软链，或先临时复制把内容对齐
- 用户明确要求“按上次正确方式跑”
- 刚刚有一条 Windows 命令失败，后来改形态后成功了

## 流程

1. 准备运行 `shell_command` 前，先判断是不是高风险 Windows 命令场景。
2. 如果不是，直接回退到 [../terminal-safe/SKILL.md](../terminal-safe/SKILL.md)。
3. 如果是，就先读 [references/validated-command-patterns.md](references/validated-command-patterns.md)，再只打开最相关的模式文件。
4. 只复用命令骨架：
   - shell 类型
   - 引号方式
   - 前置检查
   - 环境变量
   - 参数替换方式
5. 用本次任务的真实路径和参数替换占位符，不照抄旧命令全文。
6. 组装好命令后，再叠加 [../terminal-safe/SKILL.md](../terminal-safe/SKILL.md) 的静态护栏。
7. 没有可用模式时，回到终端护栏按常规方式构造命令。

## 回写规则

- 只有“先失败、后成功”的高价值修正，才考虑回写。
- 只回写成功后的命令骨架，不回写失败命令全文。
- 优先更新最接近的现有模式文件；只有放不下时才新建。
- 同类问题反复出现时，不只在当前任务里临时修，要同步更新模式库。
- 进入这种纠偏后，优先按 [references/recovery-capture-checklist.md](references/recovery-capture-checklist.md) 做最小闭环。

## 边界

- 不把这里当失败日志本。
- 不自动复盘所有终端报错。
- 不跳过 [../terminal-safe/SKILL.md](../terminal-safe/SKILL.md) 的静态护栏。
- 不把完整历史命令全文堆进记忆库。
- 不因为模式库里有相似条目，就忽视当前任务的路径和参数差异。

## 相关文件

- 模式索引：[references/validated-command-patterns.md](references/validated-command-patterns.md)
- 规则文件不同步与软链修复：[references/rule-file-sync-and-symlink.md](references/rule-file-sync-and-symlink.md)
- 模式库维护规则：[references/pattern-library-maintenance.md](references/pattern-library-maintenance.md)
- 纠偏回写检查清单：[references/recovery-capture-checklist.md](references/recovery-capture-checklist.md)
- Windows 终端护栏：[../terminal-safe/SKILL.md](../terminal-safe/SKILL.md)

## 维护

- `SKILL.md` 只负责路由、分诊和边界，不堆模式细节。
- 新模式优先补进最接近的单场景文件，不继续膨胀总索引页。
- 如果未来真要拆出 `bash` 或 `git` 专门层，再另建技能，不把这里拉成跨平台总入口。
