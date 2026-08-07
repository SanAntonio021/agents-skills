# 浏览器技能来源调研清单

调查日期：2026-08-06

## 使用边界

- 本文件属于 dual-proxy.2 隔离候选，不等于正式来源登记。
- 只有下列“采纳候选”在候选评测通过、用户再次批准后，才创建 zero-exposure mirror 并写入正式来源注册表。
- “reference-only”只记录设计对照和排除理由，不建 mirror、不进入每周检查。
- 本地实现只吸收行为思想，代码和文字从头实现；不复制上游实现。
- 正式登记后，每个来源的 `adopted` 范围保持互不重叠，避免同一改动被多个上游重复驱动。

## 现有基线

### `eze-is/web-access`

- 仓库：`https://github.com/eze-is/web-access.git`
- 路径：`.`；入口：`SKILL.md`
- 已接受提交：`7af34af6a25940d917905f0e5f2a7ef056952971`
- 已接受版本：`2.5.3`
- 许可证：MIT（声明于 `SKILL.md` 和 `README.md`）
- 状态：已登记 confirmed source；本次保持 accepted commit 不变
- 已采用范围：联网策略、CDP 基础操作、浏览器发现、站点经验和 dual-proxy.1 的本地延伸基线

## 采纳候选

这些项目只在 dual-proxy.2 通过评测并再次获批后登记。

### Microsoft Playwright CLI

- 仓库：`https://github.com/microsoft/playwright-cli.git`
- 固定提交：`ca196c297169a494ee5517584883eada60dc8d0e`
- 上游路径：`skills/playwright-cli`
- 入口与跟踪：`skills/playwright-cli/SKILL.md`、`skills/playwright-cli/references/`
- 许可证：Apache-2.0
- 候选 mirror：`microsoft-playwright-cli`
- 拟采用：snapshot/ref 生命周期和元素动作语义
- 不采用：Playwright runtime 本身、独立浏览器 Profile、trace/HAR/network interception、自动安装
- 2026-08-06 节奏证据：仓库近 90 天 14 次提交；目标路径 3 次，最近 2026-07-09
- 更新策略：正式登记后每周 review；固定提交之外的变化只生成隔离报告

### Browser Use 主技能

- 仓库：`https://github.com/browser-use/browser-use.git`
- 固定提交：`a3e3cc5dd11dd219884532fd37d67775cd66c74d`
- 上游路径：`skills/browser-use`
- 入口与跟踪：`skills/browser-use/SKILL.md`
- 许可证：MIT
- 候选 mirror：`browser-use-browser-use`（与下一条共用一个 zero-exposure mirror）
- 拟采用：登录门、用户接管、密码/MFA/授权停止边界和动作后验证
- 不采用：云浏览器、远程代理、凭据 vault、验证码处理、Cookie 导出和反检测
- 2026-08-06 节奏证据：仓库近 90 天至少 100 次提交；目标路径 9 次，最近 2026-07-26
- 更新策略：正式登记后每周 review；固定提交之外的变化只生成隔离报告

### Browser Use Remote Browser 技能

- 仓库：`https://github.com/browser-use/browser-use.git`
- 固定提交：`a3e3cc5dd11dd219884532fd37d67775cd66c74d`
- 上游路径：`skills/remote-browser`
- 入口与跟踪：`skills/remote-browser/SKILL.md`
- 许可证：MIT
- 候选 mirror：`browser-use-browser-use`
- 拟采用：tab lock、task 所有权和多对话隔离思想
- 不采用：远程浏览器服务、会话托管和云端凭据
- 2026-08-06 节奏证据：目标路径近 90 天 0 次提交，最近变更 2026-03-25
- 更新策略：正式登记后每周 review；与主技能分别判断影响

### Vercel Agent Browser

- 仓库：`https://github.com/vercel-labs/agent-browser.git`
- 固定提交：`acbc22bdc5d4f6c5a88d97d4a4745d3c5eb0591f`
- 上游路径：`skills/agent-browser`
- 入口与跟踪：`skills/agent-browser/SKILL.md`、`skill-data/core/`
- 许可证：Apache-2.0
- 候选 mirror：`vercel-labs-agent-browser`
- 拟采用：不可信页面内容边界、CLI/技能能力握手和协议版本匹配
- 不采用：安装 agent-browser CLI、替换现有 CDP Proxy、独立浏览器 Profile
- 2026-08-06 节奏证据：仓库近 90 天 60 次提交；skill 入口 2 次；`skill-data/core` 25 次
- 更新策略：正式登记后每周 review；技能入口和 `skill-data/core/` 联合比较

## Reference-only 项目

下列项目已在 2026-08-06 用 GitHub commit、contents、path commits 和许可证原文做一次性核验，但本轮不建立正式上游关系，不建 mirror、不入周检。

