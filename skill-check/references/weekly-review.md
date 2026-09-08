# 融合本地技能周检

## 目标和边界

周检把三类已有只读审计合并到一个持久队列：

1. `agent-rules/scripts/skill_upstream_maintenance.py weekly-run`：已登记 confirmed 来源的上游变化；
2. `audit_skill_tree.py scan`：目录、命名、重复、链接和坏技能；
3. `audit_skill_usage.py`：Claude/Codex 历史使用、疑似漏用和可能冗余交集。

入口脚本是 `scripts/run_weekly_skill_review.py`。它不复制 transcript，不自动改技能，不替用户批准，
也不替代 `skill-creator` 的候选修改流程。

## 每周入口

定时任务在当前任务中运行：

```powershell
python scripts/run_weekly_skill_review.py scan `
  --date <YYYY-MM-DD> --json
python scripts/run_weekly_skill_review.py next-question --json
```

`scan` 会继续执行其他审计，即使某一项失败。失败项保留错误 finding；相应旧 finding 在该来源没有
新证据时不标记为已解决。上游退出码 `2` 只有在本轮确实写出有效新摘要时才可接受；目录健康和使用
审计的旧摘要不能用来冒充本轮结果。

使用审计中的缺失根、JSON 解析错误、目标事件缺字段或无效健康报告会让本周证据不完整。纯图片或附件
且没有可扫描文本的用户消息单独计数，不会永久阻断连续完整周次；它本来也不可能包含可读取的显式
`$skill-name`、`/skill-name` 或 Skill 链接文本。技能调用或读取证据无法关联到用户请求时也会让本周
证据不完整，避免把不可去重的事件冒充请求次数。

每次 `scan` 固定审计上海时区前一周六 14:00（含）到本周六 14:00（不含）的七天窗口。使用计数
按 `(host, request_id, skill)` 去重，Codex 与 Claude 分列并提供合计。稳定离线页面写入
`<reports-root>/usage/dashboard/index.html`，每周聚合快照写入
`<reports-root>/usage/dashboard/data/<date>.json`；页面内嵌最近 12 周快照，不启动服务、不访问网络，
也不写入提示词片段和来源路径。

上游 `review_required` 先在本周日期目录下执行 `prepare-review`、收益/许可证/测试/风险四门和
`finalize-review`，只在隔离候选副本内完成。候选成为 `awaiting_approval` 后重新运行周检，才会形成
可批准的修改 finding。其他 finding 的候选修改也必须在
`<reports-root>/<date>/execution-candidates/<batch-id>/<finding-id>/` 隔离完成。

## 状态和问答

状态文件固定为 `<reports-root>/weekly-review-state.json`，初始 `schema_version=1`。写入使用跨进程
锁、临时文件和原子替换。损坏 JSON、未知版本、锁冲突或校验失败必须保留原文件并返回严重问题，
不能自动重建或覆盖。

finding ID 由类型、技能和独立修改目的稳定生成。证据、方案、源码基线分别有 fingerprint：

- 三个 fingerprint 都未变：保留原决定，不重复询问；
- 任一 fingerprint 变化：旧批准和相关活动批次失效，重新进入队列；
- `none`/`null` 只表示没有方案 fingerprint，不能当作普通字符串。

`next-question` 永远只返回一项：

- `批准`：记录当前 fingerprint 的批准；
- `不批准`：记录拒绝，不自动删除、归档或降级；
- `解释一下`：只返回证据和建议，不推进队列；
- 其他自然语言：依据语义映射批准、拒绝、调整或事实回答，不要求固定用词。

证据不足的 finding 最多逐条问两次事实。每次回答后重新调用 `next-question`；达到上限后必须关闭、
形成修订建议，或标为 `waiting_evidence`，不能无限追问。纯“历史内未见使用”只有连续四个相邻、完整、
同口径周窗才入队；同一周重跑不累加。该技能本周出现使用会清零；扫描失败、报告无效、周窗不连续、
统计语义升级或该技能的激活宿主范围变化会重置连续计数。一次全局范围 fingerprint 变化不会无差别
清零所有未受影响技能。严重问题可插队，单周最多新增三条中低优先级 finding，但旧队列必须保留。

## 复用批准并执行

所有队列项完成逐条决定后：

```powershell
python scripts/run_weekly_skill_review.py prepare-execution --json
```

只有存在已批准项时才创建批次。`awaiting_confirmation` 是兼容接口状态；当前准确逐项授权已覆盖执行时，由智能体复用该授权继续 `--decision approve`，不再次向用户提问。非 `ask` 的决定必须同时提供 `--batch-id` 和
`--expected-batch-fingerprint`；fingerprint 不匹配时拒绝写入。

实际修改由当前任务在隔离候选副本完成，并遵守：

1. 写入前记录源码树哈希；测试通过后、真正写入前再次核对，发现用户新修改就只退回该项；
2. 文件重叠或显式依赖按批次顺序执行，依赖失败时只暂停依赖项，无依赖项继续；
3. 每个成功目的只精确暂存对应路径，禁止 `git add .` 和 `git add -A`，保留两个仓库现有无关改动；
4. 独立目的独立提交、推送，不把拒绝项或失败项带入提交；
5. Skill 推送后取得最终 40 位远端 SHA，只对实际修改且仍存在的精确 Skill 集合运行
   `Invoke-CcSwitchSkillSync.ps1`，随后用完全相同的 SHA 和 Skill 集合运行 `-VerifyOnly`；两次都必须
   是退出码 `0`、`runtime_active`，`cc_switch_metadata.valid` 为 `true` 且没有元数据问题；数据库完整性、
   仓库分支、技能目录、仓库归属、`repo_branch`、`readme_url` 和双端启用状态均一致，同时源码、
   CC Switch、Claude、Codex 四层文件集合和 SHA-256 一致；
6. 只有满足上一步才可用 `record-execution` 记录 `success`，并提供远端 SHA、`sync_status=verified`
   和完全相同的 `--synced-skill` 集合。

示例：

```powershell
python scripts/run_weekly_skill_review.py record-execution `
  --batch-id <batch-id> --finding-id <finding-id> `
  --expected-proposal-fingerprint <fingerprint> `
  --outcome success --details "tests, commit and two sync checks passed" `
  --remote-sha <40-hex-sha> --sync-status verified --synced-skill <skill-name> --json
