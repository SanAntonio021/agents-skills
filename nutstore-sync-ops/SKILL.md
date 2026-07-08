---
name: nutstore-sync-ops
disable-model-invocation: true
description: >
  排查和运维 Windows 上的坚果云（Nutstore）同步：空间/配额满、同步卡住不动、上传队列堵死、
  大文件夹不想上云（junction 排除法）、目录改名是否重传、同步冲突文件夹、读客户端日志定位问题。
  遇到坚果云同步异常、Workspace 空间告警、要给新项目挂实验数据 junction、或换机后要重建同步边界时，点名使用本技能。
---

# 坚果云同步运维

## 目标

处理坚果云客户端（7.x 云桥/placeholder 模式）的三类问题：空间配额、同步卡死、大数据排除。全部结论来自 2026-07-08 在客户端 7.2.12 上的实测，不是文档转述。

## 关键事实（实测）

1. **坚果云完全无视 NTFS junction**。实时监视和重启后全量扫描都不会上传 junction 背后的内容，日志中零痕迹。这是"大文件夹在项目路径可见但不上云"的唯一可靠手段。
2. **7.x 云桥版没有选择性同步、没有忽略规则**。老版本的"选择性同步"功能已移除，`.gitignore` 式配置从未存在（官方博客 blog.jianguoyun.com/?p=2839 明确建议代码走 Git）。
3. **配额满会触发全局挂起**：日志出现 `Storage quota exhausted. Background process is halted for 12 hours.`，期间**连删除释放空间的操作都不执行**。上传队列是头阻塞的——一个失败上传（例如 Zotero WebDAV 的 zip）堵死后面所有任务。
4. **目录改名 = 服务端重命名，不重传**。日志按 `OnRename → AckRename → OnRenameCompletion` 处理，改名安全。
5. **配额账目**：专业版首年 42GB（30 基础 + 12 加享），续费每年再 +12GB；回收站和历史版本不占配额；付费版不限流量。删除文件后配额立即释放，无需清回收站。

## 工作顺序

1. 先读日志定位问题：

```powershell
Get-Content "$env:APPDATA\Nutstore\logs\Nutstore.Client.Wpf.log" -Tail 50 -Encoding UTF8
```

   认三个关键词：
   - `StorageSpaceExhausted` / `halted for 12 hours`：配额满，全局挂起。
   - `UpstreamFileChangeCommand: [Path = ...]`：正在（或正试图）上传什么。
   - `OnRename`：文件系统改动被识别为重命名（好事，不重传）。

2. 按命中情况处理，见下面对应小节。

## 配额满急救

1. **不要指望客户端自己恢复**——它挂起 12 小时，重启后如果队首上传仍失败会再次挂起。
2. **从网页版删大文件**（jianguoyun.com 登录 → 直接删）：绕过客户端，服务端立即释放配额。
3. 删完重启客户端清挂起计时器：

```powershell
Stop-Process -Name NutstoreClient -Force; Start-Sleep 3
Start-Process "C:\Program Files\Nutstore\bin-7.2.12\NutstoreClient.exe"
```

4. 验证：日志不再出现 `StorageSpaceExhausted`，积压队列开始逐条处理。

## 大文件夹排除（junction 法）

数据本体放同步区外（约定 `D:\LabData\<项目名>\`），项目里挂 junction：

```powershell
New-Item -ItemType Directory -Path "D:\LabData\<项目名>" -Force
cmd /c mklink /J "<项目路径>\experiments" "D:\LabData\<项目名>"
```

- 每个项目建一次，之后往里放任何新数据都零操作。
- junction 不会同步到其他电脑（那边看不到这个文件夹），数据本来就单机，符合预期。
- 若 junction 顶替的是云端已存在的同名真文件夹，云端旧文件夹会残留，网页版手动删一次即可。
- 验证方法（金丝雀）：同步区外建带测试文件的目录 → junction 挂进同步区 → 等 2 分钟 + 重启客户端 → 日志 grep 测试文件名应为 0 命中、网页版不出现该文件夹。

## 目录改名安全流程

1. 先用空目录试一个，确认日志走 `OnRename`（重命名）而不是删除+新建。
2. 有内容的目录逐个改，每个之间等客户端回到空闲。
3. 全程只在一台电脑操作，其余机器暂停同步或关机，改完再让它们被动拉取。
4. 改名报"拒绝访问"时是本机进程占用（VS Code 监视器、Zotero 自动导出、坚果云扫描），排查命令见 `command-memory` 的 archive-and-file-ops 参考。

## 常见坑

- **看起来在同步其实在挂起**：托盘图标不动 ≠ 正常排队，先看日志有没有 `halted`。
- **Explorer 图标误导**：云桥模式给同步区所有条目叠状态角标，junction 也会被叠；是否真上传以网页版和日志为准。
- **同步冲突文件夹**：`C:\Users\<用户>\Documents\坚果云同步冲突\` 里出现的目录多数只含自动生成的说明文件；先核对文件数和大小再决定是否有真数据要救。
- **Zotero WebDAV 同用一个账号配额**：Zotero 附件上传失败堵队列时，症状表现在 Workspace 同步上，别只盯 Workspace 查。
- **换同步工具必须重验 junction 行为**：OneDrive/Dropbox 对 junction 是跟随或报错，不是无视。

## 安全边界

- 网页版删除是不可逆操作链的入口（回收站 30 天），删之前确认本地已有完整副本。
- 不直接改 `%APPDATA%\Nutstore\` 下的数据库文件；只读日志。
- 移动大目录用 `Move-Item` 同盘操作前，确认坚果云已识别（日志 `OnRename`），异机同步完成前不在其他电脑改同一批文件。
