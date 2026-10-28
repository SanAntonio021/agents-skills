# web-access

统一的联网与本地浏览器技能。普通搜索和静态读取优先使用现有工具；登录态、动态页面和交互流程默认通过 Broker 控制当前运行的 Edge。Windows 默认使用 `existing` 模式，CDP 端口由 `DevToolsActivePort` 运行时发现，Broker Proxy 为 `3456`；每个任务使用独立 task、token 和后台标签页。

技能入口是 [SKILL.md](SKILL.md)。完整 CDP 细节按任务拆分在 [浏览器参考](references/cdp-api.md)，不需要每次全部读取。

## 快速开始

要求 Node.js 22 或更新版本。

通过 CC Switch 添加公开仓库 `SanAntonio021/agents-skills`，启用 `web-access` 即可。需要机构论文下载时，同时安装同仓库的 `paper-download`。

检查当前 Edge 并确保 Broker 可用：

```powershell
node scripts/check-deps.mjs --browser edge --mode existing --json
```

正常结果需要 `ready:true`，并且本轮控制探针通过。只查看状态、不启动或修复：

```powershell
  node scripts/check-deps.mjs --browser edge --mode existing --status-only --json
```

`--status-only` 不创建或迁移 `config.env`。`--no-probe` 只用于隔离测试。

## 当前 Edge

| 项目 | 默认值 |
|---|---|
| 模式 | `existing` |
| CDP 端口 | 从 `DevToolsActivePort` 发现 |
| Broker Proxy | `127.0.0.1:3456` |

- 任务在后台新建标签页，不切换或修改用户现有页面；结束时只关闭本任务页面。
- 复用当前 Edge 内的已有登录态；不复制或导出浏览器 Profile、密码库、Cookie 或认证令牌。
- `managed` 保留为显式隔离模式，不作为默认或自动回退。
- 任务结束调用 `complete keep:false`，只关闭本 task 的 tab/popup；不停止 Broker、不关闭 Edge 或其他任务页面。
- CDP 恢复先重读 `DevToolsActivePort`、核验监听进程并尝试 WebSocket。`/json/version` 的 HTTP 404 不等于 CDP 失败。

## 主要能力

- 搜索、网页读取、正文受阻后的浏览器切换。
- 多对话 task/token/tab 隔离，共享当前 Edge 与长期 Proxy。
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
- 浏览器控制只操作本 task 后台创建的页面；不改变已有用户标签页。

## 来源与许可

MIT。上游项目：[eze-is/web-access](https://github.com/eze-is/web-access)。本地维护版通过 [SanAntonio021/agents-skills](https://github.com/SanAntonio021/agents-skills) 分发；来源与历史记录集中维护在 [upstream-sources.md](references/upstream-sources.md)。
