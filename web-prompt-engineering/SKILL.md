---
name: web-prompt-engineering
description: 把本地 agent 规则改写成网页端无工具环境可执行的提示词。Use when the target is ChatGPT Web, Gemini Web, AI Studio, or another browser AI environment without local file or terminal tools; defer to `agent-maintenance-handbook` for local system prompt maintenance.
---

# 网页端提示词工程

## 作用

这个 skill 用来把“本地智能体能做什么、怎么做”改写成网页端大模型也能执行的提示词。

网页端环境通常没有本地文件系统、终端或 agent 工具，所以这里的重点是把规则写成纯语言可执行的约束，而不是照搬本地指令。

## 流程

1. 先确认目标平台是不是网页端无工具环境。
2. 找出真正影响行为的规则，只保留必要部分。
3. 去掉依赖本地路径、命令、脚本和工具调用的写法。
4. 把规则改成网页端可理解、可遵守的提示词结构。
5. 如果平台会重写记忆或系统信息，优先考虑首轮注入方式或平台自己的开发者指令入口。

## 转写原则

- 中文优先，指令直接，不堆装饰性话术。
- 规则要写成模型自己能执行的行为要求，不写成依赖外部工具的步骤。
- 少用复杂人格分支，优先保留稳定、明确、可复用的核心约束。
- 能缩短就缩短，但不能为了短而损失可执行性。

## 边界

- 不用于本地 Codex、CLI 或 IDE Agent 的底层 prompt 维护。
- 不用于真实文件编辑、终端执行或脚本调用任务。
- 不把本地 agent 独有的工具能力写成网页端默认能力。
- 如果目标其实是维护本地智能体规则，改用 [../agent-maintenance-handbook/SKILL.md](../agent-maintenance-handbook/SKILL.md)。

## 参考资料

- 详细转写说明：[references/guide.md](references/guide.md)

## 维护

- 平台能力变化时，优先更新这里的转写规则，不把网页端限制塞回本地维护手册。
- 如果某个平台已经有单独的稳定写法，再考虑拆成更细的专门 skill。
