---
name: journal-selection
description: 为论文稿或摘要选投稿期刊，输出 reach/match/safe 三档投稿清单和被拒后的降级改投阶梯。Use when 用户问"这篇投哪""投什么期刊合适""TTST 还是 TMTT""值不值得冲 NC"，或论文被拒要选下一个目标刊，或审稿人/编辑说 not a fit 需要重新定位；也要处理学校指定的中科院分区版本、JCR 分区与 SCIE/ESCI 的区别。收到 scope desk rejection 时先判断是范围问题还是内容问题，不要自动推断稿件质量不足。Prefer this over `research-lookup` when 目标是给自己的稿件选投稿去向，而不是检索文献。选定期刊后的 LaTeX 格式与投稿工程找 `latex-paper`，内容精修找 `ieee-manuscript-edit`，投稿前把关和模拟审稿找 `paper-review`；选定 IEEE 期刊后的网页投稿和后续生命周期事务找 `ieee-journal-submission`。
---

# 选刊定位

## 作用

从论文画像出发，给出分档投稿清单和被拒后的改投阶梯。它回答"这篇该投哪、被拒了下一步投哪"，不替代期刊官方投稿须知，也不改稿。

## 流程

1. **画像**。从摘要或稿件提取五个信号：
   - 子方向（太赫兹链路 / 微波电路 / 无线传输方案 / 通信系统架构 / 跨学科发现）
   - 证据形态（纯理论推导 / 仿真验证 / 实测样机或链路实验 / 仿真+实测两段）
   - 贡献类型（新机制、新方法、新系统、新性能纪录、新测量）
   - 实验与数据（频段、平台、数据是否可公开）
   - 强度与野心（结果有多干净、对相邻领域有没有吸引力；诚实评估，虚高浪费月数）
2. **建候选集**。读取 [references/journal-profiles.md](references/journal-profiles.md) 的常投刊池画像；候选刊不在画像库时明说"不在画像库，需现查官网"，不硬凑。
3. **五维评估**。对每个候选刊评 Fit、录用可能、审稿周转、费用政策、受众面。不编造精确加权总分，只用于分层排序，并写明理由。
4. **输出三档清单**：
   - `reach`：Fit 高但录用概率低的顶刊，结果确有跨领域吸引力才值得
   - `match`：Fit 和强度匹配的主力目标
   - `safe`：Fit 高、录用概率高、周转快的保底刊
5. **预写降级阶梯**。顶刊被拒是常态，事先写好"被拒后投哪、需要改什么"（缩短格式、补稳健性、换叙事框架）。桌面拒稿通常直接降档改投；审稿拒稿要先解决决定性质疑再投下一家。

## 输出结构

```text
【论文画像】子方向 / 证据形态 / 贡献类型 / 实验数据 / 强度
【Reach】刊名 — 一句话理由；需现查的关键事实
【Match】刊名 — 一句话理由；需现查的关键事实
【Safe】 刊名 — 一句话理由；需现查的关键事实
【投递顺序与阶梯】首选 → 若拒 → 次选（需要改什么）→ …
【待核查】投稿前需上官网确认的事实清单
```

## 硬规则

1. **易变事实一律现查**。版面费、录用率、审稿周期、限长、开放获取政策不凭记忆引用，输出里只标"需现查"并给官方入口（见画像文件各刊的官方核查条目）。
2. **诚实评估强度**。不把稿子捧进过不了的 reach，也不埋没一个现实的 match。
3. **覆盖诚实**。画像库没覆盖的刊直接说，不强行推荐。
4. **Fit 判断服从画像红线**。稿件触发某刊的秒拒条目时，不因用户偏好该刊而弱化提示。
5. **分区口径必须拆开**。回答中科院分区时，先确认年份、升级版/新锐表、大类/小类和学校采用的数据库；同时单列 JCR Quartile 与 SCIE/ESCI 收录，不以第三方网站或 JCR Q1 代替学校口径。
6. **scope desk rejection 先分类**。若编辑明确写 `scope rather than quality`、`not a fit` 或 `not recommended to send for review`，记录为编辑初筛范围拒稿，不直接推断实验、创新或论证不足；先对照决定信和已提交稿件基线，再判断是否需要内容修改。
7. **机构评价约束优先于泛化推荐**。若用户给出“学校必须满足某年某版一区/SCIE”等硬约束，先过滤不满足约束的候选，再讨论 fit、周转和风险；易变排名不写入长期画像。

## 边界

- 不管投稿格式和 LaTeX 工程（`latex-paper`）。
- 不改内容不润色（`ieee-manuscript-edit`）。
- 不做停稿判断、投稿预检、模拟审稿（`paper-review`）。
- 不做文献检索（`research-lookup`）。
- 不操作 IEEE 投稿系统，不处理作者、声明、返修提交、版权费用和校样（`ieee-journal-submission`）。

## 相关技能

- 学术写作总路由：[../writing-router/SKILL.md](../writing-router/SKILL.md)
- 投稿前把关与模拟审稿：[../paper-review/SKILL.md](../paper-review/SKILL.md)
- SCI/IEEE 论文精修：[../ieee-manuscript-edit/SKILL.md](../ieee-manuscript-edit/SKILL.md)
- LaTeX 投稿工程：[../latex-paper/SKILL.md](../latex-paper/SKILL.md)
- IEEE 期刊投稿全生命周期：[../ieee-journal-submission/SKILL.md](../ieee-journal-submission/SKILL.md)

## 相关文件

- 常投刊池画像：[references/journal-profiles.md](references/journal-profiles.md)
- 上游来源说明：[references/upstream-source.md](references/upstream-source.md)
- 触发边界测试：[references/trigger-evals.json](references/trigger-evals.json)

## 维护

- 画像文件只沉淀相对稳定的定位、证据链红线和秒拒条目；易变事实（费用、周期、限长）永远不写死。
- TTST/TMTT 画像目前是初稿，红线条目需与用户的实际投稿经验校准后才可当依据。
- 新增期刊画像时保持统一版式：定位 → 证据链红线 → 秒拒触发 → 兄弟刊分流 → 官方核查。
