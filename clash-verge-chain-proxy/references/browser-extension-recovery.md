# 浏览器扩展恢复

只处理目标浏览器、profile 和扩展；通用范围、授权和刷新规则见 [技能入口](../SKILL.md)。

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

持久规则写进当前 profile 绑定的 `rules` 增强文件，不直接改生成的 `clash-verge.yaml`。写入前备份 `profiles.yaml`、对应增强文件，以及排障所需的浏览器 profile 文件；涉及关闭或重启时，按 [入口的刷新与重启规则](../SKILL.md#刷新与重启) 核对必要性、已有授权和用户窗口。

### 修复后验证

按以下顺序验收：

1. 增强文件包含新增域名规则。
2. `clash-verge-check.yaml` 和 `clash-verge.yaml` 已重新生成并包含规则。
3. `verge-mihomo.exe -t -f <generated-config>` 通过语法检查。
4. 服务日志显示目标域名和浏览器进程命中预期分组及代理链。
5. 按已授权范围触发目标扩展更新，确认目标扩展启用、`disable_reasons` 不再包含 `1024`，且 `corrupted_disable_count` 不再增加；不默认关闭或重启浏览器。

一次更新成功只证明当前更新通过。故障涉及重启后复发，或用户要求重启后稳定性时，仍需完成重启后复查；先说明影响并保护用户窗口，复用准确授权。当前不适合重启时，将该部分标为未验证，已完成的局部检查照常交付。若计数继续增加，保留备份并继续查下载重定向域名、代理切换和 Edge/Chromium 自身的完整性判断。


## Edge/Google 搜索位置联合验收

搜索城市、账号位置来源和代理出口的分层判断沿用 [搜索位置参考](google-search-location.md)；仅在该类任务中读取，不附加到普通扩展更新或下载排障。
