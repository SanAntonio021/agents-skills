---
name: lab-report-slides
description: >
  Generate a concise Chinese lab-work presentation from the user's Codex and Claude Code sessions.
  Use this skill whenever the user says "生成今日汇报", "生成当天汇报", "生成每日汇报",
  "生成本周组会汇报", "生成组会 PPT", or asks to turn recent AI-assisted experiments,
  code, instrument tests, plots, or results into a presentation. Read local session JSONL,
  merge child-agent work into parent tasks, filter AI boilerplate, find referenced experiment
  images, check whether the work is worth presenting to an advisor, require a short outline
  approval, and export HTML, PDF, and image-only PPTX.
  Do not use for paper-to-slides work when the source is a paper PDF or DOI; use a paper-slide skill.
compatibility: Requires Python 3.10+, `python-pptx`, and Microsoft Edge or Google Chrome for headless HTML rendering.
---

# Lab Report Slides

Use this skill for the user's recurring daily report and weekly group-meeting workflow. The
teacher needs a clear record of work and evidence, not a transcript of AI conversation. Treat
the local session files as evidence; never treat model planning, speculation, or boilerplate as
completed work.

## Trigger and mode

- `生成今日汇报`, `生成当天汇报`, or `生成每日汇报`: collect the local calendar day in
  `Asia/Shanghai`.
- `生成本周组会汇报` or `生成组会汇报`: collect the most recent seven calendar days ending
  on the requested local date.
- If the user names a project, keep only matching `cwd`/project records and assets. Otherwise,
  include all projects found in the selected window and show project names in the outline.

## Data collection

Run the bundled collector. It uses only the local files and Python standard library:

```text
python scripts/collect_sessions.py --mode today --out <brief.json>
python scripts/collect_sessions.py --mode week --out <brief.json>
```

Default sources:

- Codex: `%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl` plus archived rollouts whose
  `session_index.jsonl` entry was updated inside the selected window. The collector matches
  archive filenames by session ID and does not stat the whole archive. Use `--no-include-archived`
  only when the user explicitly wants to exclude archived sessions.
- Claude Code: `%USERPROFILE%\.claude\projects\**\*.jsonl`.

The collector converts event timestamps to `Asia/Shanghai`, so a session started yesterday but
continued today is included. It records `sessionId`, `cwd`, `parent_thread_id`, `root_id`, and
platform. Merge records with the same `root_id`; child-agent sessions are supporting evidence,
not separate work items.

The collector keeps user messages and useful assistant results, excludes system/developer
prompts, hidden reasoning, token telemetry, and tool plumbing, and redacts obvious API keys,
tokens, passwords, and secrets. Do not print raw session JSONL in the chat or put it into the
generated deck.

## Evidence and noise rules

Summarize only work that has evidence in the selected records or files:

- `已完成`: a command, test, experiment, file, or result is explicitly present.
- `进行中`: work is active but no final result is recorded.
- `遇到问题`: a failure or unresolved discrepancy is explicitly recorded.
- `下一步`: an action clearly proposed by the user or grounded in the evidence.

Strip greetings, repeated acknowledgements, generic AI advice, speculative claims, and invented
terminology. Do not turn an AI plan into a result. Keep numbers, units, instrument names, test
conditions, filenames, and error messages exact. When evidence is incomplete, write `未验证` or
`待确认`; never fill the gap from general knowledge.

Reconcile status before outlining. Later evidence has priority over an earlier intermediate
finding. An explicit current statement from the user that an item is complete may override an
earlier audit that listed open issues. Use that statement only for status; do not invent missing
technical details. Remove resolved issues from `遇到问题` and `下一步`.

Prefer this content order:

1. What changed or was completed.
2. What the experiment or test showed.
3. What problem was located or remains unresolved.
4. What will be done next.

Show code only when the code itself is the research result. Otherwise report the task, method,
and observed result rather than copying code blocks.

## Report-worthiness check

Before proposing an outline, decide whether the selected work is useful to the intended advisor
or group-meeting audience. A high message count is not evidence of progress. Prefer, in order:

1. Verified research results, experiment data, plots, or quantitative test findings.
2. Completed research or project deliverables that matter to the intended advisor, with a
   traceable file or review result.
3. Supporting work that directly unblocked current research and has a verified outcome.

