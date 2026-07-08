# 坚果云实测行为记录（2026-07-08，客户端 7.2.12 云桥模式）

本文件是 SKILL.md 结论的证据底稿。客户端大版本升级后，关键行为（尤其 junction 无视）需按"金丝雀验证法"重测一遍并更新本文件。

## 实验环境

- Windows 11，坚果云客户端 7.2.12（`C:\Program Files\Nutstore\bin-7.2.12\`），云桥/placeholder 模式（日志出现 `NutstoreClient.Placeholder.CloudFileCallback`）
- 同步对：`D:\Workspace` ↔ 云端 Workspace；专业版配额 45,097,156,608 字节（42GB）
- 日志：`%APPDATA%\Nutstore\logs\Nutstore.Client.Wpf.log`（重启轮转为 `.1.log`）

## 实测 1：junction 无视

- 做法：同步区外建 `D:\LabData\junction-canary-real\`（含测试文件）→ `mklink /J` 挂进同步区项目路径 → 观察 90 秒实时日志 → 重启客户端触发全量扫描再观察 120 秒。
- 结果：全日志（含轮转文件）grep junction 名和测试文件名 **0 命中**；网页版不出现该文件夹。
- 随后 39GB 实验数据以同法挂载，15 分钟监听无任何上传事件，配额无变化。
- 注意：Explorer 会给 junction 叠同步状态角标，纯视觉，不代表上传。

## 实测 2：配额满全局挂起 + 队列头阻塞

- 日志原文：`Storage quota exhausted. Background process is halted for 12 hours.`
- 触发者是队首一个 Zotero WebDAV 附件包（`UpstreamFileChangeCommand: [Path = /B7YS75LD.zip, sandbox = ...\Nutstore\1\zotero]`）上传被服务端 `StorageSpaceExhausted` 拒绝——注意 sandbox 是 Zotero 的同步对，但拖死的是所有同步对（含 Workspace）。
- 重启客户端只能清挂起计时器；队首上传仍失败会立即再次挂起。唯一出路：网页版删文件释放配额（服务端即时生效，不用清回收站），再重启客户端。
- 实测确认：本地 `Move-Item` 移出大文件夹后，客户端把它记为待处理事件，但挂起期间不执行——"删除能救配额"的前提是删除事件能被处理，挂起状态下不能。

## 实测 3：目录改名语义

- 8 个顶层目录（含 2GB+ 的论文目录）改中文名→英文名，日志全部为：
  `OnRename → AckRename(status 0x00000000) → OnRenameCompletion → Directory rename or move, from NutstorePath [...] to NutstorePath [...]`
- 云端为服务端重命名，无重传。空目录与满目录行为一致。

## 实测 4：改名被拒的三个真凶（当天全部遇到）

1. **VS Code 文件监视服务**：`Code.exe` 的 utility 进程（NodeService）对打开过的项目持有目录和 `.git` 句柄；关标签页/窗口才释放；杀该 utility 进程会被立即重新获取（另一窗口仍引用时）。用管理员权限 `handle64 -accepteula <目录>` 定位。
2. **Zotero Better BibTeX 自动导出**：目标目录被改名后，BBT 下次导出会按 prefs.js 里的旧路径**重建**目录。改路径要关 Zotero 后改 prefs.js 的键（URL 编码路径）+ 值（双反斜杠路径）两处。
3. **坚果云自身扫描**：大目录刚发生大量变更后短暂持锁，等空闲或重启客户端。

## 配额与计费（2026-07-07 网页与官方帮助核实）

- 专业版：首年 42GB = 30GB 基础 + 12 个月加享（购买即全给）；续费逐年累加 +12GB；199.9 元/年。高级专业版 96GB 首年，399.9 元/年。
- 付费版不限上传/下载流量（流量限制只在免费版）。
- 回收站和历史版本不占配额（客服口径 + 官方帮助页佐证）；删除文件配额立即释放。
- 配额满：新上传被拒，已有文件可正常访问下载，官方不会删任何东西。

## 同步冲突文件夹

- 位置：`C:\Users\<用户>\Documents\坚果云同步冲突\`
- 实测一次：云端删除下发时本地同名目录里有客户端自己生成的冲突说明文件，被搬进该文件夹——只有 `README-冲突-*.md` 和 `了解详情.txt` 两个标记文件，无真实数据。处理前先数文件、看大小，再决定救不救。
