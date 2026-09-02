# 自建技能上游维护

本机制只追踪外部仓库中的上游 `skill`。论文、普通官方文档和模板仍按各业务技能的来源规则管理。

## 分层

- `<agents-root>/upstream/repo-mirrors.toml`：上游仓库镜像配置。
- `<agents-root>/upstream/skill-sources.toml`：全部已纳入源仓库的自建技能与已确认上游 `skill` 的机器可读关系。
- `<agents-root>/skills/<name>/references/upstream-sources.md`：给人查看的单技能来源说明，由集中登记表生成。
- `<agents-root>/reports/skill-upstream/`：周检报告、隔离候选、测试结果和审核状态；该目录不进入 Git。

上游镜像保持 `zero exposure`：不进入 Codex、Claude 或 CC Switch 的技能目录，不直接覆盖本地技能。

镜像配置提供 `git_dir_path` 时，该路径必须是绝对路径、跨镜像唯一，并位于同步盘和所有技能源码/运行时目录之外。`validate`、`report`、候选准备和镜像管理器复用同一套登记表安全校验，避免某个入口接受不安全路径。每次检查和同步都用 `git rev-parse --absolute-git-dir` 核对 Git 实际使用的元数据目录；声明值与实际值不一致时停止刷新并报告两条路径。旧镜像可暂时不提供该字段并继续原地使用；但镜像工作树一旦缺失，`check` 和 `sync` 都返回 `blocked_missing_git_dir`，必须先配置外置 Git 元数据路径。迁移旧镜像现有 `.git` 仍需用户批准。

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

全局来源登记存在覆盖缺口，但只需处理一个已登记技能时，给 `render` 和 `validate` 增加
`--skill <skill-name>`。定向模式仍严格检查目标技能、来源、镜像、许可证和生成页；其他本地技能
尚未登记不会阻断该目标的批准后闭环。

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

`weekly-run` 每次先写 `preflight-validation.json`。登记表或镜像表存在结构性错误时，保存预检错误并阻止镜像刷新；
只有“本地技能尚未登记”这类覆盖缺口时，继续刷新镜像和检查全部既有 confirmed 来源，完整写出
`mirror-results.json`、`summary.json` 和 `summary.md`，但命令返回非零。摘要必须列出未覆盖技能、影响、
隔离动作和补登记步骤，不能把已登记来源的结果冒充为全部本地技能均已检查。

镜像单仓库总预算 20 秒，最多 4 路并行。Windows 上超时会终止本次命令创建的完整 Git 子进程树，避免 `git-remote-https` 继续占用网络或让超时失效。现有镜像只执行一次远端 `fetch`，随后在本地检查并执行 `merge --ff-only`，避免 `pull` 再次联网；非快进更新仍直接阻止。现有镜像遇到明确的 Windows Schannel 兼容错误时在同一预算内切换 OpenSSL；遇到 TLS 提前关闭或连接重置时，在剩余预算内自动重试一次。新镜像的 `git clone` 不在同一路径盲目重试，避免第一次失败留下部分目录后覆盖原始错误。跟踪路径的 `git diff` 超时或失败时返回 `tracked_diff_failed`，保留前后提交和原始错误，不得静默记为“无变化”。一个镜像失败不能阻塞其他镜像；批次仍写完整 JSON，但进程返回非零，确保自动化发出异常提醒。异常按 `source` 隔离：某个来源受阻时，只阻塞该来源；同一本地技能关联的其他健康来源仍继续检查和收益评估。

新镜像的完整克隆连续触发仓库预算时，换用新的工作树和外置 Git 元数据路径。使用 `git clone --filter=blob:none --depth 1 --no-checkout --branch <branch> --single-branch --separate-git-dir=<git_dir_path> <repo_url> <local_path>` 初始化，再用 `git sparse-checkout` 检出 `tracked_paths` 和 `license_paths`。更新登记前，依次核对 origin、branch、HEAD、`git rev-parse --absolute-git-dir`、浅层与稀疏配置、跟踪文件和干净工作树；任何一项偏离登记值时保留现场并报告。

百度网盘备份期间，镜像工作树可能短暂出现 `*.baiduyun.uploading.cfg`。当它是唯一脏项时，先等待备份完成，再复查临时文件和 `git status --porcelain`。临时文件消失且工作树恢复干净后继续周检；文件持续存在或同时出现其他改动时，按脏镜像报告并保留现场。

登记镜像即使尚未被正式 `skill source` 引用，刷新失败也必须进入周检摘要，写明原始错误、影响和修复步骤；这类镜像单独计数，不伪造技能来源，也不改变正式来源总数。

镜像管理器若在登记表加载、进程启动、JSON 输出或总超时阶段整体失败，周检必须保存顶层原始错误，把缺失的逐镜像结果标记为 `mirror_manager_failed`，并阻止这些来源形成“无更新”或新候选结论。

