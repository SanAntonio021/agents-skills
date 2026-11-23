# 机构联合登录（SAML / Shibboleth / CARSI）

先读 [生命周期参考](cdp-lifecycle.md#登录与用户接管)。本页说明出版商机构登录链路上的属性释放同意页怎样在后台处理，以及名单怎样维护。

## 授权来源与边界

2026-11-22 用户明确授权：向学术出版商或数据库释放非个人的机构属性，属于常规登录步骤，同类页面以后在后台自动处理，不再停下来询问。

授权只覆盖以下情况，其他数据共享和法律承诺仍按原授权规则处理：

- **页面**：同意页位于 HTTPS 的机构 IdP origin，且是 Shibboleth 或 uApprove 的属性释放表单。结构不明的通用页面只在 IdP 已列入名单时才处理。
- **服务提供商**：页面上显示的服务名称和本任务标签此前到过的主机，都必须对应名单里的同一个服务提供商。只出现名称、或只来自其主机，都不算。
- **属性**：只限身份类别或从属关系（`eduPersonAffiliation`、`eduPersonScopedAffiliation`）、所属机构（`o`、`schacHomeOrganization`）、匿名或定向标识（`eduPersonTargetedID`、`pairwise-id`）。按属性 ID 判断；没有 ID 时按“身份类别”“所属机构”等显示名判断。认不出的 ID 一律不自动释放。
- **记住选择**：只选“仅对此服务记住，信息变化时再询问”（Shibboleth 的 `_shib_idp_rememberConsent`）。“以后对所有服务都不再询问”会把同意扩大到名单外的服务，不选；页面只有这一种记住选项时，直接同意、不记住，返回 `rememberMode:"global_only_skipped"`。

以下情况停下交给用户，返回 `state:"attribute_consent_required"`、`handoffRequired:true` 及原因：

| `reason` | 含义 |
|---|---|
| `personal_attributes` | 请求了姓名、邮箱、学号或工号、手机号等个人属性，`blockedCategories` 给出类别 |
| `attributes_not_allowed` | 请求了权限声明（entitlement）或认不出的属性 |
| `sp_unverified` | 服务提供商不在名单中，或本标签不是从该服务提供商来的 |
| `idp_unverified` | 页面 origin 与标签不一致，或结构不明且 IdP 不在名单中 |
| `attributes_unparsed` | 页面结构解析不出可靠的属性清单 |
| `ambiguous_form`、`ambiguous_accept`、`insecure_form` | 表单不唯一、找不到唯一的“同意”按钮，或不是同源 HTTPS POST |
| `already_attempted` | 本任务已在这一页同意过一次，不重放 |

返回值只含属性类别和服务提供商 ID，不含属性值。

## 链路与 `maxSteps`

`POST /v2/tabs/{targetId}/access` 带 `maxSteps`（1–6，默认 1）时，Broker 在一次请求里依次处理：同意页 → 等页面跳转（含 SAML 自动提交页）→ 密码页（浏览器自动填充或[本机凭据助手](cdp-lifecycle.md#本机凭据助手)）→ 等页面跳转 → 回到服务提供商。每一步之后重新判断页面，所以同意页出现在密码页之前或之后都能处理。步数用完时只观察、不再动作。结果附 `steps`，列出每步的 `state` 和 `loginMethod`。

UESTC 的实际顺序没有在真实页面上核实。按 Shibboleth IdP 的常规流程，`idp-lib.uestc.edu.cn` 先把认证交给统一身份认证 `idas.uestc.edu.cn`，登录后再显示属性释放同意页；浏览器里已有 idas 登录会话时会直接跳过密码页，看起来像先到同意页。两种顺序都已用合成页面测试。

## 名单维护

名单在 [federated-providers.json](federated-providers.json)，分为 `serviceProviders`、`discoveryServices` 和 `identityProviders`，每项写 `id`、`names`（页面上显示的服务名）和 `hosts`（主机，含子域）。本机补充写在 `%LOCALAPPDATA%\web-access\federated-providers.local.json`，结构相同，条目追加到公开名单后。`autoConsentCategories` 只能从上述三类里选，写入其他类别会被忽略。

新增出版商时，同时写它的显示名和主机；名称太泛（如单个常见词）时，靠主机历史约束，不必删名称。
