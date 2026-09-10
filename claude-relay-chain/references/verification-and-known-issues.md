# 验证与已知问题

## 范围与授权

按当前问题选择检查。诊断授权包含必要的非计费只读请求；用户明确要求不联网或仅查本地时遵从。
计费请求按已确定的目标、模型、次数和费用上限执行，不重复确认同一范围；缺少必要授权才询问，
并继续其余可做的检查。凭据仅在进程内使用，不写入命令行、日志或输出文件。

## 验证层级

### 1. 静态配置

按目标对象记录适用字段，独立 Claude Code 不附带检查无关 Desktop profile：

- 目标表面：独立 Claude Code、VS Code 扩展、Desktop Cowork 或 Desktop 内置 Code。
- Desktop 配置源：HKLM、HKCU 或 local `configLibrary`。
- applied profile ID 与名称。
- CC Switch 当前 provider ID、名称、`direct`/`proxy`、`apiFormat`、route 数量。
- 实际 base URL；删除 query、fragment 和 user-info 后再输出。
- credential 只报 `present` / `absent`。

### 2. 本地服务

本地路由模式要求 CC Switch 对预期端口监听。默认是 `127.0.0.1:15721`，但以 DB `proxy_config` 为准。

端口监听只证明进程可接收连接，不证明 provider、认证或协议可用。

### 3. 模型发现

按当前配置选取实际使用的发现路径或显式列表；两者均涉及时分别核对：

```text
GET <gateway-base>/v1/models
显式 inferenceModels
```

通过标准：

- HTTP 成功。
- 响应结构是当前 Claude Desktop 接受的模型列表。
- 至少一个模型 ID 可识别为 Claude，或带正确的 `anthropic_family_tier`。
- Desktop 模型选择器显示预期模型。

如果 gateway 不支持 `/v1/models`，可建议显式 `inferenceModels`；已有修改授权且后台接口支持时写入完整上游模型 ID。不要用无法在无 discovery 情况下解析的裸 `sonnet` / `opus` tier alias。

### 4. Messages API

最小请求应包含：

```json
{
  "model": "<approved-model>",
  "max_tokens": 32,
  "stream": true,
  "messages": [
    {"role": "user", "content": "Reply exactly RELAY_OK"}
  ]
}
```

Desktop 从 applied profile 读取 `inferenceGatewayApiKey` 和 `inferenceGatewayAuthScheme`；独立 Code 使用已核实的对应认证来源。在内存中构造 `Authorization: Bearer` 或 `x-api-key` header，不把 header 展开到 `curl.exe` 命令行。

通过标准：

- HTTP 200。
- streaming 返回有效 Anthropic SSE 事件。
- 最终文本是预期短回复。
- 错误时只报告 HTTP 状态、最短错误类型和 request ID；不输出完整 body。

### 5. Tool use

工具调用故障或完整 Code 链路验收时，使用无副作用工具定义发起最小请求，确认：

- request 接受 `tools`。
- response 返回结构化 `tool_use` block。
- 把 `tool_result` 送回后可继续生成。
- streaming 情况下 tool block 增量可正确组装。

启用 Desktop `toolSearchEnabled` 前，先确认 gateway 接受相应 `anthropic-beta` headers 和 beta request fields；否则可能返回 HTTP 400。

### 6. 用户可见端到端

- Desktop：验证任务涉及的 Cowork 或内置 Code；两者均在范围内才分别验证。需要重载时沿用入口的运行任务保护和授权要求，正常退出重开。
- 独立 CLI：新建 `claude` 会话或一次最小 `claude -p`，不要复用可能缓存旧环境的会话。
- VS Code：新建会话；仍使用旧配置时重载扩展宿主后再测。

配置保存可单独确认；只有所要求的目标应用实际成功，才写该链路可用。局部检查不冒充完整验收。

## 结果解释

| `/v1/messages` | `/v1/models` | 判断 |
|---|---|---|
| 成功 | 成功 | 对应接口通过；任务要求完整 Code 链路时继续 tool use 和目标应用 |
| 成功 | 失败 | 推理可用，模型发现独立故障；检查 namespace、格式或显式 `inferenceModels` |
| 失败 | 成功 | 模型列表不能证明推理；检查认证、上游 API 格式、model route 和 streaming |
| 失败 | 失败 | 先区分监听、profile、managed policy 和 provider 状态，不立即改 key |

## CC Switch 已知问题核对

### #4540：Model discovery 路径与返回格式

- 地址：https://github.com/farion1231/cc-switch/issues/4540
- 2026-07-24 状态：`Open`。
- 报告版本：CC Switch `3.16.3`，Windows。
- 典型现象：普通聊天或 Cowork 可用，内置 Code 无模型，配置页显示 `Invalid: Model list`。
- 关键证据：根 `GET /v1/models` 可能返回 `{"models":[]}` 或带内部字段的非兼容结构；`GET /claude-desktop/v1/models` 可能返回不同且可用的结构。
- 判断方法：检查 applied base URL、Desktop 日志中的 `non-array data` / `picker = 0`、本机路由和当前版本；必要的非计费只读 endpoint 检查复用诊断授权，明确禁止网络请求时仅分析已有资料。

### #4415：模型列表合成与 1M context

- 地址：https://github.com/farion1231/cc-switch/issues/4415
- 2026-07-24 状态：`Closed`，作者标记为 `Duplicate of #4353`。
- 报告版本：CC Switch `3.16.3`，macOS；问题机制仍可能影响其他平台和后续版本，必须用本机证据判断。
- 典型现象：proxy 的根 `/v1/models` 返回空列表；Messages 正常；route 中 `supports1m=true`，但 Desktop 仍只显示 200k context。
- issue 页面关联过修复提交，用于合成 `[1m]` model variants 和 `inferenceModels`。有提交或 issue 关闭不等于当前安装版本已经包含并正确应用修复。
- 判断方法：检查 route 的 `supports1m`、返回模型 ID、`context_window`、显式 `inferenceModels` 和 Desktop 模型选择器。不要把普通模型发现成功等同 1M context 正确。

### 报告要求

这些是带日期的历史候选。症状相关且本地资料仍不能解释问题时，核对适用候选的当前状态、版本与日志，
简短说明是否吻合及依据；无关编号不必列出。不能复制旧日期状态当作当前结论。

## 回滚验收

确需回滚时，仅通过支持该动作的接口恢复本次授权对象，并检查适用项：

1. 备份哈希与恢复对象对应。
2. DB 可打开，原 provider current 状态恢复。
3. Desktop `_meta.json.appliedId` 恢复。
4. 需要重载且具备条件时，正常退出重开后核对目标应用使用原 profile；尚未重载时如实标注。
5. 不保留打印过的凭据、临时请求文件或带 credential 的 shell history。
