# `prompt-rules-weekly` 周报模板

每次执行 `prompt-rules-weekly` 时，周报默认保持简洁，风格接近 `anthropic.md`、`google.md`、`openai.md`，不要写成冗长审计报告。

至少包含以下 4 个章节：

## 1. 本周核验来源

- 本周日期
- 本周核验的官方来源列表

## 2. 本周稳定结论

- Anthropic 的稳定结论或变化
- Google 的稳定结论或变化
- OpenAI / Codex 的稳定结论或变化

## 3. 本周写入结果

- 先直接写：
  - 3份参考文档：`未改动` / `已改动`
  - 3份全局规则：`未改动` / `已改动`
  - `prompt_rule/`：`未改动`
  - 实际改动文件
- 然后只保留：
  - `参考层` 一句话：哪些变化只更新了 `prompt_guidelines/`
  - `运行时层` 一句话：哪些变化进入了 `CLAUDE.md`、`GEMINI.md`、`AGENTS.md` 的 `<vendor_principles>`
  - `排除项` 一句话：哪些内容被刻意排除，因为它们只是 prompt 写法建议或本地索引
  - `CLAUDE.md`、`GEMINI.md`、`AGENTS.md` 各一句话改动摘要
  - 边界一句话：是否确认只改了 `<vendor_principles>`
- 允许出现“参考层已改、全局规则未改”这一正常结果
- 不再重复逐条展开“未改动文件”

## 4. 本周不改什么

- 明确写出本周刻意不动的部分
- 只列下周仍值得继续观察的点
