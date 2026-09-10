---
name: codex-relay-chain
description: >
  Windows 上诊断和维护 Codex、CodexCont、CC Switch 及中转站的配置和请求链路。
  用于 provider 切换、认证失效、配置反复覆盖、代理回环、Responses SSE 缺陷、
  Common Config 与任务设置差异、权限模式、旧任务认证及云端备份恢复问题。
  按具体故障选择检查；只读诊断不自动改配置或发送模型请求。
---

# Codex 中转链维护

## CC Switch 后台配置入口

先读取启动用户主目录下 `.agent-rules/local.md` 的“规则维护目录”字段，再读取该目录下
`automation/ccswitch-background/README.md`；入口为同目录 `Invoke-CcSwitchBackground.ps1`。
使用已经展开并核验的绝对路径；字段、组件或固定 CLI 校验缺失时报告不可用，不猜路径、不从 PATH
替换同名程序。步骤以共用指南为准，此处不复制配置维护实现。

供应商配置、Common Config 或通过 CC Switch 保存 Codex 技能启停规则时，使用共用入口先 Inspect、
再 Preview，核对候选和基线后按已有授权 Apply；操作状态用 Verify 核验，Rollback 仅恢复授权范围
且仍符合条件的本次操作。Inspect 只证明固定工具就绪，不证明配置或请求链路已验收。
保留本技能的认证、代理、Responses 和任务级设置排障职责；只修改该入口实际支持的 Codex 配置字段，
认证修改、供应商切换及其他未覆盖动作不得伪装成 apply-config。后台入口不支持时报告具体缺口。
全过程不切换窗口、不模拟键鼠、不驱动交互式终端；不能因为 CLI 失败而转用旧界面脚本。
配置保存、非目标字段保留、动态连接和实际请求分项验证；旧动态管道和临时连接信息不从备份恢复。

## 目标

处理这类链路：

```text
Codex -> CodexCont 127.0.0.1:8787/v1 -> CC Switch 127.0.0.1:15721/v1 -> 当前中转站
```

技能按最终服务对象“Codex 请求链路”命名，而不是按某个中间软件命名。CC Switch、CodexCont
以及会改写这条链路的本地 Agent 配置都属于排查范围；通用 `AGENTS.md`、技能目录和其他 Agent
规则维护仍由对应维护技能处理。

重点不是泛讲代理原理，而是先确认“谁有权写配置”，再检查对应链路。配置所有权与请求链路是两个维度：

- `ccswitch-owned`：当前默认。provider、认证、provider 固定模型和 Common Config 基线只通过
  CC Switch 配置；Codex Desktop 仍可按用户操作更新新任务默认值和任务级设置。本地 watcher 不写
  `config.toml`、`auth.json` 或 CC Switch 数据库，只管理 Codex Desktop 的两个权限字段；目标模式必须
  与所需审批组合一致，并记录退出与启动后漂移。需要显式
  `danger-full-access + on-request + auto_review` 时目标为 `custom`；`guardian-approvals` 只代表其内置组合。
- `legacy-writer`：历史配置 writer。只有用户明确要求回滚旧架构并接受争用风险时才进入；不能因为
  检测到漂移就自行启用。

请求链路模式仍按以下三类判断：

- `full`：Codex 是否固定打到 CodexCont，CodexCont 是否固定上游到 CC Switch。
- `ccswitch-only`：Codex 是否直连 CC Switch，CodexCont 是否保持停用。
- `disabled`：本地两层都不由 hook 自动启动。

链路验收时还需核对 provider、key、live backup 一致性及真实 Responses SSE。

本机当前默认组合是 `ccswitch-owned + ccswitch-only`。不要把“只监听 15721”误解成允许 watcher
接管配置；15721 是请求入口。provider、认证和 Common Config 基线仍由 CC Switch 管理，Codex
Desktop 自己维护的新任务默认值和任务级设置不属于 watcher 接管。

## 按问题读取

- 配置归属、权限模式、Common Config、OAuth、旧任务认证或云端恢复：[配置与认证](references/configuration-and-auth.md)。
- 端口、provider、代理回环、key 覆盖、watcher、停用或恢复链路：[模式与供应商](references/relay-modes-and-providers.md)。
- 流式文本、reasoning 字段、502/503/524 分层归因及上游修复能力：[Responses 验证](references/responses-validation.md)。

先用当前对话及相关文件定位目标，读取对应小节；无关入口、日志和历史案例不自动全读。
只有关联线索影响当前判断时才扩大只读检查，修复仍在已有授权范围内。
Clash/系统代理由 `clash-verge-chain-proxy` 处理，规则与技能维护交给 `agent-rules`。

## 执行与完成

1. 先核对当前模式、目标对象及实际配置归属。只读请求交付诊断与建议；明确修复请求复用已有授权。
2. 修改前读取最新状态，保存本次对象的备份及恢复依据，保留用户修改、凭据和无关配置。
   通过当前支持该动作的后台接口执行；不支持时说明具体缺口，只暂停该项，不转界面、SQL 或直接覆盖生成配置。
3. 普通修复不自动改变架构、启用旧 writer、重启应用或创建任务。用户已明确授权对应变更时继续；
   新出现的实质范围变化或无法查明的目标歧义才询问。重载前保护正在运行的任务和未保存工作。
4. 验证与目标匹配：解释配置或字段只核对相关静态状态；要求链路可用时完成所需真实请求；
   reasoning 或协议问题保留严格 SSE 检查；反复覆盖、停用 watcher 或链路恢复保留至少 60 秒受控观察。
   不因普通字段查询自动做全链路探测或等待观察。
5. 新增模型请求按已明确的站点、模型、测试范围及费用上限执行，复用授权；错误和重试也计入原范围。
   所需授权缺失只暂停收费测试。已有适用日志可复用，不为填报告重新请求。
6. 同范围有依据的修正和必要重试继续推进；无法解决时说明受阻步骤，完成其余独立工作。
   输出实际完成的修改、相关检查及必要限制，省略无关栏目。静态保存、接口成功与目标任务成功分开说明；
   达到本次目标即可交付，不等待最终签字。

## 安全边界

- 不打印完整 API key。
- 不打印 OAuth token、完整 `auth.json` 或带 token 的命令行。
- 不把真实 key 写进 skill、README、提交信息或日志摘要。
- 不把某一家中转站硬编码成唯一方案。
- 不直接改 `%USERPROFILE%\.cc-switch\skills` 或 `%USERPROFILE%\.codex\skills` 里的 skill 运行时副本。
- `ccswitch-owned` 下不由技能、脚本或 watcher 直接写 CC Switch 数据库、`config.toml`、`auth.json`、
  provider 或 Common Config；provider 与共同基线通过 CC Switch 变更，Desktop 新任务默认值和任务级
  设置只通过 Codex Desktop 自身交互维护。
- 不让 watcher 或兼容入口修改 `CodexAutoContinue`，也不重新启用 `CodexCapabilityCheck`。
- 不把 `/v1/models` 当作最终通过信号。
- 不在存在无关 git 改动时把它们一起提交。
- 停用计划任务优先 `Disable-ScheduledTask`，不用 `Unregister-ScheduledTask`——保留可逆性，用户改主意时能直接 `Enable-ScheduledTask` 恢复，不用重新注册任务。
