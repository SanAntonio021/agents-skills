---
name: markdown-docx-workflow
description: "管理正式文档的 Markdown 到 Word 工作流。只要用户要写报告、方案、申报材料或其他最终以 Word 交付的文档，且需要先改 Markdown、确认内容、再生成和验收 Word，就使用本技能。它负责阶段路由、用户确认、源稿/模板/Word/验收报告指纹和 PDF 发布门；具体模板、样式、分页和 Office 验收交给 docx。"
---

# Markdown 到 Word 工作流

Word 是最终提交主文件，Markdown 是内容主稿。PDF 只从已经确认的 Word 另行导出。

## 阶段

按以下状态推进，状态和指纹写入项目的工作流记录：

`DRAFT -> CONTENT_FROZEN -> DOCX_GENERATED -> DOCX_ACCEPTED -> WORD_CONFIRMED -> PDF_RELEASED`

- `DRAFT`：起草、修改、审阅 Markdown；内容仍可变化。
- `CONTENT_FROZEN`：用户确认当前 Markdown 内容，记录原话、时间、Markdown 路径和 SHA-256；此时不自动导出 Word。
- `DOCX_GENERATED`：`docx` 按已锁定的格式来源生成新 Word，记录生成清单、格式来源和 Word 指纹。
- `DOCX_ACCEPTED`：完成 `docx` 的四层验收，并提交匹配 Word 指纹的 `DocxAcceptanceReport`。
- `WORD_CONFIRMED`：用户确认该 Word 可作为最终版本，记录确认原话、时间、路径和 SHA-256。
- `PDF_RELEASED`：仅从匹配 `WORD_CONFIRMED` 的 Word 导出交付 PDF。

任何 Markdown 修改都会清除 Word、验收和 PDF 的后续状态；任何 Word 重新导出、人工编辑或 SHA-256 变化都会清除 `DOCX_ACCEPTED`、`WORD_CONFIRMED` 和 `PDF_RELEASED`，并要求重新验收。已锁定的格式来源发生路径、类型或 SHA-256 变化时，回到 `CONTENT_FROZEN`，重新锁定格式来源、生成 Word 并验收。

## 格式来源门

进入正式 Word 生成前，先锁定本次格式来源。用户已经给出“格式参考”的本地 Word、模板或预设时，视为已经指定格式来源，不得静默改用默认预设或 `Normal.dotm`。只有用户没有指定任何格式来源时，`docx` 才能采用其受管默认值；存在多个候选且用户没有说明主次时，只询问一次最关键的选择问题。

格式来源记录复用 [Markdown 到 DOCX 交接契约](../writing-router/references/markdown-docx-contract.md) 的现有字段：

- `format_source`：`template`、`preset` 或 `none`；参考 DOCX、原生模板和 `Normal.dotm` 均归入 `template`；
- `template_id`：可稳定识别本次格式来源的 ID；
- `template_path`：项目根相对路径；项目外的 `Normal.dotm` 或模板先复制为任务隔离快照再记录，`format_source=none` 时为 `null`；
- `template_sha256`：模板文件或受管预设配置的 SHA-256；`format_source=none` 时按契约记录 `none`。

用户原话、选择时间和采用受管默认值的理由写入现有工作流事件记录。生成前重新计算文件或样式配置指纹；路径不存在、指纹变化或来源类型与记录不符时停止生成。`scripts/workflow_state.py` 已在 `DOCX_GENERATED` 记录 `manifest_path`、`template_path` 和 `template_sha256`，不新增平行状态文件。

## 自然语言门

- “继续修改”：保持 `DRAFT`，只改 Markdown。
- “内容确认”“内容可以了”：进入 `CONTENT_FROZEN`，记录确认，但不导出 Word。
- “确认内容并导出 Word”：冻结当前 Markdown，锁定格式来源，再调用 `docx` 进入正式导出。
- 单独说“导出 Word”：先确认 Markdown 是否已定稿；未确认只能提供带明确标记的预览。
- “Word 可以作为最终版本”“确认这个 Word”“Word 没问题，可以提交”：在 `DOCX_ACCEPTED` 且报告无硬阻断后进入 `WORD_CONFIRMED`。报告中的警告要先逐项展示。
- “导出 PDF”：仅允许从同一份 `WORD_CONFIRMED` Word 导出，路径和 SHA-256 必须匹配。
- “差不多”“应该可以”等模糊表述不改变状态。

确认记录必须绑定当前任务、`artifact_id` 和 `revision`，不能跨任务或跨版本复用。准确的内容确认和 Word 验收许可仍使用 `docx` 契约规定的完整原话。

## 与 docx 的分工

1. 在内容阶段读取并遵守 [Markdown 到 DOCX 交接契约](../writing-router/references/markdown-docx-contract.md)，只维护 Markdown 主稿和状态记录。
2. 进入 Word 阶段前按“格式来源门”锁定格式来源；进入 Word 阶段后调用 [docx](../docx/SKILL.md)。模板、样式、分页、LibreOffice、Word 原生打开/渲染和人工逐页检查全部由 `docx` 负责。
3. `DocxAcceptanceReport` 必须包含 Word 路径/SHA-256、按顺序排列的四层结果，以及 [Word 权威验收清单](../docx/references/word-acceptance-checklist.md) 的七个项目：字体与回退、段落格式、表格格式、页眉页脚几何、分页、Word 原生打开、Word 原生渲染。
4. 四层中出现 `FAIL`、`UNVERIFIED`、`ENV_UNVERIFIED` 或 `NOT_RUN` 时不得进入 `DOCX_ACCEPTED`。警告可以保留，但必须在 Word 最终确认前展示。
5. PDF 阶段只使用已确认 Word；内部的 `_validation.pdf` 仅是 `NATIVE_RENDER_PASS` 证据，不是交付 PDF，也不能绕过确认门。

## 记录与恢复

使用本技能随附的 `scripts/workflow_state.py` 生成、校验和推进状态。状态文件采用 UTF-8 无 BOM、LF 换行的 JSON；所有路径为项目根相对 POSIX 路径。每次推进保留旧状态的哈希和事件时间，失败时写明阶段、原因和证据路径。

推荐记录文件：`deliverables/workflow/<artifact_id>.r<revision>.state.json`。

状态脚本的纯函数接口适合被内容技能、`docx` 包装器和测试调用；它不启动 Word、LibreOffice 或任何外部应用。
