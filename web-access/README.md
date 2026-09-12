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

这个 Skill 是统一联网入口，按当前任务选择搜索、正文读取或真实浏览器操作。普通读取被拦截、只有页面框架或缺少目标正文时，Agent 判断原因后自动转浏览器；已知需要登录状态、动态内容或交互时直接使用浏览器。普通搜索和不依赖浏览器的读取不检查或启动浏览器。

它保留现有浏览器会话、CDP 操作及按需读取的站点经验，兼容支持 SKILL.md 的 Agent（Claude Code、Cursor、Gemini CLI、Codex CLI 等）。真实浏览器可以处理部分普通抓取无法访问的页面，仍可能遇到站点检测、验证码或权限限制；取得所需正文和核验实际操作结果才算完成。

> **本地修订 dual-proxy.2**：在上游 v2.5.3 与 dual-proxy.1 基础上，保留 Edge（固定 3456）和 Chrome（固定 3457）双长期 Proxy，并新增唯一生产配置、单实例并发复用、task/token 隔离、AX snapshot/ref、结构化 action、wait/dialog、用户接管和敏感操作确认。

> 推荐必读：[Web Access：一个 Skill，拉满 Agent 联网和浏览器能力](https://mp.weixin.qq.com/s/rps5YVB6TchT9npAaIWKCw) ，完整介绍了 Web-Access Skill 的开发细节与 Agent Skill 设计哲学，帮助你也能写出类似通用、高上限的 Skill

---

## dual-proxy.2 能力

| 能力 | 说明 |
|------|------|
| 联网工具自动选择 | 选择当前可用的搜索、正文读取或浏览器工具；普通读取不足时自动转浏览器，已知动态或登录需求直接访问 |
| 双长期 CDP Proxy | Edge 固定 3456、Chrome 固定 3457；所有生产副本复用同一配置和现有兼容进程，不使用备用端口 |
| task/token 隔离 | 每个对话创建独立 task，只能看到和控制自己创建的 tab 及 popup；不列出或接管用户 tab |
| AX snapshot/ref | 默认读取交互式可访问性树，以短 ref 定位元素；动态重绘后重新 snapshot |
| 结构化交互 | 支持 `click`、`fill`、`type`、`press`、`check`、`uncheck`、`select`、`hover`，动作后回读验证 |
| 等待与接管 | 等 selector/text/URL/load；密码、MFA、验证码和 SSO consent 交给用户完成，handoff 期间禁止页面访问 |
| 授权复用 | 敏感信息及提交、发送、上传、付款、删除、授权、账号变更核对准确目标与已有授权，缺失或变化时才询问 |
| 本地浏览器书签/历史检索 | `find-url.mjs` 跨 Chrome / Edge 查询公网搜不到的目标（内部系统）或用户访问过的页面，支持关键词/时间窗/访问频度排序 |
| 并行分治 | 多目标可并行；同一浏览器共享 Proxy，但 task、token、tab 和 ref 互相隔离 |
| 站点经验复用 | 按域名读取已有 URL 模式、平台特征与已知陷阱；只有用户要求维护时才更新 |
| 媒体提取 | 从 DOM 直取图片/视频 URL，或对视频任意时间点截帧分析 |

`dual-proxy.2` 使用 `/v2` API。旧无版本操作路由返回 `410 LEGACY_API_DISABLED`；迁移见 [`references/migration-dual-proxy.2.md`](references/migration-dual-proxy.2.md)。

以下是上游历史更新；当前本地操作以 [技能入口](SKILL.md) 和 [浏览器参考](references/cdp-api.md) 为准。

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

## 浏览器配置与 API

选择 CDP Proxy 后才检查 Node.js 22+、浏览器调试开关与 `/v2` 协议。生产副本统一使用 `%LOCALAPPDATA%\web-access\config.env`，Edge / Chrome Proxy 端口固定为 `3456` / `3457`，复用现有兼容进程。

- [启动与浏览器选择](references/cdp-api.md#启动与浏览器选择)：前检命令、配置、固定端口和授权连接复用。
- [页面观察与导航](references/cdp-api.md#页面观察与导航)：snapshot/ref、导航、等待和能力限制。
- [文件与媒体资源入口](references/cdp-api.md#文件与媒体资源入口)：服务器字节、图片像素和截图的选择。
- [登录与用户接管](references/cdp-api.md#登录与用户接管)、[并行任务与收尾](references/cdp-api.md#并行任务与收尾)：task 隔离与生命周期。
- [完整端点协议](references/cdp-api.md#连接与通用规则) 和 [旧版本迁移](references/migration-dual-proxy.2.md)：请求、响应和恢复规则。

每个 task 只操作自己创建的 tab 和 popup；保留用户原有页面和正在运行的浏览器。密码、MFA、验证码、SSO consent 和歧义账号选择仍由用户接管。外部写入核对准确授权，已有授权范围内不重复确认；只说明当次需要用户了解的影响或需要其完成的动作，不照抄固定风险声明。

## 使用

安装后直接让 Agent 执行联网任务，skill 自动接管：

- "帮我搜索 xxx 最新进展"
- "读一下这个页面：[URL]"
- "去小红书搜索 xxx 的账号"
- "帮我在创作者平台发一篇图文"
- "同时调研这 5 个产品的官网，给我对比摘要"

## 设计哲学

> Skill = 哲学 + 技术事实，不是操作手册。讲清 tradeoff 让 AI 自己选，不替它推理。

按目标选择最短可行路径，并根据实际内容调整；详见 [联网工具选择](./SKILL.md#联网工具选择) 和 [页面观察与导航](references/cdp-api.md#页面观察与导航)。

## License

MIT · 作者：[一泽 Eze](https://github.com/eze-is) · [官网](https://web-access.eze.is)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=eze-is/web-access&type=Date)](https://star-history.com/#eze-is/web-access&Date)

## Clawhub Download History

[![Download History](https://skill-history.com/chart/eze-is/web-access.svg)](https://skill-history.com/eze-is/web-access)

<img width="1280" height="306" alt="image" src="https://github.com/user-attachments/assets/2afa25c2-3730-413e-b40f-94e52567249d" />
