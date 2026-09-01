# 历史使用审计

## 目的与边界

这项审计回答三个不同问题：

1. 哪些技能存在可核验的实际使用证据；
2. 哪些技能在所扫描历史内没有看到使用证据；
3. 哪些用户请求与技能 `name` / `description` 相符，但该条记录没有对应调用证据。

它不是实时监控器，也不证明 Codex 的全部隐式路由是否发生。扫描结果只能描述当前可访问的历史范围；历史被
删除、轮转、未落盘或来自其他客户端时，`历史内未见使用` 不能外推成“从未使用”。

周检使用固定左闭右开窗口：前一周六 14:00（含）到本周六 14:00（不含），时区为
`Asia/Shanghai`。计数单位固定为用户请求；去重键为 `(host, request_id, skill)`，因此同一请求内
重复点名、重复调用或同时存在多种证据都只计一次。

## 数据源

默认历史根：

| 根代号 | 默认位置 | 用途 |
| --- | --- | --- |
| `codex-sessions` | `~/.codex/sessions` | 当前 Codex 会话历史 |
| `codex-archived` | `~/.codex/archived_sessions` | 已归档 Codex 会话历史 |
| `claude-projects` | `~/.claude/projects` | Claude Code 项目会话历史 |
| `claude-telemetry` | `~/.claude/telemetry` | Claude 启动时候选加载信号 |

默认技能根包括源码、Codex 运行时、Claude 运行时、lark 实体层和 Codex 插件缓存。报告按规范化
`name:` 合并同一技能的多个位置，同时保留每个位置的根代号、相对路径和适用宿主。

每类根都可用对应参数重复指定。指定某一类自定义根后，该类默认根被覆盖，便于在脱敏 fixture 或限定
历史上复现：

```powershell
python scripts/audit_skill_usage.py `
  --reports-root D:\AuditReports `
  --date 2026-08-15 `
  --window-start 2026-08-08T14:00:00+08:00 `
  --window-end 2026-08-15T14:00:00+08:00 `
  --timezone Asia/Shanghai `
  --skills-root D:\BaiduSyncdisk\.agents\skills `
  --codex-sessions-root C:\Users\SanAn\.codex\sessions `
  --codex-sessions-root C:\Users\SanAn\.codex\archived_sessions `
  --claude-projects-root C:\Users\SanAn\.claude\projects `
  --claude-telemetry-root C:\Users\SanAn\.claude\telemetry
```

## 证据判定

### Claude 实际调用

只有同时满足以下条件才计为 `已用`：

- 顶层记录 `type == "assistant"`；
- `message.content[]` 元素 `type == "tool_use"`；
- `name == "Skill"`；
- `input.skill` 是非空字符串。

工具调用通过 `parentUuid` 向上关联最近一条含用户编写文本的用户记录；中间的 `tool_result` 虽然也以
`type=user` 保存，但只是传输记录，不会被当成新请求。这样可以避免把已经正确调用的同一请求标成疑似漏用。
关联失败时进入 `warnings.unmapped_requests`，不计为使用，也不据此压制其他请求的候选。相同用户祖先
下对同一技能的多次 Skill 工具调用合并为一次请求触发。

### Claude 启动候选

`event_data.event_name == "tengu_skill_loaded"` 只表示 Claude 在启动时加载了候选技能信息。该信号单独
计数，绝不进入 `已用`。这样可以避免“每次启动都加载”被误读为“每次都调用”。

### Codex 显式点名与观察到的技能读取

Codex 历史中的真实用户消息按以下优先级读取：

- 优先 `event_msg` + `payload.type == "item_completed"` + `item.type == "UserMessage"`；
- 其次 `event_msg` + `payload.type == "user_message"`；
- `response_item` + `payload.type == "message"` + `role == "user"` 只作回退；
- 同一 session + `turn_id` 的重复用户记录只保留优先级最高者。

只把 `$skill-name`、独立 `/skill-name` 或指向 `skills/<name>/SKILL.md` 的链接计为显式点名。普通文本
提到某个主题不算实际调用。此外，`item_completed` 中执行成功、明确读取已登记技能 `SKILL.md` 且能
关联到 `turn_id` 的 `CommandExecution`，计为观察到的技能读取。失败命令和无法关联请求的读取不计数。
同一请求的显式点名与读取合并为一个触发，同时在 `evidence_kinds` 保留证据构成。Codex 目前仍没有
覆盖全部隐式 Skill 路由的稳定事件，因此报告固定保留 `codex_implicit_usage_not_captured=true`。

## 分类

- `已用`：至少一个去重后的用户请求存在 Claude Skill 工具调用、Codex 用户显式点名或 Codex 技能读取证据。
- `历史内未见使用`：扫描范围内没有上述证据；不等于实际从未使用。
- `疑似漏用`：用户文本命中技能名或 `description` 的低频确定性词组，但该条记录未见对应调用证据。
- `可能冗余`：仅当传入 `--hygiene-summary` 时，历史内未见使用的技能又出现在 duplicate/overlap
  finding 中。该标签只要求人工复核。

疑似漏用默认最多保留 50 条，且单个技能最多占 5 条，避免一个长技能名淹没其他候选；使用
`--max-candidates` 调整总上限。最终列表先为每个技能保留一条，再进入下一轮，优先覆盖不同技能。
description 规则要命中两个独立词组或一个六字高区分度词组，技能名完整出现则作为强候选。
筛选不调用语言模型，候选可能包含误报；
人工复核时应看原始记录上下文、技能边界和当时宿主能力，不能直接据此改触发条件。

## 容错与隐私

三种 JSONL 记录分别处理：

- JSON 解码失败：进入 `warnings.parse_errors`；
- 目标事件缺必需字段：进入 `warnings.missing_fields`；
- 技能调用或读取无法关联用户请求：进入 `warnings.unmapped_requests`，不计数；
- 纯图片或附件、没有可扫描文本的 Codex 用户消息：进入 `warnings.non_text_user_records`，单独计数，
  不作为文本字段缺失；
- 合法但与目标事件无关：静默跳过。

详细警告最多各保留 200 条，同时保留总数和是否截断。bridge 固定审查副本通过 cwd/path 标记排除，并
在 `bridge_copy_excluded_count` 中报告数量，避免审查提示词污染用户使用统计。

默认报告片段执行以下处理后截到 240 字符：折叠空白，替换 URL、邮箱、Windows 绝对路径、疑似密钥和
长十六进制标识。`--no-excerpt` 会完全省略片段字段。无论是否保留片段，证据源都只写根代号、根下
POSIX 相对路径和行号；结构化 `session_ref` 只保存不可逆短哈希。用于回到原始证据的相对文件名可能
沿用宿主自己的 session 命名，这是定位来源所必需的信息，不另行复制为 session ID 字段。

## 报告与复核顺序

读取：

1. `usage/manifests/<date>/summary.json` 的 `warnings`，先确认扫描缺口和解析错误；
2. `已用` 与 `历史内未见使用`，了解证据覆盖；
3. `疑似漏用`，回到对应相对路径和行号人工核验；
4. `可能冗余`，再结合技能目标、输入、输出和触发场景判断是否需要 `skill-creator`。

融合周检会把聚合结果写入 `usage/dashboard/data/<date>.json`，并生成稳定入口
`usage/dashboard/index.html`。页面只内嵌最近 12 周的技能名、宿主、聚合请求计数、连续零周数、状态、
证据类型和覆盖警告；不得包含提示词片段、session 来源或绝对路径。任何自动修改、归档、删除、合并、
降级点名、daemon、常驻页面服务或网络请求都超出本审计边界。
