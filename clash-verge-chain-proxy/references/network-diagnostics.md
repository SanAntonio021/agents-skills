# 网络诊断

只执行当前故障相关的步骤；通用范围、授权和刷新规则见 [技能入口](../SKILL.md)。

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

HTTP 代理、Fake-IP DNS、接口绑定与 TUN 路由分别检查；绕过 HTTP 代理或命中 DIRECT 不能证明绕过 TUN。
门户配置、PktMon 双向观察点、任务权限及冷启动分级统一按 [本地认证门户](local-auth-portal.md) 执行，仅在门户任务中读取。

### 临时手机共享的接口跃点

Windows 先选最长前缀，再在同样精确的路由中选择“路由跃点 + 接口跃点”更小者。界面中的
“接口跃点”是路由成本，不是实际经过的路由器数量。

用户只在少量时间接入手机，但要求手机接入时承担公网出口，可以只把手机共享网卡的 IPv4 接口跃点
固定为低于有线网当前值的数；有线网保持自动跃点和连接状态。手机断开后，其默认路由消失，有线网
自然接管。不要为此默认拔网线、禁用有线网卡或删除有线网默认网关。

执行前记录基线，核对已有授权是否覆盖本次网络改动和短时连接切换；范围已明确则直接继续：

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


## 单域名下载与连接诊断

只检查当前失败的进程、入口及重定向域名。区分 DNS、连接、TLS 握手、HTTP 状态和正文传输阶段，记录耗时及实际代理路径；收到重定向或响应头不能证明压缩包已下载完整。

- 用同一时段日志核对当前请求命中的规则、组和节点。HTTP 代理、环境变量和 TUN 分开判断；所谓直连需要说明绕过了哪一层。
- 按当前故障选择必要对照；查看 GitHub 网页不自动触发 Git 推送测试，下载失败不自动检查全部节点、AI 服务或故障转移。
- 只读请求保持只读，不修改系统代理、分组或节点。已有修复授权只覆盖相关目标；临时切换沿用上面的并发检查和恢复步骤。
- 可重复读取的临时错误按 web-access 的当前重试流程处理；同错持续出现先诊断，恢复后继续原任务。
