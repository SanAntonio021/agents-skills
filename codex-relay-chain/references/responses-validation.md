# Responses SSE 验证

按 [技能入口](../SKILL.md) 选择所需检查。静态配置查询不自动触发本节；新增请求、重试和对照实验沿用明确的测试范围及费用上限，已有适用日志可复用。

不要用 `/v1/models` 判断 Codex 是否可用。它只能初筛，不能证明 Responses 流和 reasoning 字段可用。

使用真实 `stream=true` 的 `/v1/responses`，并用 list-form input，避免 CodexCont 把字符串 input 拆成字符。

请求形态示例，模型与推理强度按本次已授权目标替换，不把示例模型固定为探测默认值：

```json
{
  "model": "gpt-5.5",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "解这个小题，最后只给答案和极简验证：三个正整数互不相同，和为 41，乘积为 1716。求这三个数。"
        }
      ]
    }
  ],
  "reasoning": {
    "effort": "high"
  },
  "include": ["reasoning.encrypted_content"],
  "stream": true,
  "store": false
}
```

除非目标 provider 已单独验证，否则最小健康探测不要加入 `max_output_tokens`；部分中转会直接返回不支持参数的 `400`。
简单回显任务可能不生成 reasoning item，即使线路正常也看不到 `encrypted_content`。验证这两个字段时使用
上面的非平凡小题，并显式加入 `include = ["reasoning.encrypted_content"]`。

#### 严格校验流式文本与终态文本

不能只检查 HTTP 状态、事件名和字段是否存在。对本节预期返回文本的探测，按 SSE 事件顺序收集全部
`response.output_text.delta` 的 `delta` 并直接拼接；再从 `response.completed` 的
`response.output` 中按顺序提取全部 `output_text.text` 并拼接。两侧必须逐字符完全一致，不能先
`Trim`、折叠空白、去重句段或只做包含关系比较。

任一侧缺失或两侧冲突时，即使 HTTP 为 `200` 且 `response.created`、`response.completed` 都存在，
仍判为 Responses SSE 协议不一致，并保留最短错误类型，例如
`SSE terminal output conflicts with streamed text`。不要为了提高有效样本数而放宽解析器。

#### 并发和探针内容的控制实验

批量探测无有效样本时，不要先归因于并发数或探针内容。先保留失败请求的端点、模型、prompt、
reasoning effort、`include`、`stream`、`store`、超时和其他请求形态，关闭重试，以 `worker = 1`
重复取得原始样本：

1. 单 worker 仍稳定出现同类 HTTP、SSE 或文本一致性错误时，不能写成“8 并发限制”；优先归为
   上游或中转的协议/传输异常，再按三层链路定位。
2. 只有单 worker 对照通过，而提高 worker 后可重复失败，并且状态码、连接重置、超时或限流证据
   随并发变化时，才把并发容量列为候选原因。
3. 判断探针内容是否触发异常时，先完成上述同请求对照，再把 prompt 换成最简单的固定回显，其他字段
   保持不变。简单回显仍出现同类终态/增量冲突时，不能归因于原探针题目；HTTP `200` 也不能推翻该结论。

合格信号：

- HTTP `200`
- `Content-Type` 包含 `text/event-stream`
- SSE 里有 `event: response.created`
- SSE 里有 `event: response.completed`
- body 里有 `"type":"reasoning"`
- body 里有 `encrypted_content`
- body 里有 `reasoning_tokens`
- `full` 模式下 body 里有 CodexCont 注入的 `proxy_rounds`；`ccswitch-only` 缺失是预期结果
- 如可见，body 里有 `proxy_billed_usage`

不合格信号和含义：

- `401 Invalid API key`：优先查 provider key 和 `proxy_live_backup`。
- `reasoning_tokens` 缺失：中转可能没有完整保留 Responses usage。
- `encrypted_content` 缺失：中转或代理可能过滤了 reasoning 加密内容。
- `full` 模式下 `proxy_rounds` 缺失：请求可能没经过 CodexCont，或 CodexCont 没正常处理；`ccswitch-only` 下缺失正常。
- `response.completed` 终态文本与全部 `response.output_text.delta` 拼接文本不一致：中转返回了
  自相矛盾的 Responses SSE，不能计为有效样本。

目标是“OAuth 登录 + 中转请求”时，SSE 通过后还要运行一次真实 `codex exec`。只有
`codex login status` 为 ChatGPT、CLI 显示目标 `custom` provider、返回预期文本，且 CC Switch
请求日志记录当前 provider HTTP 200，才证明身份和请求线路同时成立。

### 上游 502/503/524 的归因

