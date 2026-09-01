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

## 融合周检状态机

- 连续四个不同日期写入同范围、完整且未见使用的合成 usage 摘要，确认前三次不入队、第四次才形成 finding；
  使用证据、扫描失败、无效报告或范围变化分别清零。
- 先保存三条旧中低优先级问题和已回答 finding，再合并新结果；确认旧问题保留、稳定 fingerprint 不重复问、
  新严重问题插队、每周最多新增三条中低优先级问题。
- 对证据不足 finding 逐条回答事实，确认最多两问，并覆盖关闭、形成建议、等待新证据三个出口。
- 对待确认或执行中 finding 提交调整意见，确认旧批准和批次失效、修订方案重新展示，未重新批准前不能执行。
- 全部逐项决定后重复调用 `prepare-execution`，确认只返回同一批次；没有批准项时不创建空批次。
- 在写入决定前替换 evidence/proposal fingerprint，确认返回 stale 且状态文件字节不变；并发持锁、损坏 JSON
  和未知 schema 均保留原文件并返回严重问题。
- 构造三个执行项：一个失败、一个显式依赖它、一个独立。确认失败项进入下周重试，依赖项暂停，独立项继续；
  修改源码树或同步 helper 后，确认只阻止受影响批次或项目。
- `record-execution success` 对需同步项必须拒绝短 SHA、非 `verified` 状态和不精确 Skill 集合。

## 结构与回归

- 运行 `python -m unittest discover -s skill-check/tests -p 'test_*.py' -v`。
- 验证 `evals/evals.json` 为合法 JSON，22 个用例 ID 唯一，新增融合周检、超时恢复、阻塞弹窗、
  合法本机文件、CC Switch 元数据与最终验收用例都存在。
- 验证 `evals/trigger-evals.json` 恰有 24 条，正反例各 12 条。
- 用 `skill-creator/scripts/quick_validate.py skill-check` 验证 frontmatter。
- 只有尚待用户确认的正式计划才进入跨模型 `review_repair`；已确认计划的实施完成后不自动追加互审，原作者仍需重跑全部测试并检查工作区 diff。
