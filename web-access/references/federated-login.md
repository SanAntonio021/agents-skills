# 机构联合登录（SAML / Shibboleth / CARSI）

先读 [生命周期参考](cdp-lifecycle.md#登录与用户接管)。本页说明出版商机构登录链路上的属性释放同意页怎样在后台处理，以及名单怎样维护。

## 授权来源与边界

2026-11-22 用户明确授权：向学术出版商或数据库释放非个人的机构属性，属于常规登录步骤，同类页面以后在后台自动处理，不再停下来询问。

授权只覆盖以下情况，其他数据共享和法律承诺仍按原授权规则处理：

- **页面**：同意页位于 HTTPS 的机构 IdP origin，是以下两类之一。结构不明的通用页面和使用条款声明页，只在 IdP 已列入名单时才处理。
  - Shibboleth 或 uApprove 的属性释放表单（如 UESTC 的“信息发布”），按表单里的属性 ID 判断；
  - Shibboleth 使用条款声明页（如 CARSI 的“关于身份认证与隐私的声明”：一个“我同意此使用条款”复选框，“拒绝”在另一个表单）。这类页面不列属性表，按声明正文里写明的属性类别判断，并勾选同意框后提交。
- **服务提供商**：按以下顺序取证据，取到第一条就按它判断，结果里的 `spEvidence` 说明用了哪条：
  1. `saml_request_issuer`：本标签发往该 IdP 的 SAML 请求里的 SP entityID（HTTP-Redirect 的 `SAMLRequest` 解码后的 Issuer、HTTP-POST 正文、Shibboleth 1.x 的 `providerId`）。Broker 被动观察本标签的顶层文档请求取得，不保存请求本身。entityID 必须在名单里，且本标签到过该 SP 的主机；entityID 不在名单中时直接停下，不再看其他证据。
  2. `page_name_and_history`：页面显示的服务名对应名单中的一个 SP，且本标签到过该 SP 的主机。
  3. `navigation_history`：没有观察到 SAML 请求时，本标签进入 IdP 之前到过的最后一个主机（发现服务和学校登录主机除外）是名单中的 SP。
  三条都不满足（如来自名单外主机、或没有任何来源记录）时停下，返回 `sp_unverified` 和对应的 `spEvidence`。
- **属性**：只限身份类别或从属关系（`eduPersonAffiliation`、`eduPersonScopedAffiliation`）、所属机构（`o`、`schacHomeOrganization`）、匿名或定向标识（`eduPersonTargetedID`、`pairwise-id`）。按属性 ID 判断；没有 ID 时按“身份类别”“所属机构”等显示名判断。认不出的 ID 一律不自动释放。
- **记住选择**：只选“仅对此服务记住，信息变化时再询问”（Shibboleth 的 `_shib_idp_rememberConsent`）。“以后对所有服务都不再询问”会把同意扩大到名单外的服务，不选；页面只有这一种记住选项时，直接同意、不记住，返回 `rememberMode:"global_only_skipped"`。

以下情况停下交给用户，返回 `state:"attribute_consent_required"`、`handoffRequired:true` 及原因：

| `reason` | 含义 |
|---|---|
| `personal_attributes` | 请求了姓名、邮箱、学号或工号、手机号等个人属性，`blockedCategories` 给出类别 |
| `attributes_not_allowed` | 请求了权限声明（entitlement）或认不出的属性 |
| `sp_unverified` | 服务提供商不在名单中，或本标签不是从该服务提供商来的；`spEvidence` 给出原因（如 `saml_issuer_unlisted`、`came_from_unlisted_host`、`no_evidence`） |
| `idp_unverified` | 页面 origin 与标签不一致，或结构不明且 IdP 不在名单中 |
| `attributes_unparsed` | 页面结构解析不出可靠的属性清单 |
| `ambiguous_form`、`ambiguous_accept`、`insecure_form` | 表单不唯一、找不到唯一的“同意”按钮，或不是同源 HTTPS POST |
| `already_attempted` | 本任务已在这一页同意过一次，不重放 |

返回值只含 `consentType`（`attribute_release` 或 `terms_of_use`）、属性类别、服务提供商 ID 和 `spEvidence`，不含属性值；停下时也给出这些字段，便于判断原因。同一路径上的不同 Shibboleth 步骤（URL 的 `execution` 不同）各算一页，各自只尝试一次。

## 链路与 `maxSteps`

`POST /v2/tabs/{targetId}/access` 带 `maxSteps`（1–6，默认 1）时，Broker 在一次请求里依次处理：同意页 → 等页面跳转（含 SAML 自动提交页）→ 密码页（浏览器自动填充或[本机凭据助手](cdp-lifecycle.md#本机凭据助手)）→ 等页面跳转 → 回到服务提供商。每一步之后重新判断页面，所以同意页出现在密码页之前或之后都能处理。步数用完时只观察、不再动作。结果附 `steps`，列出每步的 `state` 和 `loginMethod`。

UESTC 的实际顺序（2026-11-23 真实页面核实）：IEEE 文章页 → Institutional Sign In → “Access Through University of Electronic Science & Technology of China”（IEEE 自己的机构面板，不经过独立的 CARSI 发现服务页）→ `idp-lib.uestc.edu.cn` 的使用条款声明页（首次出现，接受后 IdP 会记住）→ 同一主机的“信息发布”属性释放页（只释放 `eduPersonScopedAffiliation`，提供“信息变化时再提示”的本服务记住选项）→ 回到 IEEE，页面显示 “Access provided by: University of Electronic Science and Tech of China”。两次实测都没有出现 `idas.uestc.edu.cn` 密码页，推测浏览器里已有统一身份认证会话；会话过期时密码页会插在中间，这条路径只用合成页面测过。IEEE 的 SAML 请求通过重定向发出，到达 IdP 时 URL 只剩 `execution` 参数、referrer 为空，所以服务方只能从重定向链上的 `SAMLRequest` 取证。

## 名单维护

名单在 [federated-providers.json](federated-providers.json)，分为 `serviceProviders`、`discoveryServices` 和 `identityProviders`，每项写 `id`、`names`（页面上显示的服务名）、`hosts`（主机，含子域），SP 可再写 `entityIds`。IEEE（`https://ieeexplore.ieee.org/shibboleth-sp`）、Elsevier、Springer、ACM 的 entityID 已于 2026-11-23 通过 InCommon 元数据查询服务（mdq.incommon.org）核实；其余出版商还没有核实，只靠导航历史取证，不要凭猜测补写。本机补充写在 `%LOCALAPPDATA%\web-access\federated-providers.local.json`，结构相同，条目追加到公开名单后。`autoConsentCategories` 只能从上述三类里选，写入其他类别会被忽略。

新增出版商时，同时写它的显示名和主机；名称太泛（如单个常见词）时，靠主机历史约束，不必删名称。
