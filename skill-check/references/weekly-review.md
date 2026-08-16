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
`$skill-name`、`/skill-name` 或 Skill 链接文本。

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
- 其他自然语言：按调整意见或事实回答处理。

证据不足的 finding 最多逐条问两次事实。每次回答后重新调用 `next-question`；达到上限后必须关闭、
形成修订建议，或标为 `waiting_evidence`，不能无限追问。纯“历史内未见使用”只有连续四次完整周检
才入队；使用证据、扫描失败、范围变化或报告无效会把连续次数清零。严重问题可插队，单周最多新增三条
中低优先级 finding，但旧队列必须保留。

## 最终确认和执行

所有队列项完成逐条决定后：

```powershell
python scripts/run_weekly_skill_review.py prepare-execution --json
```

只有存在已批准项时才创建 `awaiting_confirmation` 批次。重复读取同一批次会返回相同的一次确认，
而不是创建第二个批次。非 `ask` 的决定必须同时提供 `--batch-id` 和
`--expected-batch-fingerprint`；fingerprint 不匹配时拒绝写入。

实际修改由当前任务在隔离候选副本完成，并遵守：

1. 写入前记录源码树哈希；测试通过后、真正写入前再次核对，发现用户新修改就只退回该项；
2. 文件重叠或显式依赖按批次顺序执行，依赖失败时只暂停依赖项，无依赖项继续；
3. 每个成功目的只精确暂存对应路径，禁止 `git add .` 和 `git add -A`，保留两个仓库现有无关改动；
4. 独立目的独立提交、推送，不把拒绝项或失败项带入提交；
5. Skill 推送后取得最终 40 位远端 SHA，只对实际修改且仍存在的精确 Skill 集合运行
   `Invoke-CcSwitchSkillSync.ps1`，随后用完全相同的 SHA 和 Skill 集合运行 `-VerifyOnly`；两次都必须
   是退出码 `0`、`runtime_active`，且源码、CC Switch、Claude、Codex 四层文件集合和 SHA-256 一致；
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

失败项写入 `retry_pending` 并在下一轮优先询问“是否按相同输入重试”；漂移项只退回该项。helper 身份
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
全部问题完成后只问一次最终执行确认。无批准项时只输出：

```text
本周没有需要决定的修改。
```

不要把完整周报作为用户必须阅读的交付物；报告路径只作为证据引用保留在状态和最终摘要中。
