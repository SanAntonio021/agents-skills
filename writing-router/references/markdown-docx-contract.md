# Markdown 到 DOCX 交接契约

这份契约是内容技能进入 Word 格式阶段的唯一交接入口。内容技能先完成 Markdown 主稿、审阅和用户确认；`docx` 只接收交接清单，负责模板、样式、结构、分页和 Office 验收。

## 内容阶段

- Markdown 是内容唯一主稿。内容技能默认只创建或修改 `.md`，不在内容尚未闭合时反复导出 Word。
- `content_status` 依次使用 `draft`、`reviewed`、`frozen`；正式导出必须为 `frozen`。
- `content_open_items` 必须为空；“需要继续修改”或 agent 自行判断不等于用户确认。
- `content_confirmed=true` 只能由当前任务中的用户完整回复“确认内容并导出 Word”产生，并写入同一 `artifact_id` 与 `revision` 的确认记录。
- 未满足正式条件时只能走显式 `preview`，预览记录不得标为正式交付。

## 清单与路径

交接清单为 UTF-8 无 BOM、LF 换行的 JSON，字段由 `docx/scripts/markdown_docx_delivery.py` 校验。至少包括：`artifact_id`、`template_id`、`source_markdown`、`source_sha256`、内容状态与确认字段、`revision`、`format_source`、`template_path`、`template_sha256`、`output_docx`、`output_sha256`、`toolchain_versions`、四层 `acceptance`、`evidence_paths`、`source_unchanged`、`failure_code` 和 `failure_detail`。`toolchain_versions` 中每个实际使用的 Pandoc、OfficeCLI、`libreoffice-runner`、LibreOffice、Word、Poppler 和 MCP 都记录精确版本或 commit，未使用项写 `null`，禁止 `latest`。

源稿、模板、输出和证据路径都必须是项目根相对的正斜杠路径；禁止绝对路径、`..`、符号链接、目录冒充文件和项目根外写入。源 Markdown 必须保持原始 UTF-8/LF 字节；哈希校验器不补换行、不去 BOM、不 trim，也不改写源文件。

## Word 阶段

正式 DOCX 默认写入新路径，既不覆盖 Markdown、原 DOCX，也不覆盖既有交付物。已有输出只有在固定 manifest 身份和完整输出哈希完全一致时才允许幂等重用，否则返回 `OUTPUT_COLLISION`。

四层验收顺序固定为：

1. `STATIC_PASS`：OOXML/package、样式、内容和源哈希检查；OfficeCLI 只能作为结构诊断。
2. `LO_RENDER_PASS`：经 `libreoffice-runner`、独立 `UserInstallation` 转 PDF，使用固定 Poppler 参数并逐页检查。
3. `NATIVE_OPEN_PASS`：获得本次任务明确许可后，Word 原生隔离副本打开并计算页数。
4. `NATIVE_RENDER_PASS`：Word 导出 PDF，并用同一固定 Poppler 参数栅格化；必须有匹配的批准基准和逐页人工检查清单。

任一层为 `FAIL` 或 `UNVERIFIED` 都停止正式交付，保留失败证据，不写 `delivered`。OfficeCLI HTML/native 预览和任何 MCP 的“成功”都不能替代后三层。

Word 原生门的许可记录必须绑定当前 `run_id` 和 `artifact_id`，并且用户完整回复“允许本次 Word 验收”；许可不跨任务、artifact 或 revision。栅格基准必须绑定模板哈希、Word 主版本、完整 Poppler 版本和固定命令 `pdftoppm -r 150 -png -aa yes -aaVector yes`，逐页哈希和 `user:<slug>` 审批身份缺一不可；没有匹配的 `approved` 基准只能记 `UNVERIFIED`。

## 安全边界

见 `docx` 技能内的 [Office security boundary](../../docx/references/office-security-boundary.md)。Windows 上禁止直接启动 `soffice`；Word COM 只能在本次任务收到完整回复“允许本次 Word 验收”、且检测不到既有 `WINWORD.EXE` 时运行，只读打开隔离副本，不连接、保存或关闭用户实例。
