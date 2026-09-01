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

## 目标

处理 Clash Verge Rev 里“当前订阅 + 其他订阅节点 + 单独落地节点 + 链式代理 + AI 分流”的配置、恢复和验证。

重点不是泛讲代理原理，而是找准三件事：

- 当前启用的 profile 是谁。
- 它绑定的 `merge / proxies / groups / rules / script` 文件是哪几个。
- 最终生成配置和服务日志是否真的按预期走链。

## 工作顺序

1. 读 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\profiles.yaml`。
   - 确认 `current`。
   - 找当前 profile 的 `uid / name / file / option`。
   - 记录绑定的 `merge / proxies / groups / rules / script` 文件。
2. 读当前 profile 绑定的增强文件。
   - 节点增删看 `proxies`。
   - 分组增删看 `groups`。
   - 域名或进程分流看 `rules` 或 `script`。
   - 订阅更新后还要保留的逻辑，优先放增强文件，不直接改订阅原始 YAML。
3. 读最终生成配置。
   - `%APPDATA%\...\clash-verge-check.yaml`
   - `%APPDATA%\...\clash-verge.yaml`
4. 读服务日志。
   - `%APPDATA%\...\logs\service\service_latest.log`
   - 看到 `using <group>[<proxy>]` 才算真实生效。

## Windows 双出口、手机共享与全站证书告警

Windows 同时保留有线网和临时手机 USB/Wi-Fi 共享时，浏览器直连、系统代理和 Mihomo TUN
可能走不同出口。用户说“正在用手机上网”不能证明电脑已停止使用有线网；先看实际网卡、路由和
Clash 运行态。

当开启系统代理后多个 HTTPS 网站出现 `ERR_CERT_COMMON_NAME_INVALID`，关闭代理后恢复：

1. 不跳过证书告警，不导入网页提供的证书，也不先重置整套网络。
2. 先做最小 A/B：确认手机本机访问是否正常、告警域名是否随目标网站变化、电脑关闭系统代理后
   是否恢复。代理关闭后恢复只能把嫌疑收窄到电脑代理路径，不能单独证明代理节点恶意或失效。
3. 只读检查系统时间、WinINET/WinHTTP 代理、Clash 本地监听端口、活动网卡的地址/网关/DNS、
   IPv4 默认路由、`AutomaticMetric`/`InterfaceMetric`、hosts、Mihomo 配置与服务日志。
4. `Mihomo` TUN 可能创建优先级最高的虚拟默认路由；排查外层出口时仍要单独比较物理网卡路由，
   必要时按 Mihomo 已建立连接的本地地址判断外层连接实际绑定哪张网卡。
5. 证书名称不匹配只证明请求到达了错误 TLS 端点。没有证书 Subject/Issuer、DNS 对照和同一时段
   日志时，不把根因断言为 DNS 劫持、运营商拦截、校园认证页或某个代理节点。

### 本地认证门户与 Mihomo TUN

当本机自动登录程序访问校园网或其他私网认证门户时，先把“HTTP 代理”和“TUN 路由”分开判断。
程序显式关闭或绕过 WinINET/HTTP 代理，并不代表流量不会被 `auto-route` 的 TUN 接管。

遇到门户解析成 Fake-IP、需要绑定校园 DNS 到物理网卡、普通权限看不到 SYSTEM 任务，或需要在不再次
重启核心的情况下证明运行路径时，读取
[`references/local-auth-portal.md`](references/local-auth-portal.md) 并按其中的配置与抓包流程验收。

1. 从当前 `profiles.yaml` 定位激活 profile 和绑定的增强文件，重新确认门户域名、真实地址、CIDR、
   校内 DNS 与物理接口，不沿用旧环境记录。
2. “在 Clash 内命中 `DIRECT`”不等于“不受 Clash 影响”。使用 Fake-IP DNS 时，独立访问通常还需要
   门户域名排除 Fake-IP、精确 `nameserver-policy` 绑定物理接口，以及 TUN `route-exclude-address`；
   每项都写入当前 profile 的持久化增强源，并在写前备份。
3. 检查 `clash-verge.yaml` 和 `clash-verge-check.yaml` 的最终结果并运行 `verge-mihomo.exe -t`。
   `/configs` 可能不返回完整 DNS 段；字段缺失不能证明 DNS 配置未加载，也不能直接按数组索引。
4. 运行态验收要把真实门户解析、物理接口上的目标 DNS 请求与应答、`Find-NetRoute`、自动登录状态和
   任务状态绑定在同一时间窗口。只看到其他域名访问校园 DNS，不能证明门户 policy 生效。
5. 报告时区分“持久配置通过”“当前运行态通过”和“真实冷启动通过”。没有实际重启时，前两项可以
   完成，冷启动保持待验收；没有任务审计日志时，不猜测历史删除或启动失败的唯一原因。

### 临时手机共享的接口跃点

Windows 先选最长前缀，再在同样精确的路由中选择“路由跃点 + 接口跃点”更小者。界面中的
“接口跃点”是路由成本，不是实际经过的路由器数量。

用户只在少量时间接入手机，但要求手机接入时承担公网出口，可以只把手机共享网卡的 IPv4 接口跃点
固定为低于有线网当前值的数；有线网保持自动跃点和连接状态。手机断开后，其默认路由消失，有线网
自然接管。不要为此默认拔网线、禁用有线网卡或删除有线网默认网关。

执行前先记录基线并取得用户对本次网络改动和短时连接切换的授权：

1. 按活动网卡描述和 `InterfaceGuid` 定位手机共享设备，并断言只有一个目标；不要复用上次记录的
   `ifIndex`，USB 网卡重连后索引可能变化。
2. 只改已验证需要调整的地址族。当前仅有 IPv4 默认路由时，不顺手修改 IPv6。
3. `Set-NetIPInterface` 需要管理员权限。普通调用返回“拒绝访问”后，不原样重试；说明 UAC 的
   精确改动范围，再用一次性提权执行：

```powershell
Set-NetIPInterface -InterfaceIndex <phone-ifindex> -AddressFamily IPv4 `
  -AutomaticMetric Disabled -InterfaceMetric <lower-metric>
```

