# 自建技能上游维护

本机制只追踪外部仓库中的上游 `skill`。论文、普通官方文档和模板仍按各业务技能的来源规则管理。

## 分层

- `<agents-root>/upstream/repo-mirrors.toml`：上游仓库镜像配置。
- `<agents-root>/upstream/skill-sources.toml`：全部已纳入源仓库的自建技能与已确认上游 `skill` 的机器可读关系。
- `<agents-root>/skills/<name>/references/upstream-sources.md`：给人查看的单技能来源说明，由集中登记表生成。
- `<agents-root>/reports/skill-upstream/`：周检报告、隔离候选、测试结果和审核状态；该目录不进入 Git。

上游镜像保持 `zero exposure`：不进入 Codex、Claude 或 CC Switch 的技能目录，不直接覆盖本地技能。

## 首次来源调查

1. 顶层目录有 `SKILL.md` 才算一个自建技能。
2. 先查本地来源说明、Git 历史和已有镜像，再查公开一手仓库。
3. 本地文件明确写明“已吸收”“fork”“本地落点”时，才可登记为 `confirmed`。
4. 只有功能相似、没有吸收证据的来源写进审查报告，状态是候选；候选至少记录仓库 URL、仓内路径、提交或 tag、许可证、吸收证据、已吸收内容和不吸收边界。用户逐来源确认前不进入正式来源关系。
5. 没有确认来源的技能也必须登记，状态为 `none`。
6. 首次调查完成后，不再周期性寻找新来源；周检只处理已确认来源。

## 周检

首次登记或手工修改登记表后，先校验并重新生成单技能来源页：

```powershell
python <script> render `
  --registry <agents-root>/upstream/skill-sources.toml `
  --mirrors-registry <agents-root>/upstream/repo-mirrors.toml `
  --skills-root <agents-root>/skills --json

python <script> validate `
  --registry <agents-root>/upstream/skill-sources.toml `
  --mirrors-registry <agents-root>/upstream/repo-mirrors.toml `
  --skills-root <agents-root>/skills --require-rendered --json
```

每周用一个命令刷新镜像并生成报告：

```powershell
python <script> weekly-run `
  --registry <agents-root>/upstream/skill-sources.toml `
  --mirrors-registry <agents-root>/upstream/repo-mirrors.toml `
  --skills-root <agents-root>/skills `
  --reports-root <agents-root>/reports/skill-upstream `
  --date <YYYY-MM-DD> --json
```

`<script>` 是 `<agents-root>/skills/agent-rules/scripts/skill_upstream_maintenance.py`。

镜像单仓库总预算 20 秒，最多 4 路并行。一个镜像失败不能阻塞其他镜像；批次仍写完整 JSON，但进程返回非零，确保自动化发出异常提醒。异常按 `source` 隔离：某个来源受阻时，只阻塞该来源；同一本地技能关联的其他健康来源仍继续检查和收益评估。

“只报告”只表示不擅自清理镜像、改权限、改来源身份或生成不可信候选，不表示只给状态名。每个异常来源必须在 `summary.json` 和 `summary.md` 中说明：

- 具体问题和原始错误
- 对本次检查与候选更新的影响
- 按顺序执行的修复步骤
- 自动化已经采取的隔离动作
- 下一步是否需要用户批准，以及批准范围

脏镜像、非快进历史、许可证变化、上游路径删除或基线不可用时，不生成候选。许可证始终相对 `accepted_commit` 检查，不能用已审核提交跳过。只读诊断、网络重试和新建 zero-exposure 镜像可以直接执行；清理用户修改、强制重置、改 Windows ACL、修改 origin/branch、迁移接受基线或确认新上游路径前必须取得用户批准。

上游路径移动经 Git 历史确认后，用 `upstream_path` 记录当前路径，用 `accepted_upstream_path` 保留 `accepted_commit` 当时的路径，并登记 `path_migration_commit` 和 `path_migration_evidence`。校验器必须确认接受提交是迁移提交的祖先、当前镜像包含迁移提交，且迁移前后的技能目录 tree 相同。路径确认只修正来源身份；`accepted_commit` 保持不变，迁移后真正发生的内容变化仍进入收益评估。以后本地真正吸收新提交时，同时把 `accepted_upstream_path` 更新到该接受提交对应的路径。

周检还会查找既有 `review-context.json`。当 `candidate_status` 为 `awaiting_approval`，且技能、来源、`accepted_commit` 和当前上游提交完全一致时，来源状态显示为 `awaiting_approval` 并给出审核目录，不重复显示 `review_required`。这一步只恢复待批准提醒，不更新 `accepted_commit` 或 `last_reviewed_commit`；真正应用前仍执行候选时效、证据哈希和目标技能状态检查。

## 候选审核门

`review_required` 只说明跟踪文件变了，不说明变化值得吸收。

1. 用 `prepare-review` 创建隔离的旧版和候选版副本。
2. 阅读上游差异，判断是否改善功能、可靠性、兼容性或输出质量。
3. 按 `skill-creator` 运行旧版/候选版对比评测和回归测试；没有现成 `evals` 时，在隔离目录补 2 至 3 个真实用例。
4. 新增联网、凭据、依赖、批量文件写入或自动提交行为时，直接进入风险复核。
5. 只有可证明收益、关键测试无回归且许可证允许时，才标为等待批准。
6. 用户按技能逐项批准前，不修改本地源码，不更新 `accepted_commit`。

创建隔离审核目录：

```powershell
python <script> prepare-review `
  --registry <agents-root>/upstream/skill-sources.toml `
  --mirrors-registry <agents-root>/upstream/repo-mirrors.toml `
  --skills-root <agents-root>/skills `
  --reports-root <agents-root>/reports/skill-upstream `
  --date <YYYY-MM-DD> --skill <skill-name> --source <source-id> `
  --expected-commit <weekly-report-commit> --json
