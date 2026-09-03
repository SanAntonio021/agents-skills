# Claude–Codex Bridge v3 集成验收

## 请求与路径

- 两个方向都用共享 `/mcp` 调用 `v3_review_peer`，只传真实绝对 `projectRoot` 和相对
  `artifactPath`，不传正文、文件白名单、sandbox 或工具列表。
- 路径穿越、绝对 artifactPath、目录、不存在文件、同族 author/target 和任何额外字段都在创建 job
  前拒绝。
- Claude CLI 与 Codex App Server 都以真实项目为 cwd；项目规则、技能、插件、MCP、网络和完整工具可用，
  首轮可直接修改真实项目。精确模型回执缺失或不匹配时失败。

## 权限

- 项目内单个普通文件删除自动允许。
- 多目标、递归、通配符、目录、项目外或远程删除，Git 丢弃修改和数据库清空进入
  `awaiting_approval`。
- 解析 Bash、apply_patch、MCP 和原生 App Server 审批事件；只有显式可见的动作纳入保证。
- `v3_resolve_approval` 必须逐字匹配 job、approval ID、fingerprint 和有序完整 targets；24 小时过期，
  拒绝或超时取消动作。

## 三阶段与完整性

- 首轮 peer 可修改，完成后进入 `awaiting_author`。
- 作者重读并调用 `v3_author_checkpoint`。未修改时直接进入用户门；修改后只发一次 `final_check`。
- final_check 修改主文件时失败。终审的 pass、needs_changes 和 disagreement 都交给用户。
- 每次结果查询都重算主文件 SHA-256；后续变化使 `stale=true`、`conclusion_valid=false`。

## 稳定性与记录

- 502/503/504/524 的整轮失败在同一 job、会话、模型和项目中额外重试一次；第二次失败即终止。
- 同一真实项目串行，不同项目可并行；等待审批仍占项目锁。
- 会话贯穿本轮、内部重试和审批，终态发布前删除；daemon 重启清理已记录的临时 session。
- 长期记录只有清理后的任务、路径、哈希、模型、耗时、重试、审批、结果和错误；没有正文、完整
  prompt、transcript 或原始工具输出。
- 密码、API key、token、Cookie、session、私钥、认证头和设备登录值在输入、结果、错误及审批目标中
  脱敏。

## 兼容

- v1/v2 现有工具、schema、路由和结果保持回归通过。
- 没有可靠落盘路径时，v2 inline 仍要求 artifactContent、字节数和哈希，并保持 zero-tool。
- v3 失败不得静默回退 v2，也不得借旧协议绕过高风险审批。