4. 修改后同时验证活动值、持久值和路由优先级：

```powershell
Get-NetIPInterface -InterfaceIndex <phone-ifindex> -AddressFamily IPv4
netsh interface ipv4 show interface interface="<phone-alias>" store=persistent
Get-NetRoute -AddressFamily IPv4 -DestinationPrefix 0.0.0.0/0
```

验收应证明手机物理默认路由成本低于有线网、有线网设置未被改动，且持久存储显示自动跃点已关闭。
若校园资源跨越有线网直连子网，还要单独核实其具体路由；不要假定提高有线网跃点仍能覆盖全部校内网段。

### 受控重启 Clash 核心

切换物理出口后，只有旧连接、Fake-IP/DNS 状态或实际错误仍存在，或用户明确要求时才重启核心，
不把重启当作每次接入手机的固定步骤。重启前告知用户代理会中断数秒，并记录
`clash_verge_service` 状态和 `verge-mihomo` PID。

优先通过 Windows 服务管理器做一次受控重启，不直接 `Stop-Process` 核心，也不退出 Clash Verge GUI：

```powershell
Restart-Service -Name clash_verge_service -Force
```

该命令通常需要 UAC。完成后确认服务回到 `Running`、核心 PID 已变化，并通过命名管道
`GET /version` 得到 `200`。同时检查系统代理开关没有被意外改变，只查看新核心启动后的日志。
手机网络或 TUN 下单独出现 ICMP echo timeout 不等于 HTTPS 失败；最终仍用目标 HTTPS 访问和同一
时段服务日志验收。

## 只开放命名管道时的运行态控制

`config.yaml` 可能配置 `external-controller-pipe: \\.\pipe\verge-mihomo`，而最终生成配置
不暴露 TCP controller。此时 `9097` 没监听不代表 Mihomo API 不可用。优先用现有 `pywin32`
的 `win32file.CreateFile` 连接命名管道；没有该依赖时用 .NET `NamedPipeClientStream`。按
HTTP/1.1 发送请求，从 `config.yaml` 读取 `secret` 放进 `Authorization: Bearer ...`，但不要打印 secret。

常用接口：

- `GET /version`：确认管道 API 可用。
- `GET /proxies`：读取 selector 的 `now`、候选 `all`，以及节点 `alive` / `history`。
- `PUT /proxies/<URL-encoded-group>`，body 为 `{"name":"<candidate>"}`：切换运行态 selector。

只为一次诊断或推送临时换线路时，不改 YAML：

1. 先从失败请求对应的服务日志确认 GitHub 实际命中的 selector；无法确认时不要猜组。
2. `GET /proxies` 保存该 selector 的原值。
3. 从该组候选中选 `alive = true` 且近期 delay 有效的节点，不凭名称猜可用性。
4. `PUT` 临时节点后立即再次 `GET /proxies`，确认该组 `now == candidate`；不一致就停止目标请求。
5. 执行真实目标请求。
6. 在 `finally` 中先 `GET /proxies`：`now` 仍等于临时候选时才 `PUT` 原值并再次 `GET` 确认；
   已等于原值则无需写入；若已变成第三个值，说明测试期间发生并发切换，不要覆盖，明确报告。

运行态切换会立即影响使用该组的流量。切换前告知用户，持续时间只覆盖必要测试，不修改订阅、
增强文件或默认选择。

### GitHub 与 Git 推送验证

