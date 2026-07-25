# 数据契约

## 私有作者库

权威路径：`<agents-root>/local-assets/ieee-journal-submission/authors.json`。

作者库继续使用 `schema_version: "1.0"`，不因项目状态升级而迁移。每位作者使用稳定
`profile_id`，保存姓名、称谓、职称、单位、部门、城市、省份、邮编、国家/地区、按优先级排序的
邮箱、ORCID、核验状态、来源和核验日期。

禁止保存具体稿件角色和敏感信息。`first_author`、`author_order`、`corresponding_author`、
`submission_contact` 只允许出现在项目状态；身份证号、手机号、学号、工号、密码、cookie、token
和个人经历不得保存。

## 项目状态 1.1

默认路径：`<project-root>/outputs/submission/submission-state.json`。

最小结构：

```json
{
  "schema_version": "1.1",
  "journal": {},
  "manuscript": {},
  "platform": {
    "name": null,
    "institution_match_status": null,
    "current_page": null
  },
  "lifecycle": {"current_stage": "preparation"},
  "decision": {"type": null, "status": "not_received"},
  "revision_round": 0,
  "portal_tasks": [],
  "blockers": [],
  "authors": [],
  "files": [],
  "declarations": {},
  "official_sources": [],
  "confirmation_gates": [
    {"action": "pre_submission_review", "status": "not_run"},
    {"action": "author_roles", "status": "required"},
    {"action": "declarations", "status": "required"},
    {"action": "reviewers", "status": "required"},
    {"action": "final_submit", "status": "required"},
    {"action": "open_access_fees", "status": "required"},
    {"action": "copyright", "status": "required"},
    {"action": "withdrawal_transfer", "status": "required"}
  ],
  "operation_history": [],
  "next_action": {}
}
```

### pre_submission_review

只允许：

- `not_run`：未执行；
- `blocked`：存在阻断项或关键维度无法核验；
- `pass`：通过。

`pass` 必须同时保存检查时间和非空证据：

```json
{
  "action": "pre_submission_review",
  "status": "pass",
  "checked_at": "2026-07-26T15:30:00+08:00",
  "evidence": [
    {
      "type": "paper_review_report",
      "path": "outputs/reviews/pre-submission-review.md",
      "summary": "Nine-dimension precheck passed; no open blockers."
    }
  ]
}
```

无检查时间或无证据的 `pass` 无效。最终提交门不得在审查门不是 `pass` 时关闭。

`author_roles`、`declarations`、`reviewers`、`final_submit`、`open_access_fees`、`copyright` 和 `withdrawal_transfer` 进入 `confirmed`、`completed`、`closed` 或 `pass` 时，必须保存非空字符串 `question`、`user_choice`、`applies_to`，并用 `confirmed_at` 保存 ISO 日期或时间。页面已保存或没有报错不等于用户确认。

上述确认门状态只允许 `required`、`pending`、`blocked`、`not_applicable`、`not_required`、`confirmed`、`completed`、`closed` 或 `pass`；`final_submit` 不允许 `not_applicable` 或 `not_required`。不得用 `done` 等未定义同义词绕过关闭检查。

### 1.0 兼容

- 旧 `submission-state.json` 的 `schema_version: "1.0"` 继续可读；
- 校验器给出兼容警告，不要求旧文件已有 `pre_submission_review`；
- 不自动改写旧文件；下次正常更新项目状态时才升级到 `1.1`；
- 未知版本直接报错。

### 平台状态

`platform.institution_match_status` 在页面涉及机构时使用：

- `matched`：从平台规范机构库选中；
- `manually_entered`：平台正式允许自由文本并已填写；
- `not_listed`：使用平台提供的 not listed 路径。

页面要求的 proof/preview 状态记录在 `portal_tasks`，包括页面名、是否必需、查看时间和证据。
没有该步骤时记录 `not_present`，不能伪造已查看。

```json
{
  "task_type": "proof",
  "page": "Final Review",
  "required": true,
  "status": "viewed",
  "viewed_at": "2026-07-26T15:45:00+08:00",
  "evidence": [{"path": "outputs/submission/final-review-proof.pdf"}]
}
```

关闭 `final_submit` 时，所有 `required: true` 页面任务必须为 `completed`、`verified` 或 `viewed`；required proof/preview 还必须有查看时间和可定位证据。`blockers` 中每项必须为 `closed` 或 `resolved`。

### 文件与新鲜度

`files[]` 使用 `path`、`submission_name`、`purpose`、`size_bytes`、`sha256`、`stage` 和 `upload_status` 保存路径、提交文件名、用途、大小、SHA-256、阶段和上传状态。`1.1` 中只要存在文件记录，这些字段就必须完整。可选 `provenance`：

```json
{
  "built_at": "2026-07-26T14:00:00+08:00",
  "inputs": [
    {"path": "main.tex", "size_bytes": 12345, "sha256": "64-hex"}
  ],
  "freshness_checked_at": "2026-07-26T14:10:00+08:00",
  "freshness_status": "verified"
}
```

`freshness_status` 只允许 `verified`、`stale`、`unknown`。没有输入快照时只能使用 `unknown`；
`verified` 必须有非空输入快照和检查时间。

审查门 `evidence[]` 必须是可定位对象，至少包含非空字符串 `path`、`url`、`record_id` 或 `reference` 之一；`null`、数字、空对象和只有说明文字但无法定位的记录不能作为 `pass` 证据。`checked_at` 和 `freshness_checked_at` 使用 ISO 日期或时间。

## 校验

```powershell
python scripts/validate_submission_records.py --authors <authors.json> --state <submission-state.json>
```

校验器检查版本、敏感字段、作者角色越界、状态值、确认门、SHA-256 和文件新鲜度结构。它不判断期刊规则是否仍然有效。
