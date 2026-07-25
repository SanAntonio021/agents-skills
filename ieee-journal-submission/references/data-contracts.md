# 数据契约

## 私有作者库

默认路径：`<agents-root>/local-assets/ieee-journal-submission/authors.json`。

顶层字段：

```json
{
  "schema_version": "1.0",
  "updated_at": "YYYY-MM-DD",
  "privacy": {
    "scope": "local-private",
    "forbidden_fields": ["id_card", "phone", "student_id", "staff_id", "password", "biography"]
  },
  "authors": []
}
```

每位作者使用稳定 `profile_id`，并包含：

- `name_zh`、`given_name`、`family_name`；
- `salutation`、`academic_title`；
- `affiliation.institution`、`department`、`city`、`province`、`postal_code`、`country_region`；
- 按 `priority` 排序的 `emails`；
- `orcid`；
- `verification.status`、`source`、`verified_at`。

`salutation` 是投稿页面显示的称谓，`academic_title` 是作者的实际职称。两者都按当前可靠来源和页面选项填写；不能仅为了表示尊重，把非教授作者填写为 `Prof.`。页面选项、作者实际职称或来源不清时保留 `pending`，不要猜填。

字段可写成 `{value, status, source, verified_at}`。状态使用：

- `verified`：有当前可靠来源；
- `user_confirmed`：用户明确提供或确认；
- `pending`：缺失或尚未核验；
- `conflict`：来源冲突，保留候选值；
- `not_applicable`：该字段不适用。

禁止在作者库保存具体稿件角色。`first_author`、`author_order`、`corresponding_author`、`submission_contact` 只允许出现在项目状态。

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

### 具体字段

- `journal`：名称、文章类型及核验状态。
- `manuscript`：题名、稿件编号、submission ID；未知值为 `null` 配合状态。
- `platform`：平台名、稳定入口 URL、当前页面名和 `institution_match_status`；不保存 session 参数。机构状态只用 `matched`、`manually_entered` 或 `not_listed`。
- `lifecycle`：当前阶段、阶段状态、进入时间和证据。
- `decision`：决定原文类型、收到时间和来源；未收到时保持 `null`。
- `revision_round`：初投稿为 0，首轮返修为 1；不要从文件名猜轮次。
- `portal_tasks`：页面任务、当前状态和完成证据，与生命周期阶段分开。当前页面要求的 proof/preview 要记录页面名、是否必需、查看时间和证据。
- `blockers`：冲突、缺件、权限或待用户确认事项；解决后保留历史并标记 closed。
- `authors`：`profile_id`、顺序、具体稿件角色和角色核验状态。
- `files`：使用 `path`、`submission_name`、`purpose`、`size_bytes`、`sha256`、`stage` 和 `upload_status` 保存路径、提交文件名、用途、字节数、SHA256、提交阶段和上传状态。`1.1` 中存在文件记录时这些字段必须完整。可选 `provenance` 保存 `built_at`、`inputs`（每项含 `path`、可选 `size_bytes`、`sha256`）、`freshness_checked_at` 和 `freshness_status`（`verified`、`stale` 或 `unknown`）。没有输入快照时只能使用 `unknown`；`verified` 必须有非空 `inputs` 和 `freshness_checked_at`。新版本追加记录，不覆盖已提交条目。
- `declarations`：页面字段、选择、状态、来源和确认时间。
- `official_sources`：URL、访问日期、关键要求摘要和适用范围。
- `confirmation_gates`：必须单独确认的事项及当前状态。不得重复 action。
- `operation_history`：发生时间、动作、结果、证据和操作者。
- `next_action`：只保留一个当前下一步；并列任务放入阶段清单，不伪装成下一步。

required proof/preview 示例：

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

### 投稿前审查门

`pre_submission_review.status` 只允许：

- `not_run`：尚未审查；
- `blocked`：存在阻断项；
- `pass`：审查通过。

`pass` 必须同时保存 `checked_at` 和非空 `evidence`。`final_submit` 不得在审查门通过前标记为 `confirmed`、`completed`、`closed` 或 `pass`。

`evidence[]` 必须是可定位对象，至少包含非空字符串 `path`、`url`、`record_id` 或 `reference` 之一；`null`、数字、空对象和无法定位的说明文字不能作为 `pass` 证据。`checked_at` 和 `freshness_checked_at` 使用 ISO 日期或时间。

`author_roles`、`declarations`、`reviewers`、`final_submit`、`open_access_fees`、`copyright` 和 `withdrawal_transfer` 进入 `confirmed`、`completed`、`closed` 或 `pass` 时，必须保存非空字符串 `question`、`user_choice`、`applies_to`，并用 `confirmed_at` 保存 ISO 日期或时间。页面已保存或没有报错不等于用户确认。

上述确认门状态只允许 `required`、`pending`、`blocked`、`not_applicable`、`not_required`、`confirmed`、`completed`、`closed` 或 `pass`；`final_submit` 不允许 `not_applicable` 或 `not_required`。不得用 `done` 等未定义同义词绕过关闭检查。

### 1.0 兼容

- 旧 `schema_version: "1.0"` 状态继续可读，校验器输出兼容警告；
- 不原地自动改写旧文件；下次正常更新项目状态时再升级为 `1.1`；
- 旧文件按原有确认门校验，不追溯要求 `pre_submission_review`；
- 未知版本、重复确认门、错误审查门状态和无证据的 `pass` 校验失败。

## 校验

运行：

```powershell
python scripts/validate_submission_records.py --authors <authors.json> --state <submission-state.json>
```

校验器检查敏感字段、作者角色越界、状态值、引用关系、SHA256 和确认门结构。它不判断期刊规则是否仍然有效。
