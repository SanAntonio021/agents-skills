# 历史使用审计集成验收

所有真实历史测试都使用隔离报告目录；不得把报告、真实 transcript 或片段提交进技能仓库。

## 合成夹具

- 对 `evals/fixtures/` 运行 `tests/test_audit_skill_usage.py`，确认 Codex 优先 `event_msg` 并按
  session + timestamp 去重，`response_item` 只作回退。
- 确认 Claude 只有 `Skill` tool_use 且 `input.skill` 非空计为使用，`tengu_skill_loaded` 只进入启动候选计数。
- 确认 JSON 解码失败、目标事件缺字段和正常不匹配事件分别进入 parse、missing、静默跳过三条路径。
- 确认 bridge workspace 会话被排除并计数，报告源路径全部为根下 POSIX 相对路径。
- 分别运行默认脱敏和 `--no-excerpt`，检查邮箱、绝对路径、疑似密钥和结构化原始 session ID 字段不落入报告；相对证据文件名仍保留。
- 传入 hygiene summary，确认只有“历史内未见使用”与 duplicate/overlap finding 的交集进入 `可能冗余`。

## 真实历史只读抽查

- 指向本机默认历史根运行一次完整审计，输出到临时目录；确认覆盖当前、归档 Codex 会话以及 Claude
  projects/telemetry。
- 从 `已用` 中各抽查至少两个 Codex 显式点名和 Claude Skill 工具调用，回到相对文件和行号核对原记录。
- 从 `历史内未见使用` 中抽查至少五个技能，确认结论文字没有写成“从未使用”。
- 从 `疑似漏用` 中抽查至少十条，确认单个技能不超过 5 条，记录规则误报，不因单条候选直接修改技能。
- 检查 `warnings`：候选截断数量、bridge 排除数量、parse/missing 计数与源文件一致。
- 对生成的 JSON 和 Markdown 搜索用户目录、邮箱、URL 查询参数、密钥形态和原始 UUID；发现泄漏即失败。

## 结构与回归

- 运行 `python -m unittest discover -s skill-check/tests -p 'test_*.py' -v`。
- 验证 `evals/evals.json` 为合法 JSON，原有 14 个用例仍存在，新增的超时恢复与最终验收用例 ID 不重复。
- 验证 `evals/trigger-evals.json` 恰有 20 条，正反例各 10 条。
- 用 `skill-creator/scripts/quick_validate.py skill-check` 验证 frontmatter。
- 全部测试通过后才进入跨模型 `review_repair`；审查同步后由原作者重跑相同测试并检查工作区 diff。