```

只在隔离目录的 `candidate_skill/` 修改候选。完成 `benefit-assessment.md` 和 `test-report.md` 后，锁定候选补丁及审核证据：

```powershell
python <script> finalize-review `
  --registry <agents-root>/upstream/skill-sources.toml `
  --mirrors-registry <agents-root>/upstream/repo-mirrors.toml `
  --skills-root <agents-root>/skills `
  --workspace <review-workspace> --skill <skill-name> --source <source-id> `
  --benefit-confirmed --tests-passed --license-ok --risk-reviewed --json
```

如果旧版快照、候选、上游差异、收益判断或测试报告在定稿后变化，批准自动失效。

## 批准后

1. 重新检查目标技能是否变脏、候选上游提交是否变化、隔离副本哈希是否仍匹配。
2. 用户明确批准一个技能后，应用该技能候选：

```powershell
python <script> apply-review `
  --registry <agents-root>/upstream/skill-sources.toml `
  --mirrors-registry <agents-root>/upstream/repo-mirrors.toml `
  --skills-root <agents-root>/skills `
  --workspace <review-workspace> --skill <skill-name> --source <source-id> `
  --confirm-approved --approval-note "<本次逐项批准原文>" --json
```

3. 应用后状态是 `applied_pending_retest`；重新运行完整测试。测试失败时不更新接受基线，不提交。
4. 测试通过后才更新集中登记表的 `accepted_commit` 和 `last_review_date`，重新生成并校验单技能来源说明。
5. 只暂存本次相关文件；`agents-skills` 和 `agents-config` 分别提交、分别推送。
6. 推送成功后提醒用户通过 CC Switch 点击“检查更新”；不自动操作 CC Switch。

## 记录已审核提交

拒绝或无影响的提交需要记录，避免每周重复提醒：

```powershell
python <script> record-review --state <reports-root>/state.json `
  --source <source-id> --commit <sha> --accepted-baseline <accepted-sha> `
  --disposition rejected --confirm-reviewed
```

`accepted_commit` 表示已实际吸收到本地技能的上游基线；`last_reviewed_commit` 表示已经判断过的上游提交，两者不能混用。

## 每周自动化任务

自动化每周六 14:00（Asia/Shanghai）运行。任务必须先读全局规则、`agent-rules`、`skill-creator` 和 `web-access`，再执行 `weekly-run`。它可以准备隔离候选和测试，但不得自行批准、应用、提交或推送。提醒中给出摘要、异常和本地报告路径。