网络异常必须写明实际访问目标，例如 `https://github.com/<owner>/<repo>.git`，不能只写“GitHub”或“网络失败”。单次 TLS 握手超时只证明该次连接没有按时完成，不能据此判断 VPN 不可用。归因前，应对同一目标执行有次数上限的 `curl.exe -I` 或 `git ls-remote` 复测，并区分 DNS 解析、TCP 连接、TLS 握手和 HTTP/Git 响应所处的失败阶段；复测仍失败时再按证据提出代理、DNS、远端服务或本机 TLS 配置等可能原因。

“只报告”只表示不擅自清理镜像、改权限、改来源身份或生成不可信候选，不表示只给状态名。每个异常来源必须在 `summary.json` 和 `summary.md` 中说明：

- 具体问题和原始错误
- 对本次检查与候选更新的影响
- 按顺序执行的修复步骤
- 自动化已经采取的隔离动作
- 下一步是否需要用户批准，以及批准范围

脏镜像、非快进历史、许可证变化、上游路径删除或基线不可用时，不生成候选。许可证始终相对 `accepted_commit` 检查，不能用已审核提交跳过。只读诊断、网络重试和新建 zero-exposure 镜像可以直接执行；清理用户修改、强制重置、改 Windows ACL、修改 origin/branch、迁移接受基线或确认新上游路径前必须取得用户批准。

上游路径移动经 Git 历史确认后，用 `upstream_path` 记录当前路径，用 `accepted_upstream_path` 保留 `accepted_commit` 当时的路径，并登记 `path_migration_commit` 和 `path_migration_evidence`。校验器必须确认接受提交是迁移提交的祖先、当前镜像包含迁移提交，且迁移前后的技能目录 tree 相同。路径确认只修正来源身份；`accepted_commit` 保持不变，迁移后真正发生的内容变化仍进入收益评估。以后本地真正吸收新提交时，同时把 `accepted_upstream_path` 更新到该接受提交对应的路径。

当一个来源需要从仓库根同时跟踪运行时、启动器和技能子目录时，`upstream_path = "."` 保留仓库根范围，并用仓库相对的 `skill_entry_path` 明确真正的 `SKILL.md`。校验、差异和候选准备必须分别使用入口路径与跟踪范围，不能假定仓库根一定存在 `SKILL.md`。未登记 `skill_entry_path` 时，仍按 `<upstream_path>/SKILL.md` 处理，保持现有来源兼容。

没有许可证或书面授权、但必须保留历史吸收证据的来源，可经用户逐技能批准后登记 `update_policy = "provenance_only"`。这种来源继续记录仓库、历史路径、接受提交和最近观测提交，但永不生成更新候选、跳过许可证变化吸收，也不推进 `accepted_commit`。校验器仍要求接受提交及其历史技能入口存在；如果上游在后续提交中删除该路径，当前 HEAD 不再要求保留入口。它不是许可证授权；以后只有取得一手授权并再次批准修改策略，才可恢复普通更新审核。

如果上游把原有行为拆到新建的 `sections/`、`references/` 或脚本目录，必须把该目录补进 `tracked_paths`。新路径可以在 `accepted_commit` 时不存在，但必须存在于当前 HEAD；差异中按新增文件进入收益评估。这样不会因只跟踪入口 `SKILL.md` 而漏掉外置行为变化。

周检还会查找既有 `review-context.json`。当 `candidate_status` 为 `awaiting_approval`，且技能、来源、`accepted_commit` 和当前上游提交完全一致时，来源状态显示为 `awaiting_approval` 并给出审核目录，不重复显示 `review_required`。这一步只恢复待批准提醒，不更新 `accepted_commit` 或 `last_reviewed_commit`；真正应用前仍执行候选时效、证据哈希和目标技能状态检查。

## 候选审核门

`review_required` 只说明跟踪文件变了，不说明变化值得吸收。

隔离候选不是新安装的技能，也不是正式技能的替代品；它是从当前正式本地技能复制出的可选升级草稿，只用于对照审查。候选处于 `awaiting_approval` 时，正式本地技能仍保持原样并可继续使用。针对性对比评测只衡量本次拟议行为；旧版在这些用例上得分较低，只说明它没有覆盖这些拟议行为，不能证明旧技能整体失效或不可用。

同一本地技能若同时有多个来源产生有益变化，批准前必须合成一个技能级候选。候选从同一正式技能快照出发，合并各来源改动，解决重叠文件、评测 ID 和规则冲突，再运行组合回归测试。`review-context.json` 用 `additional_sources` 记录其余来源的接受基线、路径身份和当前提交；定稿恢复、周检和应用前校验必须覆盖全部来源。用户只批准这个合并后的本地技能候选，不对同一技能重复批准。

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
  --expected-commit <weekly-report-commit> `
  --additional-source <other-source-id> <other-weekly-report-commit> --json
```