一次 `curl https://github.com` 返回 200 不能证明 Git 多连接稳定。按顺序验证：

1. 先用失败日志确认 `git-remote-https.exe` 实际命中的 selector。
2. `git ls-remote --heads origin`。
3. 只有当前任务已明确授权推送且确有待推提交时，才执行真实 `git push`。纯 TLS 诊断不创建提交、
   不推送，停在 `ls-remote` 并注明只验证了读路径。
4. 核对服务日志里对应 `git-remote-https.exe` 是否命中预期组和节点。

Git 报 Schannel 握手失败时，先按同一进程、目标和时间窗口关联服务日志。若同一请求对应远端节点
`connect error: context deadline exceeded`，代理路径是优先嫌疑，但仍不能单凭这一条排除本机
TLS/证书问题。在任务授权范围内改用另一个存活节点；目标允许直连时也可用 DIRECT 做 A/B。
只有替代路径成功而原节点稳定失败时，才把故障归到原代理路径。可用一次性
`git -c http.proxy=... -c http.version=HTTP/1.1` 测试；需要对照 TLS 后端时也只用单次
`-c http.sslBackend=openssl -c http.sslCAInfo=<Git CA bundle>`，不要先写全局 Git 配置。
测试或推送结束后按上面的并发保护规则恢复原 selector。

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
  属于单独的清理动作，另行取得批准。

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

当用户希望自动选择低延迟节点，但不希望轻微波动频繁切换时，读取
[`references/url-test-latency-priority.md`](references/url-test-latency-priority.md)。

- 内层候选需要比较延迟时使用 `url-test`，NOV 场景仍探测逐节点生成的完整“前置 -> NOV”链；
  外层业务优先级继续由 `fallback` 决定，不把“最快”和“优先级”混成同一层。
- 把 `interval` 解释为定时健康检查间隔，不解释成硬性切换冷却。失败次数超过
  `max-failed-times` 配置值会提前触发强制健康检查，失效切换也不受 `tolerance` 保护。
- 同名自动组可能继承 `store-selected` 的旧选择。转换策略时优先使用新组名并精确更新引用，不删除
  全局 `cache.db`；候选卡片顺序也不等于实际选中顺序。
- 父 `fallback` 嵌套子 `url-test` 时，要检查组级健康状态导致越过子组的风险。AI 外层不得因此加入
  裸节点或 `DIRECT`；普通流量是否允许降级到裸节点继续服从用户已确认的边界。
- 验收至少跨过一次自然定时周期：持续连接用来观察旧连接是否重连，切换后另建新连接确认新节点；
  只做手动测速或短时轮询不能证明 30 分钟周期和长连接表现。

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

## Edge/Chrome 扩展更新异常

Edge 或 Chrome 显示“扩展可能已损坏”，不等于扩展文件已经损坏。若修复后很快复发，并且 Clash Verge 长期开启规则模式、TUN 或链式代理，先区分浏览器完整性状态和扩展更新请求是否失败。

### 先确认是不是文件损坏

1. 读取实际使用的浏览器 profile，不默认所有环境都是 `Default`。
2. 在 `Secure Preferences` 检查扩展状态和 `disable_reasons`；数值包含 `1024` 表示 Chromium 的 `DISABLE_CORRUPTED`。
3. 读取扩展 `manifest.json` 的 `update_url`，以真实值作为更新服务入口。
4. 如果需要判断文件完整性，按 Chromium 的 4096 字节分块 `treehash` 比较 `_metadata\computed_hashes.json` 和 `verified_contents.json`。普通文件 SHA-256 或平铺拼接哈希不能代替这项校验。
5. 若清单可解析、文件存在且 `treehash` 匹配，不把浏览器提示解释为磁盘文件被改坏；继续查更新状态和代理路径。

### 查真实更新线路

从当前 profile 和服务日志反推，不只假定 `clients2.google.com`：

```powershell
$base = Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'
rg -n -S "msedge\.exe|chrome\.exe|update\.googleapis\.com|chromewebstore\.googleapis\.com|clients2\.google" `
  (Join-Path $base 'logs\service\service_latest.log')
```

Google/Chrome Web Store 扩展更新中已经观察到的域名包括：

```yaml
rules:
  - DOMAIN,update.googleapis.com,<stable group>
  - DOMAIN,chromewebstore.googleapis.com,<stable group>
  - DOMAIN,clients2.google.com,<stable group>
  - DOMAIN,clients2.googleusercontent.com,<stable group>
