# 上游来源记录

## 原始来源

- **仓库：** K-Dense-AI/scientific-agent-skills（GitHub）
- **接受基线路径：** skills/scientific-critical-thinking/
- **已接受提交：** 757b63b1c09798a45c79eea542c9b55dbe04e502
- **已接受版本：** 1.1
- **作者：** K-Dense Inc.
- **许可证：** MIT

## 本地改了什么

1. **删掉了"科学示意图"功能：** 原版有 "Visual Enhancement with Scientific Schematics" 整节，依赖 `scripts/generate_schematic.py` 和 `scripts/generate_schematic_ai.py` 脚本。本地没有这些脚本，保留会导致运行时错误，直接删掉。
2. **GRADE/Cochrane 替换为通用工程证据分级：** 原版的证据层次基于临床医学（RCT > 队列 > 病例对照 > 横断面 > 专家意见），本地改成了更适合工程实验的层次（直接实验 > 仿真验证 > 理论分析 > 类比和外推）。通用原则（多独立复现 > 单次实验、直接测量 > 间接推断）保留了。
3. **新增 THz/通信硬件专项检查：** 新建了 `references/thz_hardware_evaluation.md`，覆盖测量可信度、实验条件完整性、结论边界控制、可复现性四个维度，附常见问题模式列表。
4. **精简临床示例：** `scientific_method.md` 里的临床试验例子替换为通用科学方法说明，加了工程实验中因果推断的注意点。
5. **3 个通用参考文件原样保留：** `common_biases.md`（偏倚分类学）、`statistical_pitfalls.md`（统计陷阱）、`logical_fallacies.md`（逻辑谬误）的内容对工程研究通用，没有改动。
6. **SKILL.md 全部改写：** 用中文重写，语言用日常说法。核心 7 个能力框架保留，但描述精简，详细内容指向 references/。去掉了 `allowed-tools: Read Write Edit Bash`（本地不需要限定工具权限）。
7. **分工说明：** 明确写了不管语言润色（→ ieee-manuscript-edit / sentence-polish）和不管停稿判断（→ paper-review）。
8. **2026-07-25 方法学更新：** 吸收 RoB 2、ROBINS-I、PRISMA 2020、AMSTAR 2、CONSORT 2010 的当前用途；同步更新 `experimental_design.md` 的报告清单版本，并明确这些临床/生物医学工具不直接套用于 THz/通信工程。

## 上游更新情况

- 2026-07-25 已审核至提交 `757b63b1c09798a45c79eea542c9b55dbe04e502`；上游 skill 元数据版本为 1.1
- 本次只吸收方法学版本和适用边界；未吸收图像自动生成、OpenRouter、凭据或第三方传输行为
- 偏倚分类学、逻辑谬误、统计陷阱、实验设计原则这些内容本身就是成熟的学术知识，不会频繁变化
- 如果上游以后在实验设计或统计分析评估方面有重要更新，可以手动合并到 `common_biases.md` 等未修改的文件里
