# 功能来源与接口依据

本技能保持一个入口。以下项目提供功能流程参考，没有安装其 MCP，也没有复制完整上游技能；协议及功能代码在本技能内独立实现。

| 来源 | 固定提交 | 本次借鉴 | 未引入 |
| --- | --- | --- | --- |
| [OpenAI Zotero](https://github.com/openai/plugins/tree/0722921d5542fc593105c27bd52630babd8b8c2a/plugins/zotero) | `0722921d5542fc593105c27bd52630babd8b8c2a` | 实际 BibTeX 导出、引用键及文稿引用流程 | 整库覆盖 `.bib`、结束 Zotero 进程、依赖当前选中集合的 Connector 保存 |
| [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp/tree/f6f26fe77f54b70eccf6d15a9000ecc02dadc739) | `f6f26fe77f54b70eccf6d15a9000ecc02dadc739` | PDF 分页、笔记与批注的所属论文和页码 | MCP 服务、语义模型、独立索引及云端回退 |
| [dvdsosa/zotero-native-mcp](https://github.com/dvdsosa/zotero-native-mcp/tree/3a612c89db3226e40787bb533e6e76323c1bc84c) | `3a612c89db3226e40787bb533e6e76323c1bc84c` | Local API 的条目、集合及附件上传对接流程 | 链接附件默认值、认证失败或数据库变化后的透明重放 |

OpenAI 来源的适用许可尚未确认，仅借鉴功能流程，独立实现，未复制其代码。54yyyu 项目的 Python／CLI 部分为 MIT，插件另为 AGPL；dvdsosa 项目为 MIT。本次不纳入其插件或源文件，不把 MCP 项目登记为有 `SKILL.md` 的技能来源。现有自动生成的上游登记页继续反映技能来源关系。

[Zotero 官方 Local API 文档](https://www.zotero.org/support/dev/web_api/v3/local_api)是协议依据。实现还核对了 Zotero 10.0.7 随附的 `server_localAPI.js`，独立实现请求与响应处理。接口支持需要实际能力检查，不能用文档或模拟通过代替目标 Zotero 验收。

普通读取无需写授权；写入授权从 `/api/local/authorize` 取得，数据库绑定使用 `Zotero-Server-ID`。PDF 采用创建附件、申请上传、传输字节和登记的流程，源文件保留。官方 API 的永久删除不用于本技能清理；`prune` 保留原生回收站操作。
