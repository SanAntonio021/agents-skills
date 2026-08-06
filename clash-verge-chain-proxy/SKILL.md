---
name: clash-verge-chain-proxy
disable-model-invocation: true
description: >
  在 Windows 上处理 Clash Verge Rev 的链式代理、前置节点、订阅增强配置和 AI 分流。遇到
  Clash Verge、Mihomo、dialer-proxy、前置节点、良心云/Flower/Nov 这类多订阅链式代理、AI
  站点分流、fallback 健康探测、自动故障转移、订阅重导入后配置丢失、节点或分组在 UI 不显示、
  增强文件没有生效、生成脚本覆盖增强组、需要确认日志里真实走哪条链，Edge/Chrome 扩展修复后很快又
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

## 双层自动故障转移

当用户要求“前置节点自动选健康节点，AI 链路在两个前置之间自动切换”时，使用两层 `fallback`，不要把裸前置组直接放进 AI 组：

```yaml
proxies:
  - name: <Nov via Flower>
    type: socks5
    server: <landing-host>
    port: <landing-port>
    username: <landing-user>
    password: <landing-password>
    dialer-proxy: <Flower front fallback>

  - name: <Nov via normal front>
    type: socks5
    server: <landing-host>
    port: <landing-port>
    username: <landing-user>
    password: <landing-password>
    dialer-proxy: <normal front fallback>

proxy-groups:
  - name: <Flower front fallback>
    type: fallback
    url: https://www.gstatic.com/generate_204
    interval: 30
    timeout: 5000
    max-failed-times: 2
    lazy: false
    proxies: [<Flower node 1>, <Flower node 2>]

  - name: <normal front fallback>
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
    proxies:
      - <Nov via Flower>
      - <Nov via normal front>
```

探测配置属于 `proxy-groups`，不是单个 `proxies` 条目：

- 两个内层 `fallback` 组探测各自的前置候选；`now` 会落到第一个健康候选。
- 外层 AI `fallback` 探测两条完整链路，先检查 Flower 链路，再检查普通前置链路。
- `fallback` 是优先级故障转移，不是测速选最快；候选顺序决定主备顺序。
- `lazy: false` 让备用候选持续探测；不把 `DIRECT` 放进 AI 组时，双链路都失败就保持失败。
- `url` 只验证通用 HTTPS 出口，不等价于 ChatGPT 或 Anthropic 专项可用；最终验收仍需发起目标域名请求并查日志。

增强文件改完后，必须检查当前 profile 绑定的 `script`。后处理脚本可能在合并完成后用 `upsertGroup` 重建同名 AI 组，把 `fallback` 覆盖回 `select`。最终生成的 `clash-verge.yaml` 和 `clash-verge-check.yaml` 才是验收对象，不直接编辑它们作为长期修复。

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

### 双层 `fallback` 验收

1. 用 YAML 解析器确认两个前置组和 AI 组各出现一次；确认 AI 候选只有两条完整链路，且没有 `DIRECT`。
2. 确认两条落地代理的 `dialer-proxy` 分别指向两个前置 `fallback` 组；确认三个组的 `url`、`interval`、`timeout`、`max-failed-times`、`lazy` 均在最终生成配置中。
3. 通过 `external-controller-pipe` 查询 `/version` 和 `/proxies`，只汇总目标组的 `now`、候选 `all`、`alive`、`history`，不打印 `secret`、密码、UUID 或完整代理对象。
4. 受控测试优先使用运行态已经标记 `alive: false` 的候选。不要为了制造故障去破坏线上节点；没有安全失败候选时，复制最小配置到临时目录，关闭 TUN、使用独立 controller 端口，在隔离配置中让一个候选失效，再确认 AI 组切换到备用完整链路。
5. 测试结束后确认运行态 selector 没有被临时 PUT 覆盖；隔离进程、临时配置和日志清理前先展示清场预览。

合格信号：

- AI 域名或 `claude.exe`：`using <AI group>[<Nov via Flower>]`
- 普通国外流量：`using <normal group>[<Nov via normal front>]`
- 国内或原本直连流量：`using DIRECT`

如果 `clash-verge.yaml` 仍是旧内容，说明增强文件已改但 Verge 还没重新生成。先重启 Clash Verge GUI；服务重启可能需要管理员权限，不要在无权限时反复硬停服务。

## 安全边界

- 不把真实订阅 URL、节点密码、UUID、落地代理账号写进回复或 skill。
- 不输出 Mihomo controller secret，也不把它放进进程命令行或日志。
- 不直接改 `.cc-switch`、`.codex`、`.claude` 运行时 skill 目录；改源码目录后通过同步工具分发。
- 不把含凭据的恢复脚本提交到公开仓库。
- 不只改 `clash-verge.yaml` 就宣称完成持久化。
- 不只看 UI 显示；必须用最终 YAML 和日志验证。
- 受控故障测试不人为破坏线上节点；隔离配置不得复用线上 controller pipe 或 TUN。
- 不默认修改无关订阅。

## 常见坑

- `current` profile 变了。先看 `profiles.yaml`，不要沿用上次摘要。
- 同名旧增强文件还在，但新导入 profile 没绑定它。
- `script` 环境不一定能读本地文件。需要跨订阅复制节点时，更稳的是把选中节点写进 `proxies` 增强文件。
- 一个落地节点如果要走两个不同前置，应该创建两个同参数、不同 `dialer-proxy` 的代理条目。
- 进程匹配可能误伤。`PROCESS-NAME,claude.exe` 会覆盖桌面 Claude、Claude Code、VS Code 插件里的 Claude。
- PowerShell 处理 emoji 和中文时容易受编码影响。脚本文件建议 UTF-8 with BOM；读写配置文件用 UTF-8。
- 命名管道临时切换必须用 `finally` 恢复并复查，不能只假定 PUT 已成功。
