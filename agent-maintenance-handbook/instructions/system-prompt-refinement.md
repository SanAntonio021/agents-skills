# System Prompt Refinement

## Purpose

约束底层系统规则的增删改方式，避免把一次性问题写成永久全局规则。

## Scope

这里讨论的是：

- 智能体底层约束
- 全局路由与维护规则
- 长期复用的行为护栏

这里不讨论：

- 普通任务输出风格
- 单项目事实
- 临时老师意见或一次性偏好
- 本应进入独立 skill 的业务流程

这里也不单独充当具体 prompt 模板写法手册。涉及本地 system prompt 或其他具体 prompt 模板的结构化写法时，默认参考 `<agents-root>\prompt_guidelines\openai.md`。

## Core Principles

1. 只有在真实失败、真实冲突或真实重复模式出现后，才新增全局规则。
2. 规则必须尽量短、客观、可执行。
3. 能放进 `custom` skill 的，不放进全局 prompt。
4. 能放进项目目录的，不放进全局 prompt。
5. 新规则应尽量替换旧规则，而不是不断叠加。

## Placement Guide

在决定“该把规则写到哪里”时，按这个顺序判断：

- 跨工作区、跨新对话都要生效的机器级路由与维护约定：优先写入 `%USERPROFILE%\.codex\AGENTS.md`，必要时再同步到 `AGENTS.md`
- 当前同步 skill 仓内部的路由、目录模型、维护约定：写入 `AGENTS.md` 或相应约定说明文档
- 可复用任务流程：写入对应 `custom` skill
- 仅用于维护智能体本身的方法：写入 `agent-maintenance-handbook/instructions/`
- 单项目限定规则：写入项目目录

## Refinement Workflow

1. 先指出真实触发问题是什么。
2. 再判断它属于：
   - 全局规则问题
   - skill 路由问题
   - 某个具体 skill 的正文问题
   - 某个项目本地问题
3. 只有确属全局层时，才改底层规则。
4. 改完后检查是否有旧规则已被覆盖，应一并删去。

## Prompt Template Baseline

当任务已经进入“写或改具体 prompt 模板”这一步时，按以下分工处理：

- 本文件负责判断这条内容应不应该进入底层规则，以及应写在哪一层。
- 具体 prompt 模板的结构化写法，默认参考 `<agents-root>\prompt_guidelines\openai.md`。
- 优先落实其中与当前任务直接相关的 `Context / Task / Constraints / Output`、作用域纪律、约束精确化和缓存布局原则。
- 不把 `openai.md` 里的整套通用写法原样抄回全局规则；这里只保留经过本地验证后仍需长期复用的维护规则。

## Good Rule Shape

优先使用这种规则形态：

- 明确触发条件
- 明确允许或禁止的动作
- 尽量能映射到工具或文件层行为

避免这种规则形态：

- 纯态度词
- 纯审美词
- 没有边界的“大而全”原则
- 依赖一次性上下文才能理解的补丁句子

## Maintenance

- 每次改底层规则时，优先删旧规则，避免只增不减。
- 如果某条规则已经稳定外拆为 `custom` skill，应把 handbook 留成索引和维护原则，不重复保留整套流程。
