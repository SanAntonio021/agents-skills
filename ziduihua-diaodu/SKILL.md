---
name: ziduihua-diaodu
description: 为本地 Codex 子对话生成分流 prompt 和固定回传契约。Use when 用户明确要求把支线问题分流到另一个本地 Codex 对话、创建子线程，或给另一个本地 Codex 聊天窗口写 handoff prompt；prefer this over `codex` when 目标是 prompt 交接，而不是直接启动新 CLI 进程。
---

# 子对话调度

## 作用

这份 skill 用来把主对话里冒出的支线问题压缩成一份可直接贴给本地 Codex 子对话的 prompt，并锁定固定回传格式。

它只负责 handoff 文本，不负责自动开子对话，也不负责执行 `codex exec`。

## 流程

1. 先判断当前问题是不是适合分流的支线。
   适合的通常是补充核查、局部分析、短支线处理；不适合的是 trivial 小问题，或与主线强耦合、需要大量共享隐式上下文的问题。
2. 如果不适合分流，直接说明原因，并建议留在当前对话处理。
3. 如果目标其实是网页端无工具对话，改走 [../web-prompt-engineering/SKILL.md](../web-prompt-engineering/SKILL.md)。
4. 如果用户要的是实际启动新的 `codex exec` 进程，改走 [../codex-cli-local/SKILL.md](../codex-cli-local/SKILL.md)。
5. 真正分流时，只保留子对话完成任务所需的最小背景，不把主对话全部上下文原样搬过去。
6. 输出固定为两段：
   - `## 子对话 Prompt`
   - `## 回传契约`

## 默认回传

`## 回传契约` 默认包含这五项：

- `结论`
- `关键依据或关键观察`
- `未决点`
- `建议主对话下一步`
- `完成状态`

## 边界

- 不把 trivial 小问题硬包装成子对话调度。
- 不把与主线强耦合的问题硬拆出去。
- 不把网页端子对话当成本地 Codex 子对话处理。
- 不把“写 prompt”与“真的启动新进程”混成一件事。
- 不输出“我已经开了子线程”“我已经启动子代理”之类不符合事实的话。

## 参考文件

- 提示词骨架：[references/prompt-template.md](references/prompt-template.md)
- 提示词基线：`<agents-root>\prompt_guidelines\openai.md`

## 相关技能

- 本地 Codex CLI：[../codex-cli-local/SKILL.md](../codex-cli-local/SKILL.md)
- 网页 Prompt 工程：[../web-prompt-engineering/SKILL.md](../web-prompt-engineering/SKILL.md)
- 多角色深度调研：[../duo-juese-shendu-diaoyan/SKILL.md](../duo-juese-shendu-diaoyan/SKILL.md)

## 维护

- 保持它只负责“显式分流 + handoff prompt + 固定回传契约”，不把执行逻辑写回正文。
- 如果本地 Codex 对话能力边界或 prompt 模板变化，优先先改 `references/prompt-template.md`。
