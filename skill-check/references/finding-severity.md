# Finding Severity

`skill-check` v1 默认把发现分成三层：

- `严重问题`
  - 不该出现的嵌套 skill
  - `docs/` 下误放 skill
  - 活跃 skill 目录缺少 `SKILL.md`
  - `SKILL.md` 只有空的文件开头配置或空正文
- `维护项`
  - 真的重复技能（按 `name:`）
  - 名字不一致
  - 职责相近但不该直接合并
  - 本地链接或路径失效
- `无需动作说明`
  - `custom + vendor` 的本地补充关系，不算重复
  - 被 `custom` wrapper 显式引用的已知上游入口变体
  - 本次扫描未命中的检查项说明

v1 不自动执行修复；所有结果都只输出建议动作和人工复核说明。
