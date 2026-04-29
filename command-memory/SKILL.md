---
name: command-memory
description: 复用已验证的 Windows 和 PowerShell 命令写法，并内置终端执行静态护栏，减少路径、引号、编码、shell 混用和外部 CLI 写错的概率。只要任务要用到 `shell_command`、PowerShell 或 Windows 命令行，尤其是处理路径、编码、搜索、压缩解压、Office/PowerPoint COM 自动化、规则文件不同步、软链修复，或刚经历“先失败后成功”的高风险命令场景，就优先使用这份技能。
---

# 命令模式记忆

## 作用

这份技能负责在执行前优先复用已经证明可行的 Windows 命令形态，并套上最基本的终端执行护栏。

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

## 静态护栏

1. 默认使用 PowerShell，除非用户明确要求别的 shell。
2. 已知目标路径时，优先用绝对 Windows 路径。
3. 路径参数一律加引号；文件操作优先用 `-LiteralPath`。
4. 主命令前先做最小存在性检查：
   - `Test-Path`
   - `Get-ChildItem`
5. 文本编辑优先 `apply_patch`，批量格式化或机械重写才用命令。
6. 文件操作优先 PowerShell 原生命令：
   - `Copy-Item`
   - `Move-Item`
   - `Remove-Item`
   - `Select-String`
   - `Get-ChildItem`
   - `Expand-Archive`
7. 不跨 shell 拼接破坏性文件操作；删除或移动前先确认最终目标路径仍在预期目录内。
8. 失败一次后，要改命令形态，不盲目重试。

## Office/PowerPoint 自动化护栏

用 PowerShell COM 自动化 PowerPoint、Word、Excel 时，把它当成本地桌面应用操作，不要当成普通无状态命令：

- 能用文件级检查时，优先不用 Office COM。例如 PPTX 是否损坏可先用 zip 完整性检查；内容结构可先解包 XML。
- 必须用 PowerPoint 导出预览或 PDF 时，只打开本次生成或用户明确指定的文件，不顺手处理用户正在编辑的演示文稿。
- 启动 COM 前先检查是否已有 Office 进程或打开的文档。若可能存在用户未保存内容，先说明风险，再继续。
- 如果脚本连接到已存在的 Office 实例，结束时只关闭自己打开的文档，不调用 `Quit()` 关闭整个应用。
- 只有确认本次创建的是独立实例，并且没有用户文档挂在同一实例上，才考虑 `Quit()`。不确定时宁可留下应用进程，也不要冒险关掉用户未保存文件。
- 预览验证可以分层做：先检查文件完整性，再尝试导出本次生成文件；不要把“打开后立即关闭 PowerPoint”作为默认验证动作。

## 流程

1. 准备运行 `shell_command` 前，先判断是不是高风险 Windows 命令场景。
2. 先套用上面的静态护栏，确认 shell、路径、引号和前置检查。
3. 如果是重复出现或高风险场景，就先读 [references/validated-command-patterns.md](references/validated-command-patterns.md)，再只打开最相关的模式文件。
4. 只复用命令骨架：
   - shell 类型
   - 引号方式
   - 前置检查
   - 环境变量
   - 参数替换方式
5. 用本次任务的真实路径和参数替换占位符，不照抄旧命令全文。
6. 组装好命令后，再回查静态护栏，确认没有路径、引号、shell 混用或破坏性操作风险。
7. 没有可用模式时，按静态护栏构造一条最小命令，不临时发明复杂链式命令。

## 回写规则

- 只有“先失败、后成功”的高价值修正，才考虑回写。
- 只回写成功后的命令骨架，不回写失败命令全文。
- 优先更新最接近的现有模式文件；只有放不下时才新建。
- 同类问题反复出现时，不只在当前任务里临时修，要同步更新模式库。
- 进入这种纠偏后，优先按 [references/recovery-capture-checklist.md](references/recovery-capture-checklist.md) 做最小闭环。

## 边界

- 不把这里当失败日志本。
- 不自动复盘所有终端报错。
- 不跳过静态护栏。
- 不把完整历史命令全文堆进记忆库。
- 不因为模式库里有相似条目，就忽视当前任务的路径和参数差异。

## 相关文件

- 模式索引：[references/validated-command-patterns.md](references/validated-command-patterns.md)
- 规则文件不同步与软链修复：[references/rule-file-sync-and-symlink.md](references/rule-file-sync-and-symlink.md)
- 模式库维护规则：[references/pattern-library-maintenance.md](references/pattern-library-maintenance.md)
- 纠偏回写检查清单：[references/recovery-capture-checklist.md](references/recovery-capture-checklist.md)

## 维护

- `SKILL.md` 只负责路由、分诊和边界，不堆模式细节。
- 新模式优先补进最接近的单场景文件，不继续膨胀总索引页。
- 静态护栏只保留稳定通用规则；一旦变成具体命令范式，就下沉到 `references/`。
- 如果未来真要拆出 `bash` 或 `git` 专门层，再另建技能，不把这里拉成跨平台总入口。