本地返回 `502`、`503` 或 `524` 时，不要先把错误归因给 CodexCont 或 CC Switch。
先区分“本机进程不可用”和“本地代理转发了远端错误”：

1. 测试前后记录 `8787`、`15721` 的监听 PID、进程启动时间，以及 Codex 和 CodexCont 的固定 URL。
2. 从当前 provider 的结构化配置解析真实远端 `base_url`，不要从 provider 名称猜地址。
3. 用同一模型、同一 list-form input、`stream=true`、`store=false` 的最小请求，按当前模式选择实际存在的层做对照；不为了凑齐三层启用已停用的代理：
   - `http://127.0.0.1:8787/v1/responses`：完整本地链路；
   - `http://127.0.0.1:15721/v1/responses`：绕过 CodexCont；
   - 当前 provider 的远端 `/v1/responses`：绕过两个本地代理。
4. 间歇性问题按已有测试授权安排交替对照；资料已足够就停止，不固定追加 3 轮。每次只报告 HTTP 状态、耗时、`Content-Type`、`Server`、
   `cf-ray` 是否存在、`cf-error-type`/`cf-error-origin` 是否存在和最短错误类型，不输出完整 key 或 SSE body。

如果 CC Switch 已开启自动故障转移，同时读取 `proxy_config.auto_failover_enabled`、
`providers.in_failover_queue` 和 `proxy_request_logs`，记录每次本地请求实际使用的 provider；
否则备用 provider 可能把主 provider 的故障隐藏掉。诊断期间不要为了“证明故障”临时改写故障转移状态。

判断规则：

- `8787` 或 `15721` 未监听、连接被拒绝：本机服务故障。此时还没有到达远端，不能写成上游 `502/524`。
- 本地和远端直连返回同一 `503`：上游 provider 故障。
- 远端直连返回 `524`，响应是 Cloudflare 错误页且耗时接近默认 `120` 秒：远端源站响应超时；可参考 [Cloudflare Error 524](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/)。
- 远端直连出现 `524`，而本地 `8787`/`15721` 返回 `200`：上游存在间歇性故障，本地转发路径在该次测试中可用；不能因为一次本地成功就否定远端超时。
- CC Switch 日志写明“上游 HTTP 502/524”，同时记录远端 URL 和 HTML 错误页：优先判定为远端错误被转发。本轮远端直连未复现时，只写“高度疑似”，不要写成已完全证实。
- 远端直连正常、本地链路失败：继续查 CodexCont、CC Switch 转发、live backup、回环地址和本机代理配置。
- 本地链路返回 `200` 但 SSE 字段缺失：继续按 Responses 兼容性检查，不把它归为可用。

目标 provider 故障且已有切换或恢复可用链路授权时，通过受支持后台入口切回已验证的备用 provider；只读诊断给出建议，不自动切换。
切回后核对 `currentProviderCodex`、`is_current` 和当前模式对应的 Codex `base_url`，并在测试授权内验证 Responses SSE。

### 上游修复权限与可完成性

确定故障在中转站、网关程序或远端协议实现后，在承诺“直接升级”“修复”或“监控后自动处理”前，
先确认当前实际能操作哪一类控制面。能管理账号不代表能改变正在运行的服务：

1. **账号管理面**：例如 `/admin/users`、余额、分组、额度和 key 页面。它只能证明可以管理租户或账号，
   不能证明可以替换服务版本、重启实例或回滚。
2. **服务部署面**：例如服务器 SSH、Docker/Kubernetes、部署面板、CI/CD、镜像版本、运行日志和回滚入口。
   把上游修复部署到实际中转站至少需要这一层权限。
3. **源码维护面**：例如目标仓库、fork、PR、合并和 release 权限。能准备补丁或跟踪 issue，仍不等于
   已把修复部署到用户正在使用的服务。

只有当前代理或用户能进入所需控制面、能确认目标版本或提交，并能在升级后重跑真实 Codex/Responses
请求时，才可以说能够直接完成上游升级。只有账号管理页时，不把它描述为服务器管理入口，也不通过修改
无关的本地 provider、用户分组或额度配置来掩盖协议实现缺陷。

缺少部署或源码发布权限时，把终态写成“诊断完成，修复受外部部署或源码权限阻塞”，并说明应由谁部署
哪个修复、部署后用什么请求验收。上游 issue 已关闭也不等于用户正在使用的实例已经升级。

监控只能发现 issue、release 或服务版本的状态变化，并在触发后提醒或续接诊断；它不会获得服务器权限，
也不能代替部署和验收。只有用户明确认可“仅提醒”的价值并同意触发条件与续接方式后才创建。用户认为
提醒没有价值或明确结束任务时，不创建或继续监控，更不能把监控包装成后续自动修复。
