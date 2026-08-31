<div align="right">
  <details>
    <summary>🌐 Language</summary>
    <div>
      <div align="center">
        <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=en">English</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=zh-CN">简体中文</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=zh-TW">繁體中文</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=ja">日本語</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=ko">한국어</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=fr">Français</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=de">Deutsch</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=es">Español</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=pt">Português</a>
        | <a href="https://openaitx.github.io/view.html?user=eze-is&project=web-access&lang=ru">Русский</a>
      </div>
    </div>
  </details>
</div>

<img width="879" height="376" alt="image" src="https://github.com/user-attachments/assets/a87fd816-a0b5-4264-b01c-9466eae90723" />

<p align="center">
  <b>给 AI Agent 装上完整联网能力的 Skill。</b><br/>
  <a href="https://web-access.eze.is">🌐 官网</a> · <a href="https://mp.weixin.qq.com/s/rps5YVB6TchT9npAaIWKCw">📖 设计详解</a> · <a href="#安装">⚡ 快速安装</a>
</p>

AI Agent 原本的联网能力（WebSearch、WebFetch）缺少调度策略和浏览器自动化能力。这个 Agent Skill 补上的是：**联网策略 + CDP 浏览器操作 + 站点经验积累**。兼容所有支持 SKILL.md 的 Agent（Claude Code、Cursor、Gemini CLI、Codex CLI 等）。

> **本地修订 dual-proxy.2**：在上游 v2.5.3 与 dual-proxy.1 基础上，保留 Edge（固定 3456）和 Chrome（固定 3457）双长期 Proxy，并新增唯一生产配置、单实例并发复用、task/token 隔离、AX snapshot/ref、结构化 action、wait/dialog、用户接管和敏感操作确认。

