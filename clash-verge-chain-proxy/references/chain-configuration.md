# 链路配置与专项验收

按本次已确认的架构选择相应方案；通用范围、授权和刷新规则见 [技能入口](../SKILL.md)。

## 推荐配置形态

如果用户要“AI 走一个前置，普通流量走另一个前置，落地同一个节点”，用两条落地代理，不共用同一个 `dialer-proxy`：

```yaml
proxies:
  - name: <Nov via Flower>
    type: socks5
    server: <landing-host>
    port: <landing-port>
    username: <landing-user>
    password: <landing-password>
    dialer-proxy: <Flower front group>

  - name: <Nov via normal front>
    type: socks5
    server: <landing-host>
    port: <landing-port>
    username: <landing-user>
    password: <landing-password>
    dialer-proxy: <normal front group>
```

再建两个前置组；需要手动控制时用 `select`，需要自动健康选择时用 `fallback`：

- `<Flower front group>`：放 Flower 订阅里可用的前置节点。
- `<normal front group>`：放当前普通订阅里可用的前置节点。

`select` 组适合在 UI 里临时换前置；`fallback` 组适合按候选顺序自动跳过故障节点。

## 手动 NOV 链与动态全订阅前置池

当用户要求“所有实际代理流量最终都经同一个 NOV 落地，AI 可手动选择 Flower 或普通订阅作为
前置，普通国外流量只使用普通订阅前置”时，使用共享前置组，不为 AI 和普通流量复制两份普通
前置选择：

```text
AI 规则 -> <AI group: select>
           |- <Nov via Flower> -> <Flower front: select> -> Flower 节点
           `- <Nov via normal> -> <normal front: select> -> 普通订阅节点

普通国外规则 -> <normal group: select> -> <Nov via normal>
                                      `-> 复用同一 <normal front>
```

- `<AI group>` 的候选只能是两条完整 NOV 链；不要放裸前置、`DIRECT`、`自动选择`或`故障转移`。
- `<normal group>` 只引用 `<Nov via normal>`。用户在共享的 `<normal front>` 换一次节点，AI 的
  普通订阅分支和普通国外流量应同时读取该选择。
- 两条 NOV 代理的 `dialer-proxy` 分别指向 Flower 前置组和共享普通前置组。AI 规则仍须位于
  宽泛国外规则之前；国内、局域网、`DIRECT` 和 `REJECT` 规则保持原语义。
- 首次部署不顺手删除旧的 `自动选择`、`故障转移`等组。先证明没有规则或活动组再引用它们；删除
  按本次准确清理授权处理；未获授权的旧组保持原位。

普通前置池必须从**当前目标订阅自身**动态重建：

1. 解析刚更新的目标订阅原始 YAML 或其未注入增强项的 provider 输出，按原顺序读取全部
   `proxies[].name`。不要从已混合多订阅和注入代理的最终 `clash-verge.yaml` 反推来源。
2. 只排除能够由来源或条目语义确认的非真实前置：流量/到期/续费等信息条目、注入的 NOV 落地
   代理、旧链条，以及不属于目标订阅的 Flower 或其他辅助节点。不要按上一次的 7 个、9 个或任意
   固定白名单做包含过滤，也不要把某次订阅的节点总数写成长期常量。
3. 将过滤后的有序唯一列表完整写入 `<normal front>`。每次官网更新或重新导入后都从新订阅重新
   计算，不能在旧白名单上增删修补。
4. 计算 `expected = source_names - excluded_names`，再比较最终前置组：`expected - actual` 和
   `actual - expected` 都必须为空。另查重并确认顺序稳定；仅比较数量不能发现漏节点或串入 Flower。

如果要生成独立 profile，先记录当前激活 profile、备份原 YAML 并保存 SHA-256；导入为新名称，
不覆盖原 profile。任一静态或运行态检查失败时，停用新 profile 并重新激活原 profile，保留备份。

## 完整链路自动故障转移

当“前置节点本身能上网，但该节点到 NOV 超时”也必须触发切换时，不要只对裸前置节点做
`generate_204`。为每个前置节点各生成一条独立的“前置 -> NOV”代理，再让 `fallback` 探测这些
完整链路。每条链使用相同的 NOV 参数，只改变 `dialer-proxy`：

```yaml
proxies:
  - name: <NOV via Flower node 1>
    type: socks5
    server: <landing-host>
    port: <landing-port>
    username: <landing-user>
    password: <landing-password>
    dialer-proxy: <Flower node 1>
```

