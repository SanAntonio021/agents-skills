---
name: clash-verge-chain-proxy
description: 在 Windows 上处理 Clash Verge Rev 中现有订阅的链式代理、前置节点、AI 分流和增强配置。Use when 用户要把单独购买的节点接入现有订阅、调整 `dialer-proxy` 前置节点、排查节点或分组在 UI 不显示、确认链式代理是否真的生效，或修复 `merge/proxies/groups/rules/script` 这些增强配置没有生效的问题；prefer this over 通用代理建议 when 工作目标是 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev`。
---

# Clash Verge 链式代理

## 作用

这份 skill 负责处理 Clash Verge Rev 里“现有订阅 + 单独购买节点 + 链式代理 + 前置节点 + AI 分流 + 增强配置”的排查和修改。

重点不是泛谈代理原理，而是先找清楚：当前订阅到底读了哪些文件、该改哪一层、以及配置写完后有没有真的生效。

## 流程

1. 先锁定目标订阅和文件位置。
   优先读取 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\profiles.yaml`，确认当前启用的是哪个订阅，以及它绑定了哪些 `merge / proxies / groups / rules / script` 文件。
2. 先判断该改哪一层：
   - 节点增删优先看 `proxies`
   - 分组增删优先看 `groups`
   - 整段覆盖或更大范围合并优先看 `merge`
   - 域名、进程或 AI 分流优先看 `rules`
   - 订阅更新后仍要持续生效、且需要改运行期结果时，优先考虑 `script`
3. 如果用户明确说“当前网络不要断”，先离线修改非当前订阅，再做本地校验，不先切换活跃订阅。
4. 给单个订阅接入链式代理时，优先使用该订阅内独立的节点名和前置组名，避免和别的订阅串名。
5. 需要在 UI 里看到新节点时，显式检查三件事：
   - 新节点是否真的进入最终 `proxies`
   - 目标组是否真的引用了它
   - 订阅刷新后计数是否按预期变化
6. 验证是否真的生效时，按固定顺序查：
   - `profiles.yaml`
   - `clash-verge-check.yaml` 或 `clash-verge.yaml`
   - `logs/service/service_latest.log`
   只看 UI 不算最终验证。

## 稳定判断

- `clash-verge.yaml` 是当前实际生效配置的证据，但不是长期唯一配置源。
- `clash-verge-check.yaml` 更适合快速看“当前实际生成出的组、节点和规则长什么样”。
- 如果实际生效配置里还原样出现 `prepend / append / delete`，通常说明当前订阅并没有按你以为的格式读取增强文件。
- 如果日志里已经出现 `using <组名>[<节点名>]` 这样的完整命中记录，才算链式代理真的跑起来了。
- AI 分流要把“分流命中”与“链式出口”拆开验证，不要看到进了 AI 组就默认前置链条也正确。

## 全量前置测试

- 前置节点推荐不能只靠抽样。少量候选只能给临时判断；真正要给默认推荐时，先从原始订阅枚举全部真实节点，再做统一出口下的全量扫描。
- 做前置对比时，固定同一个最终落地，只更换前置；不固定出口时，结果不可比。
- 默认按两阶段执行：
  1. 全量首筛：所有候选先跑一轮轻量探测，快速筛掉弱节点。
  2. 前排复测：把首筛前排再跑多轮，记录成功率、均值、P95、最坏延迟和最长连续失败。
- 复测不能只看全局前几名，还要强制带上“每个供应商内部最好的代表”，避免最后只是在比较同一家供应商内部。
- 不要为了全量扫描去改当前正在使用的主配置。优先从当前 `clash-verge.yaml` 派生临时 `mihomo` 实例，再通过 `external-controller` 在 `GLOBAL` 下切换候选做测试。
- AI 连通性测试不要用首页型重页面当主指标。像 `chatgpt.com` 首页这类目标会把页面加载时间和链路稳定性混在一起；优先轻量 AI 端点，配合短超时和流式请求测试。
- Windows 下批量改含 emoji 的 YAML 节点名或分组名时，先确认 UTF-8 和完整 Unicode 代理对；文件“看着改了”不等于分组引用仍然能准确匹配。
- 抽样结论和全量结论冲突时，默认以后者为准，并同步更新默认项和备用项；不要继续沿用旧的经验推荐。
- 全量首筛后，不需要把全部候选都做 `15` 分钟长测。默认先取前 `5-6` 个，再按需要补一两个跨供应商代表做 soak；这样既能控制总时长，也足够把默认项和备用项排出来。
- `15` 分钟长测的目的不是再筛“能不能通”，而是重排默认顺序。优先让多个 AI 端点交替循环，并继续记录成功率、均值、P95、最坏延迟和最长连续失败，而不是只看平均延迟。
- 全量短测的第一名不保证在 `15` 分钟长测里仍然第一。默认项、候选顺序和 UI 预选值，最终以长测结果为准，不以首筛名次为准。
- 某个供应商的代表节点在短测里看着没问题，也可能在长测里出现很长的连续失败；一旦出现这种情况，就不要继续把它留在 AI 默认前置里，最多降成备用，必要时直接移出前排候选。
- 地区直觉不可靠。真实结果里，最优前置可能来自意料之外的区域，某家供应商内部最稳的节点也不一定是香港或日本，所以不要凭地理位置先入为主。
- 给用户的最终建议至少拆成两档：
  - 默认：综合成功率、延迟和连续失败后的第一名
  - 备用：同一供应商内的后备节点，或另一供应商里最稳的代表
- 如果这轮长测只覆盖了 AI 前置，就只改 `AI流量` 这类组的默认项和排序；不要把 AI 长测结论直接外推到普通流量组。

## 边界

- 不默认修改与目标订阅无关的其他订阅。
- 不假设 `merge / proxies / groups / rules / script` 五类文件都用同一种格式。
- 不只改 `clash-verge.yaml` 就宣称完成持久化，除非用户明确只要临时生效。
- 不把敏感账号、密钥、订阅链接或真实节点信息写进 skill 正文。
- 不把“节点没进 proxies”和“节点没被组引用”混成一个问题。
- 不把 UI 显示正确误判成链式代理已经真实生效。

## 相关技能

- Windows 命令复用：[../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
- Windows 命令护栏：[../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)
- 对话经验提取：[../duihua-jingyan-tiqu/SKILL.md](../duihua-jingyan-tiqu/SKILL.md)
- 本地 skill 维护：[../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)

## 维护

- 如果 Clash Verge Rev 后续调整 `profiles.yaml` 结构或增强文件语义，优先更新这里的“文件职责判断”部分。
- 如果后续仍稳定复用 `profiles.yaml -> clash-verge-check.yaml / clash-verge.yaml -> service_latest.log` 这条验证链，就保持它为默认验证路径，不退回只看 UI。
