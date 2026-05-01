# chat-notes eval analysis

## Scope

This iteration only targets the new external-skill comparison requirements added to `chat-notes`.

Tested evals:

- `id 6`: user only points to `chat-notes`; the expected behavior is a review draft, no file edits, with local and external similar-skill comparison.
- `id 8`: Windows voice input / Shandianshuo / Volcengine Doubao ASR experience; the expected behavior is a review draft that decides where the experience should be captured and includes external skill metrics.

Configurations:

- `new_skill`: current working tree version of `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\SKILL.md`
- `old_skill`: snapshot from `HEAD:chat-notes/SKILL.md`

## Result

| Eval | New skill | Old skill | Main difference |
| --- | ---: | ---: | --- |
| 6 | 10/10 | 9/10 | Old skill did not require the complete external metrics fields. |
| 8 | 10/10 | 3/10 | Old skill skipped external search and did not produce the required external candidate table. |

Aggregate pass rate:

- New skill: 100%
- Old skill: 60%
- Delta: +40 percentage points

## Interpretation

The new `chat-notes` rules are doing useful work. They make the model:

- keep the response in review-draft mode;
- compare local similar skills;
- search or report external similar skills;
- present external candidates with source, link, GitHub stars, download/install metric, fit, and conclusion;
- avoid inventing unavailable metrics.

The strongest differentiator is eval `id 8`, because it matches the real conversation: Windows voice input, Shandianshuo, Volcengine Doubao ASR, user dictionary, restart verification, and token safety.

## Residual risk

The external metrics themselves still depend on live web/search availability. The skill now correctly says to write `未查到` or `未提供` when a metric is unavailable, but it cannot guarantee every external marketplace exposes weekly downloads.

Timing/token metrics were not available from the subagent notifications in this environment, so the benchmark uses output character count as the token-like comparison field.
