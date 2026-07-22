---
name: clash-verge-chain-proxy
disable-model-invocation: true
description: >
  在 Windows 上处理 Clash Verge Rev 的链式代理、前置节点、订阅增强配置和 AI 分流。遇到
  Clash Verge、Mihomo、dialer-proxy、前置节点、良心云/Flower/Nov 这类多订阅链式代理、AI
  站点分流、订阅重导入后配置丢失、节点或分组在 UI 不显示、增强文件没有生效、需要确认日志里真实走哪条链，
  或 Edge/Chrome 扩展修复后很快又显示损坏、扩展商店更新异常时，优先使用本技能。
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

再建两个手动选择组：

- `<Flower front group>`：放 Flower 订阅里可用的前置节点。
- `<normal front group>`：放当前普通订阅里可用的前置节点。

这样用户可以在 UI 里手动换前置，不需要重新改 YAML。

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

合格信号：

- AI 域名或 `claude.exe`：`using <AI group>[<Nov via Flower>]`
- 普通国外流量：`using <normal group>[<Nov via normal front>]`
- 国内或原本直连流量：`using DIRECT`

如果 `clash-verge.yaml` 仍是旧内容，说明增强文件已改但 Verge 还没重新生成。先重启 Clash Verge GUI；服务重启可能需要管理员权限，不要在无权限时反复硬停服务。

## 安全边界

- 不把真实订阅 URL、节点密码、UUID、落地代理账号写进回复或 skill。
- 不直接改 `.cc-switch`、`.codex`、`.claude` 运行时 skill 目录；改源码目录后通过同步工具分发。
- 不把含凭据的恢复脚本提交到公开仓库。
- 不只改 `clash-verge.yaml` 就宣称完成持久化。
- 不只看 UI 显示；必须用最终 YAML 和日志验证。
- 不默认修改无关订阅。

## 常见坑

- `current` profile 变了。先看 `profiles.yaml`，不要沿用上次摘要。
- 同名旧增强文件还在，但新导入 profile 没绑定它。
- `script` 环境不一定能读本地文件。需要跨订阅复制节点时，更稳的是把选中节点写进 `proxies` 增强文件。
- 一个落地节点如果要走两个不同前置，应该创建两个同参数、不同 `dialer-proxy` 的代理条目。
- 进程匹配可能误伤。`PROCESS-NAME,claude.exe` 会覆盖桌面 Claude、Claude Code、VS Code 插件里的 Claude。
- PowerShell 处理 emoji 和中文时容易受编码影响。脚本文件建议 UTF-8 with BOM；读写配置文件用 UTF-8。