```

只添加目标环境实际需要的域名，并放在宽泛国外规则和 `MATCH` 前。优先使用域名规则；除非用户明确要让整个浏览器走同一代理，否则不要用 `PROCESS-NAME,msedge.exe` 或 `PROCESS-NAME,chrome.exe` 作为长期修复，因为它会改变全部浏览流量。

持久规则写进当前 profile 绑定的 `rules` 增强文件，不直接改生成的 `clash-verge.yaml`。写入前备份 `profiles.yaml`、对应增强文件，以及排障所需的浏览器 profile 文件；如需关闭浏览器或代理软件，先告知用户。

### 修复后验证

按以下顺序验收：

1. 增强文件包含新增域名规则。
2. `clash-verge-check.yaml` 和 `clash-verge.yaml` 已重新生成并包含规则。
3. `verge-mihomo.exe -t -f <generated-config>` 通过语法检查。
4. 服务日志显示目标域名和浏览器进程命中预期分组及代理链。
5. 在浏览器里重新触发扩展更新并重启浏览器，确认扩展全部启用、`disable_reasons` 不再包含 `1024`，且 `corrupted_disable_count` 不再增加。

一次更新成功不足以证明修复稳定。至少完成一次浏览器重启后的复查；若计数继续增加，保留备份并继续查下载重定向域名、代理切换和 Edge/Chromium 自身的完整性判断。

## 订阅重导入恢复

普通“更新订阅”一般不会丢增强配置，因为增强文件绑定在 profile 上。

官网重新导入通常会生成新 UID。旧增强文件可能仍在磁盘，但新 profile 不会自动绑定它们。遇到这种情况，不要只找旧文件；要重新定位新 profile。

推荐做一个恢复脚本，逻辑如下：

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
7. 触发 Clash Verge 重新生成配置，或重启 GUI；不直接把 `clash-verge.yaml` 当长期源文件。

恢复脚本如果包含真实订阅地址、节点密码、用户名或落地节点凭据，必须加入 `.gitignore`，不要提交到公开仓库。

## Edge/Google 搜索位置联合验收

用户询问 Edge 中 Google 搜索显示的城市为什么不跟代理出口一致，或要求验收固定 NOV 出口时，读取
[`references/google-search-location.md`](references/google-search-location.md)。这类任务必须在同一时间窗口绑定三类证据：

- Edge 页面实际使用的公网出口回显；
- Google 搜索页脚的位置文字及其明确标注的来源；
- Mihomo 服务日志中该次 `msedge.exe` 请求的 `using <group>[<proxy>]`。

浏览器/Windows 定位权限、Google 活动记录、地点/住址、位置 Cookie 和 IP 推断要分别判断。节点名称、
单一 IP 地理库或一次 NOV 命中都不能单独完成验收；`fallback` 候选含裸节点时，还要明确说明固定出口并不稳定。
用户只授权 Edge 本机处理时，不扩大到 Google 账号、活动记录、住址、Clash 节点或代理配置；若只能清理
整个 Google 站点数据且可能退出登录，停止并报告。

## 验证

先看文件，再看运行日志。

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
   分支，确认两者都随同一个 `<normal front>.now` 变化。结束后恢复用户原选择并复查。

如果 `clash-verge.yaml` 仍是旧内容，说明增强文件已改但 Verge 还没重新生成。先重启 Clash Verge GUI；服务重启可能需要管理员权限，不要在无权限时反复硬停服务。

## 安全边界

- 不把真实订阅 URL、节点密码、UUID、落地代理账号写进回复或 skill。
- 不输出 Mihomo controller secret，也不把它放进进程命令行或日志。
- 不输出或持久化出口回显服务返回的真实公网 IP；只报告路径间是否为同一出口。
- 不直接改 `.cc-switch`、`.codex`、`.claude` 运行时 skill 目录；改源码目录后通过同步工具分发。
- 不把含凭据的恢复脚本提交到公开仓库。
- 不只改 `clash-verge.yaml` 就宣称完成持久化。
- 不只看 UI 显示；必须用最终 YAML 和日志验证。
- 受控故障测试不人为破坏线上节点；隔离配置不得复用线上 controller pipe 或 TUN，主 TUN 接管风险
  未排除时不得把隔离测试失败归因到代理链。
- 不默认修改无关订阅。

## 常见坑

- `current` profile 变了。先看 `profiles.yaml`，不要沿用上次摘要。
- 同名旧增强文件还在，但新导入 profile 没绑定它。
- `script` 环境不一定能读本地文件。需要跨订阅复制节点时，更稳的是把选中节点写进 `proxies` 增强文件。
- 一个落地节点如果要走两个不同前置，应该创建两个同参数、不同 `dialer-proxy` 的代理条目。
- 进程匹配可能误伤。`PROCESS-NAME,claude.exe` 会覆盖桌面 Claude、Claude Code、VS Code 插件里的 Claude。
- PowerShell 处理 emoji 和中文时容易受编码影响。脚本文件建议 UTF-8 with BOM；读写配置文件用 UTF-8。
- 命名管道临时切换必须用 `finally` 恢复并复查，不能只假定 PUT 已成功。
