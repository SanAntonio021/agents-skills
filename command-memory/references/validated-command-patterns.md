# Validated Command Patterns

这个索引只给高风险 Windows 命令急救用。普通只读命令不要读这里。

## 快速路由

| 场景 | 读取 |
| --- | --- |
| 外部 CLI、绝对路径、下载、用户级安装、PATH/env 持久化 | [cli-paths.md](cli-paths.md) |
| PowerShell 调 Python，中文路径、here-string、UTF-8 乱码 | [python-utf8.md](python-utf8.md) |
| 中文 Markdown / UTF-8 文本读取 | [markdown-read-utf8.md](markdown-read-utf8.md) |
| 搜索、遍历、文本匹配失败 | [search-and-traversal.md](search-and-traversal.md) |
| 压缩、解压、复制、移动、删除 | [archive-and-file-ops.md](archive-and-file-ops.md) |
| 规则文件同步、软链、临时复制对齐 | [rule-file-sync-and-symlink.md](rule-file-sync-and-symlink.md) |
| WindowsApps / AppX packaged app 启动锁、`0x80070020` | [windows-appx-packaged-app-lock.md](windows-appx-packaged-app-lock.md) |
| MATLAB batch / desktop / logfile / status file | [matlab-batch-logfile.md](matlab-batch-logfile.md) |
| Office COM、PowerPoint/Word/Excel 自动化 | [office-com.md](office-com.md) |
| Word COM `gen_py` cache | [word-com-genpy-recovery.md](word-com-genpy-recovery.md) |
| Codex 桌面侧边栏本地状态恢复 | [codex-sidebar-recovery.md](codex-sidebar-recovery.md) |
| GitHub Contents API 下载子目录 | [github-contents-api-download.md](github-contents-api-download.md) |
| 工具发现、preflight 命令 | [tool-discovery.md](tool-discovery.md) |
| 失败后成功，需要沉淀 | [recovery-capture-checklist.md](recovery-capture-checklist.md) |

## 规则

- 每次最多读一个最接近的 reference。
- 如果只是普通命令失败，先用常识修正；不要为小问题加载整库。
- 新模式只写进具体场景文件，不追加到本索引。
