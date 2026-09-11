---
name: clash-verge-chain-proxy
disable-model-invocation: true
description: >
  在 Windows 上处理 Clash Verge Rev 的链式代理、前置节点、订阅增强配置和 AI 分流。遇到
  Clash Verge、Mihomo、dialer-proxy、前置节点、良心云/Flower/Nov 这类多订阅链式代理、AI
  站点分流、fallback 健康探测、url-test 延迟优先、tolerance 防抖、定时测速仍提前重测或切换、
  自动故障转移、订阅重导入后配置丢失、节点或分组在 UI 不显示、
  增强文件没有生效、生成脚本覆盖增强组、需要确认日志里真实走哪条链、Edge/Google 搜索位置来源与
  代理出口联合验收，Edge/Chrome 扩展修复后很快又
  显示损坏、扩展商店更新异常、Windows 双网卡或临时手机共享、切网后全站证书告警、接口跃点、
  Clash 核心受控重启、`external-controller-pipe` 命名管道查询、临时切换 selector、GitHub TLS/
  推送线路归因时，优先使用本技能。
---

# Clash Verge 链式代理

处理当前 Clash Verge / Mihomo 配置、链式代理、分流和相关网络故障。复用任务中已明确的架构、节点范围及授权。

## 按问题读取

- 单域名下载、TLS、双网卡、TUN、命名管道或临时切换：[网络诊断](references/network-diagnostics.md)。
- 前置与落地链、AI 分流、订阅重导入、select / fallback 配置与验收：[链路配置](references/chain-configuration.md)。
- 扩展提示损坏、更新失败或重启后复发：[浏览器扩展恢复](references/browser-extension-recovery.md)。
- 门户 DNS、路由排除、PktMon 或自动登录：[本地认证门户](references/local-auth-portal.md)。
- url-test、延迟容差、提前测速、自然周期与持续连接：[延迟优先](references/url-test-latency-priority.md)。
- Google 搜索位置与实际出口不符：[搜索位置](references/google-search-location.md)。
- 来源与历史依据：[来源登记](references/upstream-sources.md)，仅维护来源时读取。

只加载当前问题所需的参考。模板中的节点、组名、参数和验收范围由当前任务确定，不把历史方案当作所有任务的默认架构。

## 工作顺序

1. 先明确用户要查询、诊断、修改还是完整验收。只读请求交付问题和建议；已授权修复则完成相关修改及验证，不重复确认同一范围。
2. 读取启动环境已展开的 `APPDATA` 下 `io.github.clash-verge-rev.clash-verge-rev/profiles.yaml`，核对 `current`、目标 `uid / name / file / option`。
3. 按问题读取当前 profile 绑定的 `merge / proxies / groups / rules / script`。节点看 proxies、组结构看 groups、分流看 rules/script；保留订阅更新后仍需存在的改动应写入对应持久增强源。
4. 对照 `clash-verge-check.yaml`、`clash-verge.yaml` 和 `logs/service/service_latest.log`，核对本次目标的实际运行路径。只读诊断不连接写入接口、不改节点、文件或系统配置。
5. 写前重新读取相关文件并保存必要备份，保留用户新修改、当前选择和无关订阅。能从当前文件和日志查明的差异自行处理；无法查明且会改变网络范围或出口要求时才询问。
6. 按下面规则刷新并验证受影响部分，交付实际结果和必要文件位置。仅阻塞依赖缺失权限、接口或未决事项的步骤，继续独立工作。

## 刷新与重启

- 配置未生效时，先区分增强源、profile 绑定、后处理 script、生成文件和当前运行态的问题，不把“仍是旧内容”直接等同于需要重启。
- 优先使用当前版本经核实可用的后台生成或重载方式，并核对返回结果。只有核心重载能力时，不能冒充已重新生成 Verge 的增强配置。
- 确实需要重启 GUI、核心或浏览器时，说明准确对象、原因和连接/窗口影响，核对已有授权并保护正在使用的窗口。范围已有准确授权则继续；不强行关闭未保护的用户工作。
- 重启并非每次修改的固定步骤。故障涉及重启后复发，或任务要求冷启动、重启后稳定性时，对应验证仍需完成；当前不适合执行则明确该项未验证，不宣称稳定性已通过。
- 重启后按目标核对服务、配置和实际请求。后台能力不足、权限不够或重启受阻时，不反复硬停进程，不把未完成步骤标为通过。

## 验证与完成

- 查询或局部诊断：回答当前问题，给出相应文件、日志和事实范围即可结束，不等待最终签字。
- 配置修改：核对受影响的持久源与两份生成配置；适用时运行 `verge-mihomo.exe -t -f <generated-config>`，再检查目标请求和同一时段 `using <group>[<proxy>]` 日志。
- 单域名下载：区分入口、重定向、TLS、HTTP 和正文传输，验证所需文件完整性。不自动扫描全部节点、测试 AI 服务或执行故障转移。
- 完整链路、出口一致性、自动故障转移、自然周期和持续连接测试，只在对应任务中执行。周期和协议结果不能由一次手动测速代替，也不从单次成功推广为所有应用稳定。
- 分开报告持久配置、当前运行态和任务要求的重启/冷启动验证；已完成的部分照常交付，未验证项明确说明。

## 操作保护

- 真实订阅 URL、节点密码、UUID、落地账号和 controller secret 不进入回复、命令行或日志；含凭据的恢复材料保留在受保护位置，不提交公开仓库。
- 出口回显仅在内存中比较，不输出或持久化真实公网 IP；不以节点名称代替实际出口。
- 不直接编辑生成 YAML 作为长期修复，不手工修改 CC Switch 数据库或技能运行副本；技能发布沿用 agent-rules 的定向流程。
- 临时切换先保存原选择；结束前重读，仍为本次临时值才恢复，用户已改成第三个值则保留。具体命名管道步骤见网络诊断参考。
- 绕过 HTTP 代理或命中 DIRECT 不能证明绕过 TUN。隔离测试使用独立端口/controller，关闭自有 TUN 并核对真实物理出口；不破坏线上节点来制造故障。
- `current`、接口索引和运行态可能变化，按本轮实际状态定位。PowerShell 读写中文按共享规则使用 UTF-8。
