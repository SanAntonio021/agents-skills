# Claude–Codex Bridge v3 集成验收

## 请求与路径

- 两个方向都用共享 `/mcp` 调用 `v3_review_peer`；必填真实绝对 `projectRoot`、task、author、target、
  model，`artifactPath/artifactContent/context` 可选；验收可省或为空，类型默认 deliverable。
- file 同时传路径与正文时，磁盘主文件仍为依据；message 可传正文/上下文或只有任务，不建文件，
  不生成主文件哈希、不调用 checkpoint 和终审，不默认改走 v2。不传文件白名单、sandbox 或工具列表。
- 路径穿越、绝对 artifactPath、目录、不存在文件、同族 author/target 和任何额外字段都在创建 job
  前拒绝。
- Claude CLI 与 Codex App Server 都以真实项目为 cwd；项目规则、技能、插件、MCP、网络和完整工具可用，
  首轮可直接修改真实项目。精确模型回执缺失或不匹配时失败。

## 权限

- 两端使用模拟工具调用验证批量、递归、目录、项目外或远程删除、Git 丢弃修改和数据库清空不再产生
  桥接器审批记录或进入 `awaiting_approval`；不在真实数据上执行破坏动作。
- 执行模型仍核对任务授权、实际目标和恢复依据；超范围由执行模型询问，无效认证、路径错误及终审写入仍拒绝。
- 历史审批记录可读、类型和 `v3_resolve_approval` 兼容；旧接口逐字匹配 job、approval ID、fingerprint
  和有序完整 targets，批准 24 小时有效。拒绝或超时取消动作，不自动批准旧待审批动作。

## 自由回复、文件阶段与完整性

- 中文、Markdown、代码块、缺字段 JSON、额外结果字段均保留完整 responseText，主模型处理
  interpretationRequired，不触发格式修复模型请求或审批。交互成功不等于审查通过，不凭关键词补造 pass。
- message 单轮终态；即使自由回复提出修改意见也不补建文件或追加文件终审流程。

- 首轮 peer 可修改，完成后进入 `awaiting_author`。
- 作者重读并调用 `v3_author_checkpoint`。未修改时不再调用模型；修改后只发一次 `final_check`。
- final_check 修改主文件时失败。终审后不追加审查阶段或新 series。覆盖主模型自行修正小问题并验证、
  用证据不采纳技术意见、目标或范围重要取舍交给用户三类收尾。验证失败保留失败，不强行宣布完成。
- 分别报告对端结论和主模型修正及验证结果；主模型改后旧结论失效，不冒充最新文件已获对端通过。
- 每次结果查询都重算主文件 SHA-256；后续变化使 `stale=true`、`conclusion_valid=false`。

## 稳定性与记录

- 502/503/504/524 的整轮失败在同一 job、会话、模型和项目中额外重试一次；第二次失败即终止。
- 同一真实项目串行，不同项目可并行；旧任务等待审批仍占项目锁。
- 会话贯穿本轮和内部重试，旧任务还包括历史审批，终态发布前删除；daemon 重启清理已记录的临时 session。
- 长期记录可含清理后的完整最终回复，包括正文、代码和修订稿；新输入
  task/acceptanceCriteria/constraints/artifactContent/context 只保存 inputMetadata，完整 prompt、
  transcript、原始工具参数与输出不长期留存，旧记录原样保留。
- 密码、API key、token、Cookie、session、私钥、认证头和设备登录值在输入、结果、错误及审批目标中
  脱敏。
- 保留非秘密 session/token 技术字段、路径、公式和代码；长普通字段和最终回复无静默截断，
  总请求或输出超限时明确失败。

## 兼容

- v1/v2 现有工具、schema、路由和结果保持回归通过。
- 明确使用旧协议时，v2 inline 仍要求 artifactContent、字节数和哈希，并保持 zero-tool。
- v3 失败不得静默回退 v2，不得扩大旧协议执行能力。
- 新 v3 使用独立 schema 4；旧 schema 3 文件哈希在读取、展示和显式迁移前后不变，新版不恢复旧活动
  job 或自动批准旧动作。用户明确的历史 resolve 可精确写入 schema 4 决策，不恢复执行。迁移写新存储；
  回滚旧版不读写 schema 4。发布前等待旧活动任务按原语义结束。

## 科研分支

- 显式科研监督或里程碑互审进入科研分支；普通科研、单次仿真和论文润色不触发，单次互审不扩成循环。
- 兼容执行任务跟踪原 task job；落盘里程碑复用 v3 job/series、checkpoint、终审和主模型收尾。
- 已授权里程碑对端通过且结论有效，或主模型收尾验证满足物理判据后继续；两种结果分开报告。
  未满足判据只暂停依赖步骤，目标、范围或重要取舍再询问用户；旧审批拒绝单个动作仍继续原 job。
- 区分 Mock、仿真、离线和实测；核对单位、物理判据、复现资料、独立验证与相关因果反例。
