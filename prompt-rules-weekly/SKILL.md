---
name: prompt-rules-weekly
description: 每周核验 `prompt_guidelines` 下 Anthropic、Google、OpenAI 的官方 prompt 与 agent guidance，必要时更新三份参考文档，并只把真正影响 AI 运行时行为的长期原则同步到 `AGENTS.md`、`GEMINI.md`、`CLAUDE.md`。Use when the user asks to run the weekly prompt-rules review, maintain global prompt rules, or create and report the related Codex automation; use official sources only.
---

# 全局规则周检

## 作用

这个 skill 负责维护 `<agents-root>\prompt_guidelines` 这一层长期参考基线。

它每周主要做四件事：

1. 核验官方来源有没有出现稳定变化
2. 必要时更新 `anthropic.md`、`google.md`、`openai.md`
3. 只把真正影响 AI 运行时行为的长期原则写入三份全局规则文件的 `<vendor_principles>`
4. 生成一份周报

## 固定输入

- `<agents-root>\prompt_guidelines\sources.yml`
- `<agents-root>\prompt_guidelines\anthropic.md`
- `<agents-root>\prompt_guidelines\google.md`
- `<agents-root>\prompt_guidelines\openai.md`
- `<agents-root>\CLAUDE.md`
- `<agents-root>\GEMINI.md`
- `<agents-root>\AGENTS.md`
- `<agents-root>\prompt_rule\` 只读索引层

## 四层分工

1. 参考层：
   - `anthropic.md`
   - `google.md`
   - `openai.md`
2. 目标层：
   - `CLAUDE.md`
   - `GEMINI.md`
   - `AGENTS.md`
3. 本地索引层：
   - `prompt_rule/`
4. 控制层：
   - `sources.yml`

不要混层。参考层写“人怎么写 prompt 更稳”，目标层写“AI 在运行时应该怎么做”。

## 流程

1. 先确认 `Asia/Shanghai` 当天日期，格式固定为 `YYYY-MM-DD`。
2. 读 `sources.yml`，确认本周只核验登记过的官方来源。
3. 先区分本周变化属于哪一层：
   - 只影响参考层
   - 影响运行时长期原则
   - 只属于本地索引，不该进主文件
4. 只访问官方来源。
5. 必要时更新三份参考文档，但保持它们的固定结构不变。
6. 写入三份全局规则文件前，先生成备份。
7. 自动写入时，只允许改 `<vendor_principles> ... </vendor_principles>`。
8. 最后在 `<agents-root>\prompt_guidelines\` 下按 `weekly-YYYY-MM-DD.md` 的格式生成周报。

## 周报要求

周报至少要回答：

- 本周核验了哪些官方来源
- 三家厂商各自有什么稳定结论或变化
- 三份参考文档是否更新
- 三份全局规则文件里实际写入了什么运行时原则
- 哪些变化被刻意排除，因为它们只是 prompt 写法建议或本地索引
- 本周如果没有实质变化，也要明确写“本周无实质更新”

周报模板：

- [references/report-template.md](references/report-template.md)

## 边界

- 只用官方来源，不用第三方提示词网站做直接依据。
- 不把参考文档写成官方文档摘抄集。
- 不把产品说明、版本口径、短期 UI 变化写进长期规则。
- 不单独维护 Codex 独立参考层，Codex 相关长期规则并入 `openai.md`。
- 不改 `<vendor_principles>` 之外的内容。
- 不改 `prompt_rule/` 目录。

## 相关文件

- 执行基线：`<agents-root>\workflows\update-prompts.md`
- 周报模板：[references/report-template.md](references/report-template.md)

## 维护

- 来源列表变化时，优先改 `sources.yml`。
- 主文件骨架变化时，要同步更新 `sources.yml`、workflow 和周报模板中的相关约定。
- 周检是本地编排层，不替代官方文档本身。
