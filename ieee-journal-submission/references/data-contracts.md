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

## 项目状态

默认路径：`<project-root>/outputs/submission/submission-state.json`。

最小结构：

```json
{
  "schema_version": "1.0",
  "journal": {},
  "manuscript": {},
  "platform": {},
  "lifecycle": {"current_stage": "preparation"},
  "decision": {"type": null, "status": "not_received"},
  "revision_round": 0,
  "portal_tasks": [],
  "blockers": [],
  "authors": [],
  "files": [],
  "declarations": {},
  "official_sources": [],
  "confirmation_gates": [],
  "operation_history": [],
  "next_action": {}
}
```

### 具体字段

- `journal`：名称、文章类型及核验状态。
- `manuscript`：题名、稿件编号、submission ID；未知值为 `null` 配合状态。
- `platform`：平台名、稳定入口 URL、当前页面名；不保存 session 参数。
- `lifecycle`：当前阶段、阶段状态、进入时间和证据。
- `decision`：决定原文类型、收到时间和来源；未收到时保持 `null`。
- `revision_round`：初投稿为 0，首轮返修为 1；不要从文件名猜轮次。
- `portal_tasks`：页面任务、当前状态和完成证据，与生命周期阶段分开。
- `blockers`：冲突、缺件、权限或待用户确认事项；解决后保留历史并标记 closed。
- `authors`：`profile_id`、顺序、具体稿件角色和角色核验状态。
- `files`：路径、提交文件名、用途、字节数、SHA256、提交阶段和上传状态。可选 `provenance` 保存 `built_at`、`inputs`（每项含 `path`、可选 `size_bytes`、`sha256`）、`freshness_checked_at` 和 `freshness_status`（`verified`、`stale` 或 `unknown`）；没有 `inputs` 时只能使用 `unknown`，新版本追加记录，不覆盖已提交条目。
- `declarations`：页面字段、选择、状态、来源和确认时间。
- `official_sources`：URL、访问日期、关键要求摘要和适用范围。
- `confirmation_gates`：必须单独确认的事项及当前状态。
- `operation_history`：发生时间、动作、结果、证据和操作者。
- `next_action`：只保留一个当前下一步；并列任务放入阶段清单，不伪装成下一步。

## 校验

运行：

```powershell
python scripts/validate_submission_records.py --authors <authors.json> --state <submission-state.json>
```

校验器检查敏感字段、作者角色越界、状态值、引用关系、SHA256 和确认门结构。它不判断期刊规则是否仍然有效。
