# 外部结构参考

核对日期：`2026-07-14`。

这些项目只用于数据结构、状态模型和评测设计。它们不能证明 IEEE 或某本期刊的投稿要求。

| 项目 | 许可 | 可借鉴结构 | 不采用内容 |
| --- | --- | --- | --- |
| [Aperivue/medsci-skills](https://github.com/Aperivue/medsci-skills) | MIT | 单一事实来源、文件哈希、build/audit/freeze、返修意见编号和台账 | 医学期刊声明和流程规则 |
| [my-submission-formatting-agent](https://github.com/maxwell2732/my-submission-formatting-agent) | README 称 MIT，但缺独立 LICENSE | 要求提取日期、未知字段为 null、PASS/WARN/FAIL | 自动补写缺失章节、无依据质量分数、关键字段 ASSUMED |
| [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | MIT | 专业 skill 分工、同行评审维度、模板和正文编辑分离 | 2024 年宽泛 IEEE 归纳和任何易变规则 |
| [Open Journal Systems](https://github.com/pkp/ojs) | GPL-3.0；文档 CC BY 4.0 | Submission、Review、Copyediting、Production、Publication 粗粒度阶段 | GPL 代码、编辑部内部状态 |
| [Kotahi](https://github.com/eLifePathways/Kotahi) | 主体 MIT | 可配置工作流、角色、任务、事件记录 | 完整出版系统的复杂权限模型 |
| [NISO MECA](https://www.niso.org/publications/rp-30-2023-meca) | 规范页面未给开放复用许可 | manifest、元数据、源文件、转投包概念 | 直接复制规范文本或默认生成 MECA/JATS 包 |
| [NISO Peer Review Terminology](https://peerreviewterminology.niso.org/) | 页面未见明确复用许可 | 评审模式分维度记录 | 把术语模型当稿件状态机 |
| [Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) | Apache-2.0 | 有/无 skill 对照、断言、人工评审页、正负触发测试 | 环境专用命令照搬 |

## 吸收结果

- 项目状态同时记录 `lifecycle`、`decision`、`revision_round`、`portal_tasks`、`blockers` 和 `operation_history`。
- 文件 manifest 记录角色、版本、SHA256、适用阶段、上传状态和平台显示名。
- 规则记录 URL、访问日期、关键要求、期刊、文章类型、阶段和核验状态。
- 投稿页面自由文本是独立数据源，不能假定与 PDF、Cover Letter 或 LaTeX 自动一致。
- 评测包含确定性校验、安全缺陷注入、有/无 skill 对照和近似不触发测试。
