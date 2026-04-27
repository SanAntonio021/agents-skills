# Finding Severity

`skill-check` v1 默认把发现分成三层：

- `阻塞项`
  - 不该出现的嵌套 skill
  - `docs/` 下误放 skill
  - 活跃 skill 目录缺少 `SKILL.md`
  - `SKILL.md` 只有空 frontmatter 或空正文
- `维护项`
  - 真重复候选（按 `name:`）
  - 名字漂移
  - 边界交叉候选
  - 本地路径或引用漂移
- `无需动作说明`
  - `custom + vendor` 的 wrapper 排除
  - 被 `custom` wrapper 显式引用的已知上游入口变体
  - 本次扫描未命中的检查项说明

v1 不自动执行修复；所有结果都只输出建议动作和人工复核说明。