对 Flower 和普通订阅的每个真实节点重复生成该条目，再按下面的边界聚合：

```yaml
proxy-groups:
  - name: <Flower to NOV auto>
    type: fallback
    url: https://www.gstatic.com/generate_204
    interval: 30
    timeout: 5000
    max-failed-times: 2
    lazy: false
    proxies: [<NOV via Flower node 1>, <NOV via Flower node 2>]

  - name: <normal to NOV auto>
    type: fallback
    url: https://www.gstatic.com/generate_204
    interval: 30
    timeout: 5000
    max-failed-times: 2
    lazy: false
    proxies: [<NOV via normal node 1>, <NOV via normal node 2>]

  - name: <normal plain auto>
    type: fallback
    url: https://www.gstatic.com/generate_204
    interval: 30
    timeout: 5000
    max-failed-times: 2
    lazy: false
    proxies: [<normal node 1>, <normal node 2>]

  - name: <AI group>
    type: fallback
    url: https://www.gstatic.com/generate_204
    interval: 30
    timeout: 5000
    max-failed-times: 2
    lazy: false
    proxies: [<Flower to NOV auto>, <normal to NOV auto>]

  - name: <normal group>
    type: fallback
    url: https://www.gstatic.com/generate_204
    interval: 30
    timeout: 5000
    max-failed-times: 2
    lazy: false
    proxies: [<normal to NOV auto>, <normal plain auto>]
```

- AI 流量只引用 `<AI group>`：Flower/NOV 优先，普通订阅/NOV 备用；两边都失败就保持失败，候选中
  不得加入裸节点、`DIRECT` 或 `<normal plain auto>`，因此最终出口不会降级。
- 普通境外流量引用 `<normal group>`：平时优先走普通订阅/NOV，NOV 链全部失效后才降级到普通订阅
  裸节点；普通节点的最终出口 IP 可以随故障转移变化，Flower 不得进入该组。
- `<normal to NOV auto>` 可以同时作为 AI 的第二条固定出口路径和普通流量的首选路径；
  `<normal plain auto>` 只能被普通流量的外层组引用。
- `fallback` 按候选顺序选第一个健康项，不是测速选最快；`lazy: false` 让备用路径持续探测，恢复后会
  自动回到更靠前的候选。
- `generate_204` 只验证通用 HTTPS 链路，不等价于 ChatGPT 或 Anthropic 专项可用；最终仍需用目标
  域名请求和同一时段日志验收。

增强文件改完后，必须检查当前 profile 绑定的 `script`。后处理脚本可能用 `upsertGroup` 重建同名组，
把 `fallback` 覆盖回 `select`。最终生成的 `clash-verge.yaml` 和 `clash-verge-check.yaml` 才是验收对象，
不直接编辑它们作为长期修复。

### 延迟优先且减少切换

低延迟选择、tolerance、store-selected、嵌套组健康判断和自然周期验证统一按 [延迟优先参考](url-test-latency-priority.md) 执行。
只在任务涉及自动切换策略、周期或持续连接时启用对应验证；局部域名修复不自动进入长时间观察。

## AI 分流

AI 域名和本地 App 进程要放在规则前面，先于普通国外规则和 `MATCH`：

```yaml
rules:
  - PROCESS-NAME,claude.exe,<AI group>
  - PROCESS-NAME,claude,<AI group>
  - DOMAIN-SUFFIX,openai.com,<AI group>
  - DOMAIN-SUFFIX,chatgpt.com,<AI group>
  - DOMAIN-SUFFIX,oaistatic.com,<AI group>
  - DOMAIN-SUFFIX,oaiusercontent.com,<AI group>
  - DOMAIN-SUFFIX,anthropic.com,<AI group>
  - DOMAIN-SUFFIX,claude.ai,<AI group>
  - DOMAIN-SUFFIX,claude.com,<AI group>
  - DOMAIN-SUFFIX,gemini.google.com,<AI group>
  - DOMAIN,generativelanguage.googleapis.com,<AI group>
  - DOMAIN,aistudio.google.com,<AI group>
  - DOMAIN-SUFFIX,perplexity.ai,<AI group>
  - DOMAIN-SUFFIX,poe.com,<AI group>
  - DOMAIN-SUFFIX,openrouter.ai,<AI group>
  - DOMAIN-SUFFIX,x.ai,<AI group>
  - DOMAIN-SUFFIX,grok.com,<AI group>
  - DOMAIN,copilot.microsoft.com,<AI group>
```