| 项目 | 固定提交与精确入口 | 许可证与近 90 天节奏 | 可参考点 | 排除理由 |
|---|---|---|---|---|
| OpenAI Playwright | `openai/skills@49f948faa9258a0c61caceaf225e179651397431`；`skills/.curated/playwright/SKILL.md` | 目录内 Apache-2.0；路径 0 次，最近 2026-02-06 | CLI 表单、snapshot、截图和数据提取 | 与 Microsoft 正式候选重叠 |
| OpenAI Playwright Interactive | 同仓同提交；`skills/.curated/playwright-interactive/SKILL.md` | 目录内 Apache-2.0；路径 0 次，最近 2026-03-11 | 持久 REPL、功能/视觉 QA、QA inventory | 要求安装 Playwright 并关闭 sandbox，只作评测参考 |
| Microsoft Playwright MCP | `microsoft/playwright-mcp@4c5077651542f68525a0b51e97bab2a32abc9290`；入口 `cli.js`，`package.json` 注册 `playwright-mcp` | Apache-2.0；仓库 21 次 | AX snapshot、持久状态和结构化操作 | 官方 README 对 coding agent 也优先建议 CLI+SKILL；本轮明确不装 MCP |
| Ego Lite / Ego Browser | `citrolabs/ego-lite@f260b21761354ca0d2781ce750418305f16f8988`；`skills/ego-browser/SKILL.md` | MIT；目标路径 57 次 | task space、claim/handoff/takeover、登录态复用 | 替代浏览器/runtime，与当前本地 Proxy 重叠 |
| Browserbase Stagehand / Browse CLI | `browserbase/stagehand@7566804ed4b97649706782bccdcab5d80f6fe588`；`packages/cli/skills/browse/SKILL.md` | MIT；目标路径 12 次 | AX refs、selector、DOM、截图与 network capture | 云会话和模型驱动 runtime 超出本地 Proxy 范围 |
| BrowserAct | `browser-act/browseract-api-examples@3f14e981521a8153ffe1dc2655ef53ad52a4e004`；根 `README.md`；Java：`Scenarios-Java/README.md`、`Scenarios-Java/src/main/java/com/browseract/scenarios/Scenario1RunAndWait.java`、`Scenarios-Java/src/main/java/com/browseract/scenarios/Scenario2RunTemplateAndWait.java`；Node.js：`Scenarios-NodeJs/README.md`、`Scenarios-NodeJs/scenario1_runAndWait.js`、`Scenarios-NodeJs/scenario2_runTemplateAndWait.js`；Python：`Scenarios-Python/README.md`、`Scenarios-Python/scenario_1_run_and_wait.py`、`Scenarios-Python/scenario_2_run_template_and_wait.py` | MIT；路径 0 次，最近 2026-03-27 | SaaS workflow 的 run/wait/status 示例 | 没有 `SKILL.md`；未找到权限清单或敏感确认源码证据，不把这些能力归因给它 |
| Anthropic Webapp Testing | `anthropics/skills@b29e7cf65e5cb78a5ac33d582270551bc74a14eb`；`skills/webapp-testing/SKILL.md` | 目录内 Apache-2.0；路径 0 次，最近 2026-04-20 | reconnaissance-then-action、动态页面和 server 生命周期 | 面向本地 webapp QA，不驱动生产 Proxy |
| Anthropic Browser/Computer Use | `anthropics/claude-quickstarts@57336d30d71a9d0ec5cd42d69747b7ad6def9366`；`browser-use-demo/`、`computer-use-demo/`、`computer-use-best-practices/` | MIT；三路径近 90 天分别 1/2/1 次 | 显式工具、批处理、VM 隔离和安全警告 | 教学参考，明确非生产 SDK，且包含全桌面控制 |
| Firecrawl Search/Scrape | `firecrawl/firecrawl-claude-plugin@b1bd4442f4c935069ad83835c8eb69d7fe684db4`；`skills/firecrawl-search/SKILL.md`、`skills/firecrawl-scrape/SKILL.md` | 技能仓无 LICENSE；各路径 2 次。引擎 `firecrawl/firecrawl@0344bc87a64b455d6e06c7d1eb74ba5ebe007b1c` 为 AGPL-3.0，仓库至少 100 次 | 搜索、抓取和 JS 渲染路由 | 外部云服务、无本地登录态；技能仓许可证不明，不能登记或复制 |
| SawyerHood dev-browser | `SawyerHood/dev-browser@73fe10f045b9c872f963fe6168de4328857e38cf`；`skills/dev-browser/SKILL.md` | MIT；目标路径 1 次、仓库 8 次 | 持久页面、sandboxed JS 和 daemon | 替代 runtime，缺少 task token/所有权协议 |
| lackeyjb playwright-skill | `lackeyjb/playwright-skill@bb7e920d376022958214e349ef25498a2644e189`；`skills/playwright-skill/SKILL.md` | MIT；路径 0 次，最近 2025-12-19 | Playwright 表单和 QA 样例 | 更新停滞、非首选权威来源，且与 Microsoft/OpenAI 重叠 |

更新次数来自 2026-08-06 对 GitHub path commits 的只读统计；API 首页达到 100 条时只记“至少 100”，不伪造精确总数。

## 明确不吸收

- 云浏览器、远程代理或远程监听
- 验证码绕过、反检测或规避站点风控
- Cookie 导出、凭据采集或凭据 vault
- 自动安装、开机服务、自动批准、自动提交或自动推送
- 在首版加入 HAR、trace、network interception、下载管理或跨域 OOPIF ref

## 后续登记门

1. dual-proxy.2 候选与旧版完成隔离评测，完整回归连续通过 3 次。
2. 用户审查静态 viewer，并针对本技能给出一次明确批准。
3. 才创建 3 个 zero-exposure mirror、登记 4 条新正式来源。
4. 保留 `eze-is/web-access` 的 accepted commit，不把候选调研改写成已接受历史。
5. 正式应用后再经 CC Switch 同步，并核对源码、CC Switch、Codex、Claude 四层哈希。