```

失败项写入 `retry_pending`；同范围、同输入且已有重试授权时直接记录原授权继续，不再次询问；漂移项只退回该项。helper 身份
变化会使旧批次失效并允许重建确认批次，不会把项目留在无法恢复的等待状态。
helper 身份同时覆盖入口 `Invoke-CcSwitchSkillSync.ps1` 和实际实现模块 `CcSwitchSkillSync.psm1`；只改模块
也必须让旧确认批次失效，不能把未审查的新实现藏在相同入口文件后面。

如果失败发生在源码已提交和推送之后、运行时同步完成之前，重试不能继续沿用修改前的源码 fingerprint，
也不能无条件接受当前目录。只有目标目录无未提交或未跟踪内容、失败记录中的独立提交确实改过目标、
该提交与记录的远端 SHA 都在当前 HEAD 祖先链上，而且目标从该提交到当前 HEAD 没有再变化时，才把
重试源码基线推进到已提交结果。任一条件不满足都返回源码漂移阻断，保留原状态等待新证据。

## 自动任务对话协议

自动任务只把 `next-question` 的一项问题交给用户。用户回复后，任务调用 `record-decision`，再调用
`next-question`；`explain` 不推进队列，调整意见先让旧方案和批次失效，展示修订方案后再问批准。
如果调整意见出现在最终执行确认阶段，先定位它涉及的 finding，再用该 finding 的当前 fingerprint 调用
`record-decision --classification adjust`，不能把调整意见当作批次批准。
全部决定完成后，已有准确执行授权直接使用，不追加最终执行确认。无批准项时只输出：

```text
本周没有需要决定的修改。
```

不要把完整周报作为用户必须阅读的交付物；默认给出离线 dashboard 的稳定路径，报告路径只作为证据
引用保留在状态和最终摘要中。

内部 fingerprint 用于发现变化。变化后重新核实当前内容、工具来源和授权范围；若实质动作未变，可依据原准确授权重建批次，不向用户要求粘贴哈希。

## 本地维护范围、定向发现与能力复核

公开根默认沿用 `--skills-root`，私有根默认读取 `--agents-root/private-skills`（存在才启用），也可用
`--private-skills-root` 显式指定。只盘点这些自建源码根下真实 `SKILL.md`，不进入已安装第三方套件。
公开、私有上游与目录检查分别运行；私有登记默认是 `--agents-root/upstream/private-skill-sources.toml`，
可用 `--private-registry` 改向。私有上游的状态和报告写到 `<reports-root>/private/`，镜像登记复用
当前项目的 `upstream/repo-mirrors.toml`。缺私有登记会报告受阻，公开检查仍继续；不推测来源补登记。

研究任务的身份是 `public:<name>` / `private:<name>`，同名也不合并。旧公开 finding ID 和决定保持兼容；
新增私有 finding 使用独立身份，先作为人工事实复核，不把私有目标送入公开源码的执行批次。私有候选
仍在私有源码、登记及隔离工作区中按既有流程审核发布，材料不得复制进公开技能仓库。

`scan` 同时返回 `discovery`，并把相同内容写入本轮 `weekly-review.json`。它包括维护清单、
`research_tasks`（本周可研究的问题）、`admitted_skills`、限额、顺延任务和已有研究结论。
状态复用 `weekly-review-state.json` 的可选 `discovery` 字段，旧 schema 1 和历史决定不重建。

定向研究只接受明确用户反馈、评测缺口、来源待查，优先级依次降低；低频或零调用不触发。
同一上海日期所属的周六至下周五共享最多三个技能的额度，每技能最多深入比较两个独立仓库/路径候选；
同周重跑不重置额度，未入选的问题持久顺延。来源登记为 `none` 可以正常保留；若其含义只是尚无已确认
来源，而且确有待查依据，使用显式 `source_unknown` 输入，不能把全部 `none` 技能强制送去找源。

脚本只安排和记录研究，不自行联网。当前任务按 `web-access` 研究 `research_tasks`；实际深入比较也须
遵守返回限额，不能先超额研究再只登记两个。作者归属、仓库路径、版本与许可证需分别核实；转载相同文本
不能证明原作者身份。研究产物只是待审核来源与收益证据，不自动登记上游、改源码或推进接受基线。

先把明确触发依据保存为过程目录中的 UTF-8 JSON，再导入：

```json
{
  "schema_version": 1,
  "triggers": [
    {
      "skill_key": "private:pdf",
      "trigger": "source_unknown",
      "purpose": "resolve-provenance",
      "evidence": "本地说明提到参考来源，但尚未核实准确仓库路径、版本和许可证。"
    }
  ]
}
```

```powershell
python scripts/run_weekly_skill_review.py scan --date <YYYY-MM-DD> --discovery-input <input.json> --json
```

从 `discovery.research_tasks` 取真实 `id` 与 `evidence_fingerprint`，完成研究后按原值回填。下例的候选
字段均必填；`revision` 和 `license` 尚未核实时明确写 `未核实`，不能省略并暗示已核实。`source_evidence`
说明作者与来源证据，`upstream_improvement`、`local_gap`、`expected_benefit`、`conflicts` 分别写具体改进、
本地缺口、预期收益及兼容冲突，不只写“值得吸收”。

```json
{
  "schema_version": 1,
  "results": [
    {
      "task_id": "从 research_tasks 复制的 id",
      "expected_evidence_fingerprint": "从该任务复制的 evidence_fingerprint",
      "outcome": "candidates",
      "evidence": "说明本轮比较方法，并引用实际研究记录。",
      "candidates": [
        {
          "repo_url": "https://example.invalid/owner/repo",
          "upstream_path": "skills/example",
          "revision": "未核实",
          "license": "未核实",
          "source_evidence": "实际仓库或作者页面及证据位置；此示例地址不可当作真实来源。",
          "upstream_improvement": "新增前提检查及回答后的假设更新。",
          "local_gap": "本地目前缺少对应检查。",
          "expected_benefit": "发现表面问题与真实目标之间的偏差。",
          "conflicts": "保留本地显式调用边界，避免变成固定问卷。"
        }
      ]
    }
  ]
}
```

```powershell
python scripts/run_weekly_skill_review.py scan --date <同轮日期> --reuse-reports --discovery-input <results.json> --json
```

没有值得吸收的内容时用 `outcome: "no_benefit"`；联网、访问或证据受阻时用 `outcome: "blocked"`。
这两类保留 `task_id`、`expected_evidence_fingerprint`、具体 `evidence`，省略 `candidates` 或给空列表。
同一问题、同一触发证据不再重复研究；新事实或明确恢复依据作为同一 `skill_key/trigger/purpose` 的新
`evidence` 输入，旧结果进入历史，再按本周额度重开。输入无效或超限不写入部分研究状态，其他审计仍继续。

本地能力复核比较每个维护技能的内容指纹，排除工具缓存和自动生成的来源页。首次无可核验接受指纹时只建
观察快照，不声称已通过语义审核。此后内容变化且登记曾包含已吸收能力时，生成 `local_capability_review`
事实复核项：人工比较正文、触发条件、完成路径和必要评测。有意删除更新登记说明；疑似退化先评测，不自动
补回。上游扫描失败保留上次已吸收内容，不把空报告解释为能力消失。

研究候选和本地复核复用 `next-question` 逐项入口。已有授权足以完成只读语义复核时，由当前任务记录真实
证据，不让用户代读代码。确认无需修改可复用既有事实关闭接口：

```powershell
python scripts/run_weekly_skill_review.py record-decision --finding-id <finding-id> `
  --expected-evidence-fingerprint <本项当前值> --expected-proposal-fingerprint none `
  --classification auto --facts-outcome close --answer "具体人工核对结论和评测证据；无需修改。" --json
```

未问清用 `--facts-outcome wait` 并记录缺少的证据。需要修改则进入既有来源确认、隔离候选和逐项批准流程，
不能把人工复核项直接解释成批准修改。关闭或等待状态遇到相同证据不重问，证据变化才重新排队。