Routine login fixes, AI configuration, disk cleanup, general software maintenance, and meta-skill
work usually belong in a private work log. Routine administrative forms also stay out unless they
represent a material project milestone for this audience. Before counting an item, ask whether the
advisor needs it to understand current research progress. Include supporting work only when the
user asks or when it directly affected the reported milestone. Do not pad a deck with these tasks
to make the day look busy.

If the day contains no first- or second-priority result and only routine supporting work remains,
stop before the outline. Tell the user plainly that the available record lacks substantive
advisor-facing progress, and ask one question: stop, or create a private work log instead.

## Outline checkpoint

After the report-worthiness check passes, produce a short outline in the chat. The outline must
contain no more than five slide titles and one or two evidence bullets per slide. Use these default
roles as needed:

1. 总览
2. 主要工作
3. 实验/测试结果
4. 问题与判断
5. 下一步

Remove empty roles and compress to two or three slides on a light day. Ask the user to confirm or
correct the outline. Do not render the final files until the user confirms.

## Experiment assets

The collector first uses image and chart files explicitly referenced in the selected session
events. If that produces no useful asset, it scans the selected project directories for images
modified inside the same date window. Skip `.git`, `.venv`, `node_modules`, `.codex`, and `.claude`.
The fallback is capped at 5 seconds and 2,000 files by default, so a synced drive cannot stall a
daily report. Pass a narrower project scope when a result image is important.

Use the following priority:

1. A result image or chart directly referenced by the experiment conversation.
2. A result image created or modified in the selected window under the matching project.
3. No image, with a clear text statement that the result image was not found.

Never insert an old or unrelated image merely to fill a blank area. Keep the file path in the
manifest so the user can trace each inserted asset.

Ignore icons, logos, and other assets found under agent runtime or skill directories. They are
interface resources, not experimental evidence, unless the user explicitly identifies one as a
result image.

## Deck JSON and rendering

After outline approval, write a small deck JSON file outside the skill directory. The renderer
expects this shape:

```json
{
  "title": "今日工作汇报",
  "date": "20260715",
  "footer": "2026-07-15",
  "slides": [
    {
      "kicker": "实验进展",
      "title": "1 km 光纤链路引入低频噪声峰",
      "status": "已完成",
      "blocks": [
        {"type": "text", "heading": "观察", "text": "..."},
        {"type": "image", "path": "D:\\path\\spectrum.png", "caption": "频谱仪 CH2"}
      ]
    }
  ]
}
```

Render with:

```text
python scripts/render_deck.py --deck <deck.json> --output-dir "D:\\BaiduSyncdisk\\组会" --base-name <YYYYMMDD-or-YYYYMMDD组会>
```

The renderer creates:

- `<name>.html`: self-contained HTML source.
- `<name>.pdf`: one slide per page.
- `<name>.pptx`: each slide is a full-slide PNG, preserving visual layout.
- `<name>_01.png`, `<name>_02.png`, ...: the rendered slide images.
- `<name>.manifest.json`: output paths, slide count, and provenance.

Use `D:\\BaiduSyncdisk\\组会\\20260506.pptx` as the visual reference: 16:9, white background,
等线/Microsoft YaHei fallback, blue heading accents, experiment images, and a restrained amount
of text. Do not copy the 42 MB template into the skill. The current style profile is recorded in
`references/template-profile.json`.

File naming:

- Daily: `YYYYMMDD`.
- Weekly group meeting: `YYYYMMDD组会`.
- If the requested stem already exists, preserve it and use `_v2`, `_v3`, and so on. Never
  overwrite an earlier deck automatically.

## Verification

Before reporting success:

1. Confirm HTML, PDF, PPTX, PNG, and manifest files exist and are non-empty.
2. Confirm the PPTX is a valid ZIP/Office package and has the expected number of slides.
3. Confirm every PNG is 1600x900 and every referenced image either renders or is marked
   `[MISSING: ...]`.
4. Check that no slide exceeds five slides for a daily report, that text is readable at 16:9,
   and that no placeholder or unsupported claim remains.
5. Report the exact output paths and any `未验证` items.

Do not launch or close PowerPoint through COM merely to validate an image-only deck. If a PowerPoint
instance is already open, use the generated PDF/PNG files and package-level checks instead.
