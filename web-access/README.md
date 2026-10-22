# web-access

统一的联网与本地浏览器技能。普通搜索和静态读取优先使用现有工具；登录态、动态页面和交互流程通过受管 Edge Broker 执行。Windows 默认使用独立 Profile、CDP `9222` 和 Proxy `3456`，多个对话共享同一浏览器但各自使用独立 task、token 和标签页。

技能入口是 [SKILL.md](SKILL.md)。完整 CDP 细节按任务拆分在 [浏览器参考](references/cdp-api.md)，不需要每次全部读取。

## 快速开始

要求 Node.js 22 或更新版本。

通过 CC Switch 添加公开仓库 `SanAntonio021/agents-skills`，启用 `web-access` 即可。需要机构论文下载时，同时安装同仓库的 `paper-download`。

首次浏览器任务按需启动受管 Edge：

```powershell
node scripts/check-deps.mjs --browser edge --mode managed --json
```

正常结果需要 `ready:true`，并且本轮控制探针通过。只查看状态、不启动或修复：

```powershell
node scripts/check-deps.mjs --browser edge --mode managed --status-only --json
```

`--status-only` 不创建或迁移 `config.env`。`--no-probe` 只用于隔离测试。

## 受管 Edge

| 项目 | 默认值 |
|---|---|
| Profile | `%LOCALAPPDATA%\web-access\managed-edge-profile` |
| CDP | `127.0.0.1:9222` |
| Broker Proxy | `127.0.0.1:3456` |
| 状态文件 | `%LOCALAPPDATA%\web-access\managed-edge-state.json` |

- 首次任务启动 Edge 和 Proxy；后续任务复用同一实例与 CDP 连接。
- 学校、CARSI、OpenAthens、MFA 和验证码由用户在页面完成；工具不读取或保存密码、Cookie 或认证令牌。
- 任务结束调用 `complete keep:false`，只关闭本 task 的 tab/popup；不停止 Broker、不关闭 Edge 或其他任务页面。
- 关闭受管 Edge 后，下次 `ensure` 使用同一 Profile 重启；登录 Cookie 随 Profile 持久化。
- 日常 Edge/Chrome 只在人工明确指定 `--mode existing` 时使用；受管模式失败不会自动回退。

## 主要能力

- 搜索、网页读取、正文受阻后的浏览器切换。
- 多对话 task/token/tab 隔离，共享一个受管 Edge 与长期 Proxy。
- AX snapshot/ref、结构化 click/fill/type/press/check/select/hover、wait 和 dialog。
- 用户登录/接管、表单写入保护、敏感操作授权和完整结果回读。
- 书签/历史定位、服务器文件字节取回、图片像素导出、截图和 iframe 正文。
- 本地站点经验与旧 Proxy 迁移说明。

## 文档入口

- [技能正文](SKILL.md)：联网工具选择、失败处理、授权与完成条件。
- [CDP 入口](references/cdp-api.md)：按任务选择下一篇参考。
- [生命周期与任务隔离](references/cdp-lifecycle.md)：启动、恢复、并发、登录交接和收尾。
- [协议参考](references/cdp-protocol.md)：健康、能力、task/tab、错误码和隔离边界。
- [交互参考](references/cdp-interaction.md)：页面观察、动作、等待、dialog 和本地历史。
- [内容提取](references/cdp-content.md)：PDF/二进制、图片、截图和 iframe。
- [旧 Proxy 迁移](references/migration-dual-proxy.2.md)。

## 边界

- 只复用用户合法拥有的浏览器会话和机构权限，不绕过出版社访问控制。
- task token 只用于减少多个对话之间的误操作，不是本机安全边界。
- 受管启动和修复只使用全局锁；正常页面操作通过独立 task/token 并发。
- 端口或 Profile 被其他程序占用时报告具体状态，不结束用户进程、不创建备用端口。
- 首版稳定并发保证只覆盖 Windows 受管 Edge；Chrome 保留显式 `existing` 模式。

## 来源与许可

MIT。上游项目：[eze-is/web-access](https://github.com/eze-is/web-access)。本地维护版通过 [SanAntonio021/agents-skills](https://github.com/SanAntonio021/agents-skills) 分发；来源与历史记录集中维护在 [upstream-sources.md](references/upstream-sources.md)。