Windows 上如果用户说“所有 Claude App 都算 AI”，可用 `PROCESS-NAME,claude.exe` 粗匹配。若用户只要桌面 Claude App，不要 Claude Code 或 VS Code 插件，改用 `PROCESS-PATH`，避免误伤。

## 订阅重导入恢复

普通“更新订阅”一般不会丢增强配置，因为增强文件绑定在 profile 上。

官网重新导入通常会生成新 UID。旧增强文件可能仍在磁盘，但新 profile 不会自动绑定它们。遇到这种情况，不要只找旧文件；要重新定位新 profile。

沿用已有恢复工具或按以下步骤处理；不为一次恢复默认新建脚本：

1. 读取 `profiles.yaml`。
2. 按 profile 名称或订阅特征找到当前目标订阅，例如 `<normal subscription name>`。
3. 找到辅助订阅，例如 `<Flower subscription name>`。
4. 读取新目标订阅的 `option.proxies / option.groups / option.script / option.rules`。
5. 备份这些增强文件和 `profiles.yaml`。
6. 重新写入：
   - 两条落地链：`<Nov via Flower>`、`<Nov via normal front>`。
   - 两个前置组：`<Flower front group>`、`<normal front group>`。
   - AI 组和 AI 规则。
   - 普通主组默认使用 `<Nov via normal front>`。