`--additional-source` 可重复；没有其他来源时省略。命令会为每个来源重新检查接受基线、当前 HEAD、许可证和跟踪路径，并生成各自的上游差异证据。同一技能已有完整且仍有效的待批准候选时，不再创建第二个候选。

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
定稿还会锁定完整来源范围和四个审核门；删除 `additional_sources`、清空必需证据哈希，或任一来源的 HEAD、接受基线、许可证状态发生变化，整个技能级候选一并失效，不能降级成单来源候选继续批准。

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
4. 测试通过后运行 `complete-review`，一次推进该技能候选涉及的全部来源：

```powershell
python <script> complete-review `
  --registry <agents-root>/upstream/skill-sources.toml `
  --mirrors-registry <agents-root>/upstream/repo-mirrors.toml `
  --skills-root <agents-root>/skills `
  --workspace <review-workspace> --skill <skill-name> --source <source-id> `
  --date <YYYY-MM-DD> --confirm-retest-passed `
  --accepted-version <source-id> <version> --json
```

`--accepted-version` 可按来源重复，也可省略并保留已有版本。命令只接受
`applied_pending_retest` 状态；先确认正式技能仍与已应用候选一致、候选证据未变、全部来源 HEAD 与接受基线仍有效，
再通过恢复日志保护的可恢复事务更新集中登记、定向生成来源页并把上下文标为 `completed`。路径迁移已经随新基线完成时，删除冗余的
`accepted_upstream_path`、`path_migration_commit` 和 `path_migration_evidence`；加载时仍由当前 `upstream_path`
推导接受路径。每次写入前保存三个文件的旧快照；普通写入失败会立即恢复，进程中断则在下次重跑时先恢复。
恢复失败时保留 `complete-review-transaction.json` 和原始错误，禁止继续推进。对同一完成状态重复运行会复核完整来源身份与生成页，只做一致性检查并返回
`already_completed`，不重复写入。

5. `complete-review` 不提交、不推送，也不修改无关脏文件。测试失败、目标技能偏离候选、来源过期或登记源范围不完整时，
保持 `applied_pending_retest` 和旧接受基线，先修复或重新审核。
6. 只暂存本次相关文件；`agents-skills` 和 `agents-config` 分别提交、分别推送。
7. Skill 推送成功后取得 40 位远端提交 SHA，调用
   `D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1`，只传本次提交
   实际修改且仍存在的 Skill。该 helper 使用固定版本、固定哈希的隐藏命令行程序，先创建 CC Switch 数据库
   备份，再按准确名称更新或首次安装目标，并显式启用 Claude 和 Codex；不打开、查找、显示或激活 CC Switch
   桌面窗口，不建 watcher 或计划任务，也不提供“全部更新”。后台程序通过 CC Switch 服务层更新数据库登记、
   公共 Skill 副本和已启用运行目录，这种受控写入属于正式更新流程；仍禁止任务自行执行 SQL、手工复制运行时
   文件、替换 CC Switch EXE 或直接改配置。明确的临时下载、连接或数据库占用错误只在单条后台命令内部重试
   一次；其他错误直接停止，不切换到 UI Automation、鼠标或前台窗口。
8. 只有 helper 返回退出码 `0`、状态 `runtime_active`，且提交源码、`.cc-switch`、`.claude`、`.codex`
   四层全部目标文件集合和 SHA-256 完全一致，且 CC Switch 数据库完整性、仓库分支、目录归属和双端启用状态
   通过核验，才算运行时生效。`updated_background`、`installed_background` 或单条命令退出成功不能替代这个
   结论。后台更新或验收失败时，不重复完整 helper、不直接修运行时，只能报告“源码已推送，运行时未生效”，
   并保留 JSON 错误码和差异证据。删除或合并 Skill 产生的运行时残留不走该 helper，仍需单独批准清理。

## 记录已审核提交

拒绝或无影响的提交需要记录，避免每周重复提醒：

```powershell
python <script> record-review --state <reports-root>/state.json `
  --source <source-id> --commit <sha> --accepted-baseline <accepted-sha> `
  --disposition rejected --confirm-reviewed
```

`accepted_commit` 表示已实际吸收到本地技能的上游基线；`last_reviewed_commit` 表示已经判断过的上游提交，两者不能混用。

## 每周自动化任务

自动化每周六 14:00（Asia/Shanghai）回到同一个用户任务运行，不再保留职责重叠的独立上游周报任务。
统一入口是 `skill-check/scripts/run_weekly_skill_review.py scan`；它会调用这里的 `weekly-run`，再合并目录健康、
历史使用和疑似漏用结果。完整队列、状态和一次一问协议见
`../../skill-check/references/weekly-review.md`。

任务必须先读全局规则、`skill-check`、`agent-rules`、`skill-creator` 和 `web-access`。它可以在日期报告
目录中准备、评估和测试隔离候选，但用户逐项批准以及最终执行确认前，不得应用、提交、推送或同步。
每次只展示一项问题；用户不需要阅读完整周报，报告路径只保留为可核验证据。
