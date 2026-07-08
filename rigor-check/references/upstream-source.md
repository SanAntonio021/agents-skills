# 上游来源记录

## 原始来源

- **仓库：** K-Dense-AI/scientific-agent-skills（GitHub）
- **路径：** scientific-skills/rigor-check/
- **作者：** K-Dense Inc.
- **许可证：** MIT

## 本地改了什么

1. **删掉了"科学示意图"功能：** 原版有 "Visual Enhancement with Scientific Schematics" 整节，依赖 `scripts/generate_schematic.py` 和 `scripts/generate_schematic_ai.py` 脚本。本地没有这些脚本，保留会导致运行时错误，直接删掉。
2. **GRADE/Cochrane 替换为通用工程证据分级：** 原版的证据层次基于临床医学（RCT > 队列 > 病例对照 > 横断面 > 专家意见），本地改成了更适合工程实验的层次（直接实验 > 仿真验证 > 理论分析 > 类比和外推）。通用原则（多独立复现 > 单次实验、直接测量 > 间接推断）保留了。
3. **新增 THz/通信硬件专项检查：** 新建了 `references/thz_hardware_evaluation.md`，覆盖测量可信度、实验条件完整性、结论边界控制、可复现性四个维度，附常见问题模式列表。
4. **精简临床示例：** `scientific_method.md` 里的临床试验例子替换为通用科学方法说明，加了工程实验中因果推断的注意点。
5. **4 个通用参考文件原样保留：** `common_biases.md`（偏倚分类学）、`statistical_pitfalls.md`（统计陷阱）、`logical_fallacies.md`（逻辑谬误）、`experimental_design.md`（实验设计）的内容对工程研究通用，没有改动。
6. **SKILL.md 全部改写：** 用中文重写，语言用日常说法。核心 7 个能力框架保留，但描述精简，详细内容指向 references/。去掉了 `allowed-tools: Read Write Edit Bash`（本地不需要限定工具权限）。
7. **分工说明：** 明确写了不管语言润色（→ ieee-manuscript-edit / sentence-polish）和不管停稿判断（→ paper-review）。

## 上游更新情况

- K-Dense 仓库整体活跃（最新版本 2.37.1，2026-05 有更新），但 rigor-check 这个 skill 的核心内容很稳定
- 最近的改动都是格式修缮（2026-04-11 修引用链接、2026-03-03 清理、2026-02-23 格式统一），核心方法论上一次实质更新是 2025-12-12
- 偏倚分类学、逻辑谬误、统计陷阱、实验设计原则这些内容本身就是成熟的学术知识，不会频繁变化
- 如果上游以后在实验设计或统计分析评估方面有重要更新，可以手动合并到 `common_biases.md` 等未修改的文件里
