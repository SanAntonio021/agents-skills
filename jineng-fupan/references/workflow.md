# Skill Retro Review Workflow

## Inputs

- 项目根目录：`D:/BaiduSyncdisk`
- 报告目录：`D:/BaiduSyncdisk/.agents/reports/skill-improver`
- 本周日期：`YYYY-MM-DD`
- transcript 根目录：默认 `C:/Users/SanAn/.codex`

## Discovery Rules

1. 按给定日期计算“本周”窗口，默认取该日期所在周的周一到当天。
2. 从 `C:/Users/SanAn/.codex/sessions/<YYYY>/<MM>/<DD>/` 读取本周每天新建的 `.jsonl`。
3. 额外检查 `C:/Users/SanAn/.codex/archived_sessions/*.jsonl`，只保留 `session_meta.timestamp` 落在本周窗口内的记录。
4. 每个候选 session 必须满足：
   - 首行是 `session_meta`
   - `session_meta.cwd` 能映射回 `D:/BaiduSyncdisk` 下某个项目
   - 如果 `cwd` 位于 `.codex/worktrees/*/<repo-name>`，则优先归一回 `D:/BaiduSyncdisk/<repo-name>`
5. 候选最小单位是 `project_root + session_path`，不是 thread 标题，也不是人工摘要。

## Index Rules

索引文件位于 `index.json`，每个条目至少包含：

- `run_key`
- `project_root`
- `project_slug`
- `session_path`
- `session_id`
- `session_slug`
- `started_at`
- `cwd`
- `thread_name`
- `analysis_status`
- `action_status`
- `signature`
- `signal_summary`
- `last_analyzed_at`
- `last_reminded_at`
- `report_path`

## Signature Rules

签名至少覆盖：

- session `.jsonl` 文件本身

每个文件记录：

- 绝对路径
- 是否存在
- 文件大小
- 最后修改时间
- `sha256`

只有签名变化时，该 session 才重新进入分析队列。

## Report Writing Rules

### 项目级单 session 报告

路径：
`projects/<project-slug>/<date>/<session-slug>.md`

必须包含这些章节：
1. 项目路径
2. session 路径 / session_id / 开始时间 / cwd / thread
3. 关键信号
4. 这周反复出现的问题
5. 下周最容易再出问题的地方
6. 哪些改法值得采纳
7. 哪些事情先继续观察
8. 证据路径

### 项目周报

路径：
`projects/<project-slug>/<date>/summary.md`

建议包含：

- 本周新增或变化的 session
- 未处理遗留项
- 本项目重复模式

### 跨项目观察报告

路径：
`cross-project/<date>.md`

只读取项目摘要，不跨项目混读原始 transcript。

建议包含：

- 本周重复出现的 `pattern_key`
- 涉及项目列表
- 共享改进候选
- 仅建议，不自动修改 skill

### 每周总览

路径：
`weekly/<date>.md`

必须单列：

- `本周新增/变化对话`
- `未处理遗留项`
- `跨项目观察`
- `执行说明`

## Finalization Rules

分析完成后执行：

```powershell
python scripts/retro_scan.py finalize --reports-root D:/BaiduSyncdisk/.agents/reports/skill-improver --date <YYYY-MM-DD>
```

作用：

- 将本周分析队列标记为 `analyzed`
- 为已分析项设置 `action_status = pending_review`
- 为遗留提醒项更新 `last_reminded_at`

## Action Status Rules

支持状态：

- `pending_review`
- `reviewed`
- `adopted`
- `dismissed`

只有 `pending_review` 会在后续周报里继续提醒。

## Guardrails

- 不自动修改技能文件。
- 不把多个项目的原始 transcript 拼成一份统一分析。
- 不因为同名目录就认定是同一项目；始终以归一化后的 `project_root` 判断。
