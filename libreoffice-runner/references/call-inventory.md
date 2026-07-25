# LibreOffice 直接调用盘点

盘点日期：2026-07-26。目标是找出会实际启动 LibreOffice 的路径；只提到 LibreOffice 的说明文字
不等于可执行调用。

| 层级 | 位置 | 分类 | 处理结论 |
|---|---|---|---|
| 自建源码 | `skills/xlsx/scripts/libreoffice_headless.py` | migrate | 保留公开函数和 CLI，内部转发 runner。 |
| 自建源码 | `skills/docx/scripts/office/soffice.py`、`skills/docx/scripts/accept_changes.py` | runner-backed | `soffice.py` 是有限参数兼容层，`accept_changes.py` 直接调用 runner；两者都不自行启动 LibreOffice。 |
| 自建源码 | `skills/pptx/scripts/office/soffice.py`、`skills/pptx/scripts/thumbnail.py` | runner-backed | `soffice.py` 是有限参数兼容层，`thumbnail.py` 通过该兼容层调用 runner；两者都不自行启动 LibreOffice。 |
| 自建源码 | `skills/command-memory/references/cli-paths.md` | migrate | 直接 `soffice.com` 示例改为 runner CLI。 |
| 自建归档 | `skills/archive/pdf-fork/SKILL.md` | out-of-scope | 已归档，不修改；重新启用前必须迁移。 |
| 上游镜像 | `skills/upstream/**/docx/scripts/office/soffice.py`、`accept_changes.py`、`pptx/scripts/thumbnail.py`、`xlsx/scripts/recalc.py` | policy-bypass | 镜像和许可证边界禁止修改；Windows 工作流不得执行其 LibreOffice 部分。 |
| cc-switch 分发 | `%USERPROFILE%/.cc-switch/skills/{xlsx,docx,pptx,libreoffice-runner}` | deployment-copy | 运行时副本不直接改；以自建源码为准，提交后通过 cc-switch 同步。 |
| Claude 运行时 | `%USERPROFILE%/.claude/skills` | documentation-only | 本轮未发现独立可执行 direct call；引用的同步 skill 仍以源码同步状态为准。 |
| Codex 运行时 | `%USERPROFILE%/.codex/skills` | documentation-only | 本轮未发现独立可执行 direct call；引用的同步 skill 仍以源码同步状态为准。 |
| Lark 实体层 | `%USERPROFILE%/.agents/skills` | out-of-scope | 路径不存在。 |
| Codex bundled cache | `%USERPROFILE%/.codex/plugins/cache/openai-primary-runtime/documents/**/render_docx.py` | policy-bypass | bundled cache 不改；Windows 工作流改用 runner 转 PDF 后再执行非 LibreOffice 步骤。 |
| Codex bundled cache | `presentations/**/render_presentation.mjs`、模板检查脚本和 documents 文档 | documentation-only | 无可迁移的 Windows direct launch，或只检测/说明 LibreOffice。 |

结论：本地 `xlsx` 包装器和 `command-memory` 示例仍按迁移项管理；当前 `docx`、`pptx` 的 Windows
转换路径已经通过薄适配器调用 runner。继续保持 runner 独立，不把进程、队列或 profile 管理复制进
文件类型 skill；不改运行时缓存、第三方安装体或上游镜像。
