# 本地认证门户独立访问

## 何时读取

本机自动登录程序需要访问校园网、企业网或其他私网认证门户，且 Clash Verge/Mihomo 开启 Fake-IP、
TUN `auto-route` 或接口绑定 DNS 时，使用本检查表。目标是让门户访问不依赖代理核心是否先启动，
同时把持久配置、当前运行态和真实冷启动三种证据分开。

## 先区分四个控制面

- HTTP/WinINET 代理绕过只控制显式代理；它不阻止 TUN 接管。
- `DOMAIN,<portal-host>,DIRECT` 是 Mihomo 内部规则；流量仍可能先经过 Fake-IP DNS 和 TUN。
- `fake-ip-filter` 决定门户是否得到真实地址，而不是 Fake-IP 地址。
- `route-exclude-address` 决定真实门户地址是否绕过 TUN，直接交给物理网卡路由。

因此只加 `DIRECT` 或只加一个门户 IP 的 `/32` 都可能不完整。配置范围必须来自当前域名解析、门户部署
和用户确认；不要把一次观察到的地址或网段写成通用常量。

## 配置前检查

1. 读取当前 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\profiles.yaml`，确认 `current`、当前
   profile UID，以及它绑定的 `merge`、`rules` 和 `script`。
2. 读取自动登录程序当前配置，取得真实门户域名；用当前校内网络确认其地址、所需 CIDR、校内 DNS
   和物理接口名称。
3. 备份 `profiles.yaml`、三个目标增强文件和两份生成 YAML，逐文件记录 SHA-256。备份和正式修改都
   不得输出订阅 URL、代理凭据或 controller secret。
4. 记录 Clash 服务状态、核心 PID、系统代理开关、目标任务状态和当前门户诊断结果，作为前后对照。

## 持久配置

在当前 profile 的持久化增强源中建立以下组合；不要直接编辑订阅原始 YAML 或生成 YAML：

1. 在 `script` 生成的 `dns.fake-ip-filter` 中让 `<portal-host>` 精确出现一次。若增强模式不是
   `fake-ip`，不要机械加入此项。
2. 在 `dns.nameserver-policy` 中为 `<portal-host>` 设置校内 DNS，并用 Mihomo 支持的接口后缀绑定
   当前物理接口，例如 `udp://<campus-dns>:53#<physical-interface>`。发现已有冲突 policy 时失败关闭，
   不静默覆盖。
3. 在 `rules` 增强文件的高优先级位置让 `DOMAIN,<portal-host>,DIRECT` 精确出现一次。
4. 在 `merge` 的 `tun.route-exclude-address` 中写入已经确认的 `<portal-cidr>`。不要为了方便扩大网段，
   也不要改系统默认路由、禁用网卡或删除网关。

重新生成后验证：

- 两份生成 YAML 都包含同一组门户声明，目标条目唯一；
- 除获批声明外没有结构漂移；
- 两份 `verge-mihomo.exe -t` 均通过；
- 当前核心 `/configs` 中能看到的 TUN 排除项正确。该接口可能省略完整 DNS 段，缺少 `dns` 键时回到
  最终 YAML 和真实抓包，不把缺失字段当成未加载，也不直接索引空值。

## 不再次重启核心的 DNS 取证

核心已经稳定加载目标配置后，不要仅为制造一次 DNS 查询再次重启服务。按以下顺序验证：

1. 确认 `pktmon` 没有活动会话或他人过滤器；记录物理接口对应的 PktMon component ID。
2. 只为获批的校内 DNS 添加 UDP/53 过滤器并开始抓包。抓包启动、停止和过滤器清理必须由同一个
   脚本管理，并在 `finally` 中执行 `pktmon stop` 和过滤器移除。
3. 运行 `Clear-DnsClientCache` 清 Windows DNS Client 缓存，再通过现有命名管道 controller 调用
   `POST /cache/dns/flush` 清 Mihomo 的运行态 DNS 缓存。只接受成功状态；不得删除或修改 `cache.db`，
   也不得打印 controller secret。
4. 立即对 `<portal-host>` 发起一次 A 记录查询，等待应答后停止抓包并转换 ETL。
5. 在同一次捕获中同时确认：
   - 查询名精确为 `<portal-host>`，不是其他域名；
   - 至少有一个发往获批校内 DNS 的请求和对应应答；
   - 门户请求与应答的 component ID 都属于目标物理接口；
   - 系统答案是预期的真实门户地址，不落入当前配置的 Fake-IP 地址段。

只抓到其他域名访问校内 DNS，只能证明校内 DNS 可达，不能证明门户 `nameserver-policy` 生效。门户查询
仍完全命中缓存、没有目标上游包或没有应答时，报告“接口绑定证据不足”，不把配置存在或一次解析成功
写成运行态通过。是否回滚按本次已批准方案执行，不为补证据擅自清理持久缓存或破坏在线服务。

## 路由与自动登录验收

1. 对真实门户地址运行 `Find-NetRoute -RemoteIPAddress <portal-ip>`。该命令可为一个目标返回源地址对象
   和路由对象等多条结果；检查相关对象都指向预期物理接口，不要求“返回对象数等于目标地址数”。
2. 查询自动登录状态与健康检查，至少确认在线状态、门户错误、状态 API 和 challenge API。
3. 对 SYSTEM 开机任务使用提升权限的 `Get-ScheduledTask` 核对任务存在、状态和 Action。普通权限的
   `schtasks` 看不到任务，或工具返回 `Windows PowerShell task operation was rejected`，都不能单独
   证明任务被删除。
4. 复核核心 PID 和系统代理前后未变化；确认 PktMon 已停止且测试过滤器为空。临时抓包和结果文件按
   本次清场授权处理，不能因为测试完成就自动删除。

## 完成状态

- **持久配置通过**：增强源、两份生成 YAML 和 Mihomo 语法检查一致。
- **当前运行态通过**：门户 DNS 请求与应答、真实地址、物理路由、自动登录状态和任务状态均通过。
- **真实冷启动通过**：实际重启后没有手动启动客户端或任务，以上运行态证据仍成立。

真实重启暂时不方便时，可以结束本轮实施并明确写“冷启动验收延期”，不能把它升级成冷启动通过。
