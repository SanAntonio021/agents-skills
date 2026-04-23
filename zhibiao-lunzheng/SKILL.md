---
name: zhibiao-lunzheng
description: 用于技术指标、申报指标、考核指标和性能指标的可行性论证、表述修订、定量拆解与来源补强。Use when 核心任务是指标论证本身、指标收紧、证据补强，或需要把工程口径和实验口径分开。
---

# 指标论证

## 作用

这份 skill 负责把模糊、冒进或边界不清的指标，收紧成能被工程或申报文本正式承载的说法。

先收紧定义边界，再判断数值是否站得住，不为了保一个数字去反过来发明口径。

## 流程

1. 先明确指标对象：
   - 单链路、单节点、聚合系统，还是整套系统
   - 峰值、持续值、典型值，还是保证值
   - 实验口径还是工程口径
   - 是否包含上层处理环节
2. 再判断成立强度：
   - `成熟`
   - `有条件`
   - `高风险`
3. 最后给出标准输出：
   - 原始指标
   - 建议表述
   - 建议理由
   - 仍需补的来源

## 来源规则

优先使用这些来源：

- 官方产品页
- 官方技术文档
- 标准
- 同行评审论文
- 可追溯的公开工程演示

如果没有可靠外部支撑，就明确标成工程估算，而不是写成公开事实。

## 边界

- 不把不同指标口径混成一团后直接下结论。
- 不把实验室条件下的数据直接写成工程保证值。
- 不把“可能成立”写成“稳定成立”。
- 不把外部事实写成无来源断言。
- 如果任务只是一般申报讨论，而不是指标论证本身，退回 [../proposal-sci-collab/SKILL.md](../proposal-sci-collab/SKILL.md)。

## 参考文件

- [references/metric-checklist.md](references/metric-checklist.md)
- [references/common-patterns.md](references/common-patterns.md)
- [references/output-template.md](references/output-template.md)
- [references/source-policy.md](references/source-policy.md)
- [references/maintenance-policy.md](references/maintenance-policy.md)

## 维护

- 维护的是“怎样论证指标”，不是“某次项目最后用了什么指标”。
- 新增内容优先扩到 `references/`，不要按项目名堆积。
