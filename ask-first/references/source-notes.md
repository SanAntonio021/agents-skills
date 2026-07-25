# ask-first 来源说明

更新时间：2026-07-25

`ask-first` 是本地维护的显式调用技能。外部来源用于提炼询问方法、设计任务检查项和确认关口，不作为运行时依赖。

技能正文采用重新组织后的本地表达。上游专用目录、自动提交、固定文档体系、工具绑定和批量询问流程保留在原项目。

## 正式跟踪来源

### Addy Osmani: interview-me

- 仓库：https://github.com/addyosmani/agent-skills
- 路径：`skills/interview-me`
- 许可证：MIT
- 吸收：一次一个问题、当前判断、Outcome/User/Success/Constraint 等收束维度。
- 保留边界：可见置信度进度和每题固定猜测留在上游；本地采用客观覆盖条件。

### Addy Osmani: idea-refine

- 仓库：https://github.com/addyosmani/agent-skills
- 路径：`skills/idea-refine`
- 许可证：MIT
- 吸收：开放任务比较 2 至 3 个方向、检查用户价值和关键假设。
- 保留边界：完整创新工作坊、初始化脚本和固定产物格式留在上游。

### Matt Pocock: grilling

- 仓库：https://github.com/mattpocock/skills
- 路径：`skills/productivity/grilling`
- 许可证：MIT
- 吸收：事实由智能体调查，目标和取舍交给用户；按决策依赖逐层询问。
- 保留边界：批量问卷和其他 productivity 技能留在上游。

### Matt Pocock: domain-modeling

- 仓库：https://github.com/mattpocock/skills
- 路径：`skills/engineering/domain-modeling`
- 许可证：MIT
- 吸收：使用通行领域术语，把宽泛描述落到具体场景、实体和边界情况。
- 保留边界：ADR、上下文文档和完整领域建模产物留在上游。

### Trail of Bits: ask-questions-if-underspecified

- 仓库：https://github.com/trailofbits/skills
- 路径：`plugins/ask-questions-if-underspecified/skills/ask-questions-if-underspecified`
- 许可证：CC BY-SA 4.0
- 吸收：先做低风险资料检查，优先处理高影响信息缺口，并覆盖安全性和可逆性。
- 保留边界：上游每轮多题格式留在原项目；本地始终一次询问一个问题。

### Impeccable: shape

- 仓库：https://github.com/pbakaus/impeccable
- 路径：`.agents/skills/impeccable`
- 许可证：Apache-2.0
- 吸收：确认真实内容、关键状态、内容规模和需要保持的部分，只询问会改变结果的问题。
- 保留边界：完整视觉设计工具链和实现指令留在上游。

### Anthropic: product-brainstorming

- 仓库：https://github.com/anthropics/knowledge-work-plugins
- 路径：`product-management/skills/product-brainstorming`
- 许可证：Apache-2.0
- 吸收：检查高风险假设、证据、反例和最低成本验证方式。
- 保留边界：5 至 7 个发散方向及完整产品管理产物留在上游。

### Superpowers: brainstorming

- 仓库：https://github.com/obra/superpowers
- 路径：`skills/brainstorming`
- 许可证：MIT
- 吸收：先看项目背景、比较 2 至 3 个方案、给出推荐并设置确认关口。
- 保留边界：自动触发、视觉辅助、强制设计文档、自动提交和 writing-plans 交接留在上游。

### wshobson: brand-landingpage

- 仓库：https://github.com/wshobson/agents
- 路径：`plugins/brand-landingpage/skills/brand-landingpage`
- 许可证：MIT
- 吸收：设计任务确认受众、核心动作、真实内容、参考案例、品牌感受和关键状态；已有答案直接采用。
- 保留边界：Stitch 依赖、落地页生成和视觉实现流程留在上游。

## 补充研究来源

以下来源参与过方法比较，首版保留为研究参考：

- GitHub Spec Kit `clarify`：按影响程度和不确定程度排序问题。
- GSD Core `questioning`：从用户关注点继续追问，把宽泛词转换成具体场景。
- OpenSpec `explore`：先探索背景和方案，确认后进入执行。
- BMAD Product Brief：先让用户完整表达，再结构化当前理解。
- Agent OS `shape-spec`：读取既有产品资料并设置执行确认关口。
- Product Manager Skills：保存已确认内容、暂停后恢复当前问题。
- Socratic Method Prompt：检查关键假设的依据、反例和代价。

这些材料包含流程文档、命令模板或更大工作流。现有周检机制只登记具有 `SKILL.md` 的正式上游技能。
