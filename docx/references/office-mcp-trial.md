# Office MCP 隔离试验说明

当前结论：公开的 `Office-Word-MCP-Server` 不进入生产依赖。按当前核对记录，该仓库已归档；本地 OfficeCLI、LibreOffice runner 和 Word 原生门仍是正式 DOCX 流程，MCP 不能替代任一验收层。

如需试用 Office MCP，只能在 `%TEMP%/office-mcp-trials/<candidate>/<commit>/<run_id>/` 创建临时副本，并固定来源 URL、许可证、commit/tag、依赖锁文件和源码 SHA-256。依赖取得后关闭网络；不得修改 `C:\Users\SanAn\.codex`、`.cc-switch`、`.claude` 或正式技能运行目录，也不得把临时 MCP 注册为生产配置。

固定测试集至少覆盖：中文字体、标题层级、长表格、图片、公式、页眉页脚、分页、批注/修订和异常输入。每个候选都与当前 Pandoc/模板/OfficeCLI 路线做 A/B，并按相同四层流程验收：OOXML、LibreOffice 转换和逐页人工检查、Word 原生打开、Word 原生渲染。缺依赖、损坏输入、超时、权限拒绝、路径穿越、符号链接、网络仍开启或既有 Office 进程存在时，必须返回明确失败并保留证据。

同一输入、锁定版本和隔离配置必须连续运行三次。三次输出 DOCX 必须字节一致；只允许 `skills/docx/mcp-determinism-allowlist.json` 登记的核心属性时间戳/生成 ID 发生变化，而且正文、样式、媒体、关系、页数和栅格指标完全一致。否则记为 `MCP_NONDETERMINISTIC`。在全部条件通过并取得明确审批前，候选只保留为手动诊断报告，记为 `MCP_NOT_ADMITTED`，不得进入生产流程。

试验入口只负责生成对照报告，不负责正式导出：

```text
%TEMP%/office-mcp-trials/<candidate>/<commit>/<run_id>/trial-report.json
```

正式交付仍使用：

```text
python skills/docx/scripts/markdown_docx_delivery.py validate-manifest --manifest <path> --project-root <root>
python skills/docx/scripts/markdown_docx_delivery.py review-manual submit --manifest <path> --checklist <path> --project-root <root>
```
