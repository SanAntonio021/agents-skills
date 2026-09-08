# ask-first 来源说明

说明维护日期：2026-09-08

此日期只表示本地来源说明的维护时间。最近成功检查、最近审核提交和实际接受基线以周检状态及报告为准，三者不能互相替代。

`ask-first` 是本地维护的显式调用技能。外部来源曾用于比较询问方法、设计任务检查项和确认方式，不作为运行时依赖。下列“当前保留”以本版正文为准；通用维度按实际问题使用，未保留的专项清单不构成本版执行要求。

技能正文采用重新组织后的本地表达。上游专用目录、自动提交、固定文档体系、工具绑定和批量询问流程保留在原项目。

## 本次用户需求依据

2026-09-08 用户提供苏格拉底式问诊提示词，确认显式调用后应主动检查表面问题与真实目标，不要求先表达困惑；保留事实、解释、价值判断、目标及证据与反例的区分，一次一问、逐轮更新、六项收束和新问题确认。用户另明确取消固定六问上限，按关键缺口是否厘清停止。

这段文本是本次功能需求依据。用户提及的原作者身份尚未独立核实；发现相同文本的转载仓库不等于找到原作者，不新增未经确认的正式上游。

## 正式跟踪来源

### Addy Osmani: interview-me

- 仓库：https://github.com/addyosmani/agent-skills
- 路径：`skills/interview-me`
- 许可证：MIT
- 当前保留：一次一个问题；判断变化时简述更新，简短整理已确认目标和关键未决事项。
- 保留边界：可见置信度进度和每题固定猜测留在上游；本地采用客观覆盖条件。当前不固定采用 Outcome、User、Success、Constraint 摘要字段。

### Addy Osmani: idea-refine

- 仓库：https://github.com/addyosmani/agent-skills
- 路径：`skills/idea-refine`
- 许可证：MIT
- 当前保留：检查关键假设；需要比较选项时说明各自影响。用户价值由目标和价值取舍的通用提问按需涵盖。
- 保留边界：完整创新工作坊、初始化脚本和固定产物格式留在上游。当前不固定要求比较二至三个方向。

### Matt Pocock: grilling

- 仓库：https://github.com/mattpocock/skills
- 路径：`skills/productivity/grilling`
- 许可证：MIT
- 当前保留：事实由智能体调查，目标和取舍交给用户；按决策依赖逐层询问。
- 保留边界：批量问卷和其他 productivity 技能留在上游。

### Matt Pocock: domain-modeling

- 仓库：https://github.com/mattpocock/skills
- 路径：`skills/engineering/domain-modeling`
- 许可证：MIT
- 当前保留：澄清含糊用词，并将问题收束为准确、具体、可继续行动的表述。
- 保留边界：ADR、上下文文档和完整领域建模产物留在上游。当前未保留通行领域术语、场景、实体和边界情况的固定专项清单。

### Trail of Bits: ask-questions-if-underspecified

- 仓库：https://github.com/trailofbits/skills
- 路径：`plugins/ask-questions-if-underspecified/skills/ask-questions-if-underspecified`
- 许可证：CC BY-SA 4.0
- 当前保留：先检查可获得资料，优先处理高影响信息缺口；低影响、可恢复细节采用合理默认。
- 保留边界：上游每轮多题格式留在原项目；本地始终一次询问一个问题。当前不声明独立安全检查或完整可逆性评估流程。

### Impeccable: shape

- 仓库：https://github.com/pbakaus/impeccable
- 路径：`.agents/skills/impeccable`
- 许可证：Apache-2.0
- 当前保留：只询问会改变问题理解、结论或做法的问题，并沿用已确认内容。
- 保留边界：完整视觉设计工具链和实现指令留在上游。设计任务的真实内容、关键状态、内容规模和保持项不再作为固定检查清单。

### Anthropic: product-brainstorming

- 仓库：https://github.com/anthropics/knowledge-work-plugins
- 路径：`product-management/skills/product-brainstorming`
- 许可证：Apache-2.0
- 当前保留：检查关键假设的依据、相反解释及成立或不成立的后果。
- 保留边界：5 至 7 个发散方向及完整产品管理产物留在上游。当前没有固定的最低成本验证要求。

### Superpowers: brainstorming

- 仓库：https://github.com/obra/superpowers
- 路径：`skills/brainstorming`
- 许可证：MIT
- 当前保留：先查看背景；实质问诊后确认重新定义的问题，再给判断、理由和下一步建议；已有确认直接沿用。
- 保留边界：自动触发、视觉辅助、强制设计文档、自动提交和 writing-plans 交接留在上游。当前不固定比较二至三个方向，也不重复设置已经得到确认的关口。

### wshobson: brand-landingpage

- 仓库：https://github.com/wshobson/agents
- 路径：`plugins/brand-landingpage/skills/brand-landingpage`
- 许可证：MIT
- 当前保留：沿用已确认或纠正的内容，并按实际影响决定下一问。
- 保留边界：Stitch 依赖、落地页生成和视觉实现流程留在上游。受众、核心动作、真实内容、参考案例、品牌感受和关键状态不再作为固定设计检查清单。

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