7. 按 [入口的刷新与重启规则](../SKILL.md#刷新与重启) 检查并重新生成配置；不直接把 `clash-verge.yaml` 当长期源文件。

恢复脚本如果包含真实订阅地址、节点密码、用户名或落地节点凭据，必须加入 `.gitignore`，不要提交到公开仓库。

## 验证

先看受影响文件，再看对应运行日志。下面的完整 fallback、出口一致性和 select 流程，仅用于相应设计或验收任务；局部修复选取相关检查，不自动遍历全部组。

```powershell
$base = Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'
rg -n -S "Nov|Flower前置|良心云前置|AI网站|PROCESS-NAME,claude" `
  (Join-Path $base 'clash-verge.yaml') `
  (Join-Path $base 'clash-verge-check.yaml')
```

用 Mihomo 检查最终配置：

```powershell
& '<Clash Verge install dir>\verge-mihomo.exe' -t -f "$env:APPDATA\io.github.clash-verge-rev.clash-verge-rev\clash-verge.yaml"
```

看日志是否命中预期：

```powershell
$base = Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'
rg -n -S "claude\.exe.*AI网站|using .*Nov|using DIRECT" `
  (Join-Path $base 'logs\service\service_latest.log')
```

### 自动 `fallback` 验收

1. 用 YAML 解析器确认 Flower/NOV、普通订阅/NOV、普通裸节点、AI 和普通外层组各出现一次；确认每个
   NOV 内层组的候选都是逐节点生成的完整链，AI 组没有 `DIRECT` 或普通裸节点。
2. 确认每条 NOV 代理的 `dialer-proxy` 指向对应的单个前置节点；普通外层组的候选顺序只能是
   “普通订阅/NOV 自动、普通裸节点自动”，Flower 不得进入普通外层组。确认所有自动组的 `url`、
   `interval`、`timeout`、`max-failed-times`、`lazy` 均在最终生成配置中。
3. 通过 `external-controller-pipe` 查询 `/version` 和 `/proxies`，只汇总目标组的 `now`、候选 `all`、`alive`、`history`，不打印 `secret`、密码、UUID 或完整代理对象。
4. 受控测试优先使用运行态已经标记 `alive: false` 的候选。不要为了制造故障去破坏线上节点；没有
   安全失败候选时，复制最小配置到临时目录，关闭该配置的 TUN，并使用独立的监听端口、controller
   和 DNS 端口。
5. 主实例 TUN 仍开启时，隔离进程的出站也可能被再次接管。临时配置要用 `interface-name` 绑定当前
   物理出口，并使用已验证可从该物理接口访问的 DNS；再根据隔离 Mihomo PID 的本地地址、
   `Find-NetRoute` 和隔离日志确认没有绕回主 TUN。做不到这些时，隔离测试出现 `EOF`、`SERVFAIL`
   或超时只能记为“测试环境不确定”，不能据此判定 NOV 或前置节点失效。
6. 在隔离配置中分别让 Flower/NOV 和普通订阅/NOV 失效：AI 只能在两条 NOV 路径间切换，全部 NOV
   失效时保持失败；普通外层组应降级到普通裸节点，恢复 NOV 后回到首选 NOV 路径。
7. 测试结束后确认运行态 selector 没有被临时 PUT 覆盖；隔离进程、临时配置和日志清理前先展示清场预览。

合格信号：

- AI 域名或 `claude.exe`：`using <AI group>[<Nov via Flower>]`
- 普通国外流量正常态：`using <normal group>[<normal to NOV auto>]`
- 普通国外流量 NOV 故障态：`using <normal group>[<normal plain auto>]`
- 国内或原本直连流量：`using DIRECT`

### 出口 IP 一致性与隐私验收

1. 对 AI 的 Flower/NOV、AI 的普通订阅/NOV，以及普通流量当前的 NOV 首选路径，分别通过同一个出口
   回显服务发起请求。把返回值保存在进程内变量中，规范化后只比较是否相等，不把原始 IP 输出到
   终端、日志、报告或验收文件。
2. 报告只写布尔结果和路径状态，例如 `AI_NOV_PATHS_SAME_EXIT=true`、
   `ORDINARY_USES_NOV=true`；不得写实际 IPv4/IPv6 地址，也不得用节点名称代替出口回显证据。
3. 正常态下三条 NOV 路径应得到同一最终出口。普通流量降级到 `<normal plain auto>` 后出口可以变化，
   但必须同时确认 AI 仍停留在 NOV 组，不能因普通流量的降级而暴露 AI 到普通节点。
4. 若请求工具、异常堆栈或调试日志会自动打印响应正文，先改为只在内存中解析并输出比较结果；无法
   避免原始 IP 落盘时停止该验收，不以泄露敏感网络信息换取结论。

### 手动 `select` NOV 链验收

1. 用 YAML 解析器确认目标组各只定义一次；普通前置组与当前目标订阅过滤后的完整节点集合严格
   相等，且不含元信息、Flower、注入 NOV 或旧链条。
2. 确认 AI 组候选恰好是两条 NOV 链、普通主组候选恰好是普通订阅 NOV 链，两条代理的
   `dialer-proxy` 正确。扫描全部规则和活动组引用，确保没有流量仍指向旧的 `自动选择`、
   `故障转移`或裸前置；旧组可以保留为未引用定义。
3. 通过 controller 查询 `/proxies`，确认所有目标手动组均为 selector，且 `all` 与静态 YAML 一致。
   对每个待测候选执行 `PUT` 后重新 `GET`，只有 `now` 精确等于所选项才继续请求。
4. AI 组分别选择 Flower 链和普通订阅链，向 OpenAI/ChatGPT 与 Anthropic/Claude 发起真实请求；
   普通国外站点必须命中普通订阅 NOV 链，国内站点仍命中 `DIRECT`。用同一时段服务日志确认
   `using <group>[<chain>]`，不能只凭 selector 显示或通用 204 探测宣称完成。
5. 共享性验证至少选两个不同的普通前置节点 A、B；每次分别测试普通国外流量和 AI 的普通订阅
   分支，确认两者都随同一个 `<normal front>.now` 变化。结束前读回选择，仍为本次临时值才恢复原值并复查；用户已另行改选则保留，按[网络诊断](network-diagnostics.md)的并发恢复规则收尾。

如果生成配置仍是旧内容，先核对当前 profile 绑定、生成错误和后处理脚本，再使用经核实可用的后台刷新方式。按入口的刷新与重启规则处理，不由文件未刷新直接推出需要重启 GUI。


## 常见坑

- 同名旧增强文件还在，但新导入 profile 没绑定它。
- `script` 环境不一定能读本地文件。需要跨订阅复制节点时，更稳的是把选中节点写进 `proxies` 增强文件。
- 一个落地节点如果要走两个不同前置，应该创建两个同参数、不同 `dialer-proxy` 的代理条目。
- 进程匹配可能误伤。`PROCESS-NAME,claude.exe` 会覆盖桌面 Claude、Claude Code、VS Code 插件里的 Claude。
- 命名管道临时切换在 `finally` 中先读回，仅恢复仍为本次临时值的选择并复查；用户已改选则保留，不能只假定 PUT 已成功。
