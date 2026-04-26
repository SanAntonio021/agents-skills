---
name: agent-maintenance-handbook
description: 维护当前本地智能体的底层规则、系统提示词、技能目录和长期维护约定。只要用户要修改 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md`，精简或重写本地规则，处理本地规则和上游规则的重复、冲突与分层，判断一条维护经验该写进主规则、现有说明文件还是长期约定，分清源文件和当前副本，或排查规则文件不同步，就优先使用这份技能；如果问题已经变成“该不该拆成新技能”或“该新建还是改已有”，先交给 `duihua-jingyan-zhengli` 判断。普通业务任务不要用。
---

# 智能体维护手册

## 这份技能管什么

这份技能只处理“智能体怎么维护”这类底层问题，不处理普通业务任务。

它负责的内容包括：

- 本地系统提示词和底层规则整理
- `AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 这类全局规则文件的分层、去重和精简
- 技能目录、命名、查找顺序和维护规则
- 文件修改约定和长期维护边界
- 其他相关说明该放在哪里

## 何时使用

只有下面这些场景才进入这里：

- 用户明确点名 `agent-maintenance-handbook`
- 任务是在改 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md`
- 任务是在改本地系统提示词
- 任务是在改技能结构、技能维护规则或查找顺序
- 任务已经明确属于维护层，但还要判断该写进主规则、现有说明文件，还是只保留为本地长期约定
- 任务是在处理本地规则和上游规则的重复、冲突或层级边界
- 任务是在清理长期积累的底层约定、索引或维护协议

## 流程

1. 先确认任务是否真的是“维护智能体本身”，而不是普通业务执行。
2. 找到对应层级：
   - 系统提示词和主规则精简
   - 技能查找顺序与目录边界
   - 文件修改和维护约定
   - 媒体处理等能力边界
3. 只改最小必要层：
   - 能改局部文件时，不扩大到整套规则重写
   - 能补索引时，不把所有细节都塞回主文件
4. 如果任务是在改全局规则文件，先区分这次是在做：
   - 主规则做减法
   - 源文件与运行时副本判断
   - 不同步排查和修复
5. 再进入对应说明文件，只读这次真正需要的那一份，不把整套维护文档都读一遍。
6. 修改 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 时，共通规则默认同步；只有平台差异或明确的本地差异，才分开写。
7. 改完后补最小验证：
   - 查找顺序是否更清楚
   - 边界是否更稳定
   - 是否误伤普通任务

## 边界

- 不作为普通业务技能使用。
- 网页端提示词设计也在这里处理，不再单拆独立技能。
- 不直接替代本地技能创建与改写流程，相关工作改用 `skill-creator`。
- 不负责先判断要不要拆成新技能；这类问题先交给 `duihua-jingyan-zhengli`。
- 不把一次性项目经验、临时偏好或普通输出习惯写进这里。
- 当已有独立技能能处理任务时，这里只保留维护和索引角色。

## 内部文件

- 找“该读哪一份技能说明”，以及分清源文件、当前副本和旧目录：[instructions/skill-discovery-protocol.md](instructions/skill-discovery-protocol.md)
- 处理文件修改，以及规则文件没同步上时怎么查、怎么修：[instructions/file-editing-best-practices.md](instructions/file-editing-best-practices.md)
- 精简系统提示词和主规则：[instructions/system-prompt-refinement.md](instructions/system-prompt-refinement.md)
- 网页端无工具环境下的提示词写法：[instructions/web-system-prompt-guidelines.md](instructions/web-system-prompt-guidelines.md)
- 本地子对话交接模板：[instructions/subdialog-handoff-template.md](instructions/subdialog-handoff-template.md)
- 媒体处理能力边界：[instructions/media-processing-limitations.md](instructions/media-processing-limitations.md)

## 维护脚本

- 上游镜像检查与同步：[scripts/manage_repo_mirrors.py](scripts/manage_repo_mirrors.py)

## 维护

- 新规则先判断是否真的属于“底层长期规则”，再决定是否写入这里。
- 改全局规则前，先查重，再补缺口；不要整段照搬上游已覆盖的内容。
- 已有独立技能能承接的内容，优先拆出去，不继续堆在主文件。
- 改动这里时，重点看是否会影响查找顺序、命名、引用和其他维护文档的一致性。