> 推荐必读：[Web Access：一个 Skill，拉满 Agent 联网和浏览器能力](https://mp.weixin.qq.com/s/rps5YVB6TchT9npAaIWKCw) ，完整介绍了 Web-Access Skill 的开发细节与 Agent Skill 设计哲学，帮助你也能写出类似通用、高上限的 Skill

---

## dual-proxy.2 能力

| 能力 | 说明 |
|------|------|
| 联网工具自动选择 | WebSearch / WebFetch / curl / Jina / CDP，按场景自主判断，可任意组合 |
| 双长期 CDP Proxy | Edge 固定 3456、Chrome 固定 3457；所有生产副本复用同一配置和现有兼容进程，不使用备用端口 |
| task/token 隔离 | 每个对话创建独立 task，只能看到和控制自己创建的 tab 及 popup；不列出或接管用户 tab |
| AX snapshot/ref | 默认读取交互式可访问性树，以短 ref 定位元素；动态重绘后重新 snapshot |
| 结构化交互 | 支持 `click`、`fill`、`type`、`press`、`check`、`uncheck`、`select`、`hover`，动作后回读验证 |
| 等待与接管 | 等 selector/text/URL/load；密码、MFA、验证码和 SSO consent 交给用户完成，handoff 期间禁止页面访问 |
| 安全确认 | 敏感信息首次输入及提交、发送、上传、付款、删除、授权、账号变更前确认 |
| 本地浏览器书签/历史检索 | `find-url.mjs` 跨 Chrome / Edge 查询公网搜不到的目标（内部系统）或用户访问过的页面，支持关键词/时间窗/访问频度排序 |
| 并行分治 | 多目标可并行；同一浏览器共享 Proxy，但 task、token、tab 和 ref 互相隔离 |
| 站点经验积累 | 按域名存储操作经验（URL 模式、平台特征、已知陷阱），跨 session 复用 |
| 媒体提取 | 从 DOM 直取图片/视频 URL，或对视频任意时间点截帧分析 |

`dual-proxy.2` 使用 `/v2` API。旧无版本操作路由返回 `410 LEGACY_API_DISABLED`；迁移见 [`references/migration-dual-proxy.2.md`](references/migration-dual-proxy.2.md)。

**v2.5.2 更新：**
- **Microsoft Edge 支持** — CDP Proxy 不再绑定 Chrome，新增 Edge 适配（及 Chromium、Chrome Canary 等 Chromium 系，通过同一套自动发现机制接入）。在 `edge://inspect/#remote-debugging` 勾选 "Allow remote debugging for this browser instance" 即可
- **浏览器偏好持久化** — 新增 `config.env`（gitignored，首次运行从模板创建），通过 `WEB_ACCESS_BROWSER` 固定默认浏览器；多浏览器同时开启 toggle 时 Agent 会询问偏好。也支持单次覆盖 `--browser <chrome|edge>`
- **不擅自降级** — 偏好/指定的浏览器没启动或没开 toggle 时硬错并给出明确处理步骤，不会悄悄连到别的浏览器；proxy 首次成功连接后 pin 住浏览器 id，避免运行中漂移
- **find-url 也支持 Edge** — 本地书签/历史检索默认遍历 Chrome 与 Edge，可用 `--browser <chrome|edge>` 限定单一浏览器

<details><summary>v2.5.0 更新</summary>

- **本地 Chrome 资源检索** — 新增 `scripts/find-url.mjs`，从本地 Chrome 书签/历史按关键词/时间窗/访问频度定位 URL。典型场景：用户提到组织内部系统（"我们的 XX 平台"等公网搜不到的目标）、回查之前访问过但不记得地址的页面、查看最近高频访问网站等（场景感谢 @MVPGFC 在 #60 提出）
</details>

<details><summary>v2.4.3 更新</summary>

- **修复 CLAUDE_SKILL_DIR 路径问题** — bash 代码块改用 `${CLAUDE_SKILL_DIR}` 字符串替换语法，修复 Windows Git Bash 路径转换错误和变量未设置问题（#47 #46）
- **站点经验列表合并到前置检查** — 启动检查通过后自动输出已有站点经验列表，移除不可靠的 `!` 内联注入
</details>

<details><summary>v2.4.1 更新</summary>

- **跨平台支持** — 脚本从 bash 迁移到 Node.js，Windows / Linux / macOS 均可使用
- **DOM 边界穿透** — 新增技术事实：eval 递归遍历可穿透 Shadow DOM、iframe 等选择器不可跨越的边界
</details>

<details><summary>v2.4 更新</summary>

- **站点内 URL 可靠性** — 新增事实说明：站点生成的链接自带完整上下文，手动构造的 URL 可能缺失隐式必要参数
- **平台错误提示不可信** — 新增技术事实：平台返回的"内容不存在"等提示可能是访问方式问题而非内容本身问题
- **小红书站点经验增强** — xsec_token 机制、创作者平台状态校验、暂存草稿流程
</details>

<details><summary>v2.3 更新</summary>

- **浏览哲学重构** — 更清晰的「像人一样思考」框架，强调目标驱动而非步骤驱动
- **Jina 积极推荐** — 明确鼓励在合适场景主动使用 Jina 节省 token
- **子 Agent prompt 指引优化** — 明确加载写法，增加避免动词暗示执行方式的说明
</details>

## 安装

**方式一：npx skills 一键安装（推荐）**

```bash
npx skills add eze-is/web-access
```

> [skills CLI](https://github.com/vercel-labs/skills) 是开源的 Agent Skill 包管理器，自动检测你的 Agent 环境并安装到正确位置。

**方式二：让 Agent 自动安装**

```
帮我安装这个 skill：https://github.com/eze-is/web-access
```

**方式三：Plugin 安装（Claude Code）**

```bash
claude plugin marketplace add https://github.com/eze-is/web-access
claude plugin install web-access@web-access --scope user
```

**方式四：手动**

```bash
git clone https://github.com/eze-is/web-access ~/.claude/skills/web-access
```

## 前置配置（CDP 模式）

CDP 模式需要 **Node.js 22+** 和浏览器（Chrome / Edge）开启远程调试：

1. 在你想用的浏览器地址栏打开对应 inspect 页面：
   - Chrome：`chrome://inspect/#remote-debugging`
   - Edge：`edge://inspect/#remote-debugging`
2. 勾选 **Allow remote debugging for this browser instance**（可能需要重启浏览器）

### 唯一生产配置与固定端口

源码、CC Switch、Claude 和 Codex 的技能副本统一读取 `%LOCALAPPDATA%\web-access\config.env`。首次运行会原子创建该文件；各技能目录中的 `config.env` 不再作为生产配置来源：

```bash
# 未显式指定时默认使用 Edge
WEB_ACCESS_BROWSER=edge

# 生产端口固定，防止不同技能副本各起一份 Proxy
WEB_ACCESS_EDGE_PORT=3456
WEB_ACCESS_CHROME_PORT=3457
```

`WEB_ACCESS_BROWSER` 合法值为 `chrome` / `edge`。生产配置中的端口必须保持 `3456/3457`；同名环境变量只有与固定值相等时才兼容，不能用于另起备用端口。临时端口仅供仓库测试脚本在系统临时目录下以 `WEB_ACCESS_TEST_MODE=1` 隔离使用。

**本次使用 Chrome**（不修改默认浏览器，也不停止 Edge Proxy）：

```bash
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser chrome --json
```

**同时检查两个浏览器**：

```bash
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --all --json
```

两个浏览器会分别建立一个 Proxy/CDP WebSocket。Edge 的授权绑定当前浏览器实例和长期 Proxy 连接：Edge 与 `3456` 上的正式 Proxy 都保持存活时，所有技能副本和后续对话都会复用这条连接，每个对话只新建自己的 task，通常只需点击一次“允许对此浏览器实例进行远程调试”。关闭 Edge、停止正式 Proxy、迁移旧 Proxy 或连接断开重建后，才可能再次提示。

若同一 Edge 实例中反复提示授权，先检查是否有第二个 Proxy 进程或备用端口也在连接同一个 Edge CDP。不要靠再分配端口“解决”端口占用；并发启动的输家应核验 `3456` 上现有 Proxy 的协议、浏览器和能力后直接退出并让调用方复用它。

环境检查（Agent 运行时会自动完成前置检查，无需手动执行）：

```bash
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --json
# $CLAUDE_SKILL_DIR 是 skill 加载时自动设置的环境变量
# 手动运行请替换为实际路径，如 ~/.claude/skills/web-access
```

## CDP Proxy API

Proxy 通过 WebSocket 直连浏览器（兼容 `chrome://inspect` / `edge://inspect` 方式，无需命令行参数启动），只绑定 `127.0.0.1`，提供 task-scoped `/v2` HTTP API：

```bash
# 启动/复用 Edge；Chrome 改用 --browser chrome
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --json

# 使用 check-deps 输出的 proxy-url；Chrome 默认为 http://127.0.0.1:3457
WEB_ACCESS_PROXY="http://127.0.0.1:3456"

# 协议与能力
curl -s "${WEB_ACCESS_PROXY}/health"
curl -s "${WEB_ACCESS_PROXY}/capabilities"

# 创建 task，保存响应中的 taskToken；不要回显
curl -s -X POST "${WEB_ACCESS_PROXY}/v2/tasks" \
  -H "Content-Type: application/json" -H "Idempotency-Key: TASK_KEY" \
  -d '{"label":"current-user-request"}'

# 创建 task 自有 tab
curl -s -X POST "${WEB_ACCESS_PROXY}/v2/tabs" \
  -H "Authorization: Bearer TASK_TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: TAB_KEY" -d '{"url":"https://example.com"}'

# snapshot/ref 操作
curl -s -H "Authorization: Bearer TASK_TOKEN" \
  "${WEB_ACCESS_PROXY}/v2/tabs/TARGET_ID/snapshot?mode=interactive"
curl -s -X POST "${WEB_ACCESS_PROXY}/v2/tabs/TARGET_ID/action" \
  -H "Authorization: Bearer TASK_TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: ACTION_KEY" \
  -d '{"action":"click","ref":"r4"}'
```

每个 task 只能控制自己创建的 tab 和 popup。active task 30 分钟无操作后过期；自建 tab 闲置 15 分钟后自动关闭。Proxy 重启会清空 token、归属和 ref，但保留浏览器 tab并把它们降为用户 tab。完整契约见 [`references/cdp-api.md`](references/cdp-api.md)。

## ⚠️ 使用前提醒

通过浏览器自动化操作社交平台存在账号被限流或封禁的风险。敏感信息首次输入，以及最终提交、发送、发布、上传、付款、删除、授权和账号变更前必须确认；密码、MFA、验证码和 SSO consent 统一由用户接管输入。

## 使用

安装后直接让 Agent 执行联网任务，skill 自动接管：

- "帮我搜索 xxx 最新进展"
- "读一下这个页面：[URL]"
- "去小红书搜索 xxx 的账号"
- "帮我在创作者平台发一篇图文"
- "同时调研这 5 个产品的官网，给我对比摘要"

## 设计哲学

> Skill = 哲学 + 技术事实，不是操作手册。讲清 tradeoff 让 AI 自己选，不替它推理。

详见 [SKILL.md](./SKILL.md) 中的浏览哲学部分。

## License

MIT · 作者：[一泽 Eze](https://github.com/eze-is) · [官网](https://web-access.eze.is)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=eze-is/web-access&type=Date)](https://star-history.com/#eze-is/web-access&Date)

## Clawhub Download History

[![Download History](https://skill-history.com/chart/eze-is/web-access.svg)](https://skill-history.com/eze-is/web-access)

<img width="1280" height="306" alt="image" src="https://github.com/user-attachments/assets/2afa25c2-3730-413e-b40f-94e52567249d" />
