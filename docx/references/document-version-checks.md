# Word 版本与检查结果

恢复任务或复用“检查通过”时，先核对实际主稿、模板及其 profile、图片和 Word 的内容版本。
版本信息写在对应文档的检查记录中，由工具计算，不要求用户回填哈希或重复确认。

## 生成记录

`scripts/template/export_markdown_to_word.ps1` 自动在转换前捕获输入，在格式处理后核对输入未变，
再把生成的 Word 版本写入 `<output>.check.json`。可用 `-CheckRecordPath` 复用该文档已有的检查记录。
不要把此参数指向源稿、模板或多文档项目总台账。生成结果为 `UNCHECKED`，不表示内容或版式通过。

默认输出已存在时另存编号文件；明确指定的输出已存在时，选择新路径，只有用户明确允许覆盖才使用
`-OverwriteExisting`。两种情况都保护源稿、模板和图片。

其他制作路径可以复用同一工具，输入快照应在生成前捕获：

```powershell
$snapshot = python <skill-root>\scripts\document_versions.py capture-inputs `
  --source draft.md --template template.docx
# Generate and check content using the existing document tools.
$snapshot | python <skill-root>\scripts\document_versions.py record-generation output.docx `
  --record output.docx.check.json
```

`--source`、`--image` 可重复。`--preset` 与 `--template` 二选一。Markdown 图片使用 Pandoc JSON
解析，与导出命令一样以主稿所在目录查找；模板和可选 profile 同时记录。远程图片、未覆盖的 HTML
资源会使记录不可跨轮复用，不为此新增下载或缓存流程。

## 复用与重查

将原有、只读的 JSON 检查命令放在 `run-check` 的 `--` 后。命令只来自本次调用，不从记录中执行：

```powershell
python <skill-root>\scripts\document_versions.py run-check output.docx `
  --record output.docx.check.json --kind word-native -- `
  python <skill-root>\scripts\office_native_gate.py check output.docx `
  --format docx --json --require-render --allow-office-com
```

- 文件、检查参数及检查脚本未变，且原检查确实通过：返回 `reused=true`。
- 主稿、模板/profile 或图片变化：返回 `INPUTS_CHANGED`。更新受影响的 Word 产出并重新检查；
  如同时存在 Word 手改，保留手改，只有真实内容冲突无法自行处理时才询问。
- 只有 Word 变化：对当前 Word 重查，不自动重新套模板或覆盖。
- 记录缺失或不完整：重新检查当前 Word；有当前输入材料时用 `--source/--template/--image` 指定。
- 检查期间文件变化、检查器失败、报告对象或哈希不符：不记录通过。
- 明确需要再次执行同一检查时使用 `--refresh`。无法判断变更影响哪些页时，重新检查完整相关内容。

Office 检查的超时与清理由原有守护程序负责，版本包装层不强制结束检查器进程。LibreOffice 的
`--queue-timeout/--run-timeout` 放在实际检查命令中；`run-check --timeout` 仅用于非 Office 检查。

飞书主稿先通过相应技能回读，临时快照只代表本轮读取，不能替代远程主稿。跨轮不能对应旧快照时，
使用当前材料重新检查，不声称远程版本未变。

只读核对已有结果：

```powershell
python <skill-root>\scripts\document_versions.py verify output.docx --record output.docx.check.json
```

`verify` 不写文件、不调用检查器；可复用退出 `0`，需要重查退出 `2`。
记录仅代表 `check_kind` 标明的那项检查。LibreOffice 转换和原生打开/导出仍分别表述，真实渲染和
智能体逐页目检继续执行；版本一致不证明整份文档已验收。原生检查器清理的临时图也不作为可用交付物。
