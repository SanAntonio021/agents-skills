# Report Template

周报 `weekly/<date>.md` 固定按这个顺序输出：

1. `扫描范围`
2. `当前实际会用到的技能`
3. `摘要计数`
4. `严重问题`
5. `真的重复技能`
6. `名字不一致`
7. `职责相近但不该直接合并`
8. `链接或路径失效`
9. `空技能或坏技能`
10. `建议动作`
11. `无需动作说明`

`summary.json` 与周报保持同一批结论，但结构化保留：

- 扫描根目录与报告目录
- 本地目录规则
- 当前实际会用到的技能清单
- 各检查项计数
- 各类 findings 详情
- 建议动作与无需动作说明

如果某个检查项没有发现问题，也要在周报里显式写 `- 无`，不要省略该章节。

## 历史使用审计报告

`audit_skill_usage.py` 使用独立路径，避免和目录卫生审计的同名产物相互覆盖：

- `usage/manifests/<date>/summary.json`
- `usage/weekly/<date>.md`

周报固定顺序：

1. `扫描范围`
2. `已用`
3. `历史内未见使用`
4. `疑似漏用`
5. `可能冗余`
6. `解释边界`

`summary.json` 还要结构化保留技能位置与 active host、使用证据、Claude 启动候选加载计数，以及
`parse_errors`、`missing_fields`、候选截断数、bridge 临时副本排除数和
`codex_implicit_usage_not_captured=true`。证据源只允许根代号、相对路径和行号，不能写 transcript
绝对路径或原始 session ID。
