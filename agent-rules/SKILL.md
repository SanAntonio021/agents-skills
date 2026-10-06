---
name: agent-rules
description: 维护全局规范和系统提示词，并执行自建技能的定向发布与生效核验。用户要求精简 AGENTS.md、CLAUDE.md、GEMINI.md，处理规则归属、重复、冲突和同步关系，或发布技能时使用。具体技能创建、修改和验证由 skill-creator 承接，目录及生效诊断由 skill-check 承接；普通业务请求不进入维护流程。
---

# 全局规范维护与技能发布

维护范围与授权沿用全局规范。先区分唯一源码、受管理入口与当前运行副本，再读取本次维护需要的操作说明。

## 按任务选择

- **全局规则与提示词**：在这里判断规则应放在哪一层，去重、精简并维护共通内容与平台差异。网页端无工具提示词也由这里承接。
- **具体技能创建、修改与验证**：交给 [skill-creator](../skill-creator/SKILL.md)。
- **技能发布**：读取[技能定向发布](references/skill-upstream-maintenance.md#技能定向发布)，沿用现有提交、同步和核验流程。
- **相关任务转交**：目录、来源、生效诊断及上游发现交给 [skill-check](../skill-check/SKILL.md)；对话经验整理交给 [chat-notes](../chat-notes/SKILL.md)；供应商与请求链路分别交给 `codex-relay-chain`、`claude-relay-chain`。

只加载当前步骤需要的技能和参考，不按上述列表逐一加载。

## 规则修改

1. 已由 CC Switch 全文提供的全局规则直接遵循。需要修改源码时，先按用户指定位置、当前项目说明或已核实的维护目录定位，并读取源码同目录的修改说明；启动用户的 `.agent-rules/local.md` 存在时可补充定位信息，缺失不要求创建。无法定位时只暂停依赖源码的修改并询问位置，继续独立检查。先区分源码、受管理入口和当前运行副本。
2. 判断实际问题和内容归属：全局约定放共享正文，本机环境事实留本机文件，可复用业务方法进对应技能，项目事实留项目。先查重，优先修改已有内容，不把一次性问题写成长期规则。
3. 在唯一源码中修改，保留实际需要的平台差异；受管理入口由受支持流程更新。
4. 检查含义、引用及受影响的行为，验证方法沿用 `skill-creator`。

## 按需资料

- 规则分层、精简和写入位置：[系统提示词与主规则](references/system-prompt-refinement.md)。
- 当前工具下的文本修改，或源文件与当前文件不同步：[文件修改与同步判断](references/file-editing-best-practices.md)。
- 技能查找、源目录与运行副本：[技能查找顺序](references/skill-discovery-protocol.md)。
- 网页端无工具环境：[提示词写法](references/web-system-prompt-guidelines.md)；涉及媒体能力时再读 [媒体处理](references/media-processing-limitations.md)。
- 已授权的技能提交、同步及验收：[技能定向发布](references/skill-upstream-maintenance.md#技能定向发布)；失败后续做见同页 [恢复说明](references/skill-upstream-maintenance.md#发布失败后的恢复)。
- 上游发现、来源登记、候选审核及周检：[上游维护](references/skill-upstream-maintenance.md)。已有镜像和来源脚本入口保留在该参考中，不为普通修改运行它们。
- 维护 CC Switch 共用后台组件的定位或引用时：[后台组件边界](references/skill-upstream-maintenance.md#cc-switch-后台组件)。不涉及该组件就不检查其环境。

## 发布验收

发布只走现有受支持后台流程，不手工覆盖运行副本、直接修改数据库或切换前台兜底。源码修改、测试通过和提交推送分别如实报告；只有定向同步及同参数只读核验满足 `runtime_active`、四层完整文件一致和必要元数据检查，才确认技能已生效。
