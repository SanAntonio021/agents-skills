---
name: agent-maintenance-handbook
description: 维护当前本地智能体的底层规则、system prompt、skill 治理和长期维护约定。Use when the user explicitly asks to modify local agent rules, the local system prompt, the skill layout, or maintenance governance; do not use this for ordinary business tasks.
---

# 智能体维护手册

## 作用

这个 skill 只处理“智能体如何被维护”这类底层问题，不处理普通业务任务。

它负责的内容包括：

- 本地 system prompt 和底层规则整理
- skill 目录、命名、路由和治理规则
- 维护协议、编辑约定和长期演进边界
- 其他元信息的索引与收纳

## 何时使用

只有下面这些场景才进入这里：

- 用户明确点名 `agent-maintenance-handbook`
- 任务是在改本地 system prompt
- 任务是在改 skill 架构、技能治理或维护规则
- 任务是在清理长期积累的底层约定、索引或维护协议

## 流程

1. 先确认任务是否真的是“维护智能体本身”，而不是普通业务执行。
2. 找到对应层级：
   - system prompt 精炼
   - skill 治理与路由
   - 文件编辑与维护协议
   - 媒体处理等能力边界
3. 只改最小必要层：
   - 能改局部文件时，不扩大到整套规则重写
   - 能补索引时，不把所有细节都塞回主文件
4. 改完后补最小验证：
   - 路由是否更清楚
   - 边界是否更稳定
   - 是否误伤普通任务

## 边界

- 不作为普通业务 skill 使用。
- 不直接承担网页端 prompt 设计，网页端场景改用 [../web-prompt-engineering/SKILL.md](../web-prompt-engineering/SKILL.md)。
- 不直接替代本地 skill 创建与改写流程，相关工作改用 [../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)。
- 不把一次性项目经验、临时偏好或普通输出习惯写进这里。
- 当已有独立 `custom` skill 能处理任务时，这里只保留治理与索引角色。

## 内部文件

- Skill 发现治理：[instructions/skill-discovery-protocol.md](instructions/skill-discovery-protocol.md)
- 文件编辑维护协议：[instructions/file-editing-best-practices.md](instructions/file-editing-best-practices.md)
- system prompt 精炼：[instructions/system-prompt-refinement.md](instructions/system-prompt-refinement.md)
- 媒体处理能力边界：[instructions/media-processing-limitations.md](instructions/media-processing-limitations.md)

## 维护

- 新规则先判断是否真的属于“底层长期规则”，再决定是否写入这里。
- 已有独立 skill 能承接的内容，优先拆出去，不继续堆在主文件。
- 改动这里时，重点看是否会影响路由、命名、引用和其他治理文档的一致性。
