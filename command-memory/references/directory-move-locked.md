# 目录移动/删除被占用排查

## 症状

```
mv: cannot remove 'D:/path': Device or resource busy
Remove-Item: 另一个程序正在使用此文件，进程无法访问
```

## 本次迁移实战 (2026-07-08/09)

| 场景 | 根因 | 解决 |
|---|---|---|
| `mv /d/Workspace/04-agents` 失败 | VS Code cwd 压住目录 | 关掉 VS Code |
| `rm LabData/04-agents/.venv` 失败 | paper-search-mcp 僵尸进程持有句柄 | `taskkill /F /IM python.exe` |
| `mv BaiduSyncdisk/04-agents` 失败 | 百度云客户端监视 | 暂停同步 |
| PowerPoint 锁 `申报书本子/` | Office 进程未退出 | `taskkill /F /IM POWERPNT.EXE` |
| 删 junction 失败 | 当前 shell cwd 在 junction | `cd /` 后再删 |

## 排查顺序

### 1. 检查当前 shell cwd
```powershell
$PWD.Path  # 80% 的锁都是这个
```
→ 切到别的目录或关窗口

### 2. 查 MCP 僵尸
```powershell
Get-Process python | Where-Object {$_.CommandLine -like '*mcp*'}
```
→ `taskkill /F /IM python.exe`（残留进程安全杀）

### 3. 查 Office
```powershell
Get-Process | Where-Object {$_.Name -match 'POWERPNT|WINWORD|EXCEL'}
```
→ 退出应用（不能强杀，会丢未保存内容）

### 4. 查 VS Code
```powershell
Get-Process Code
```
→ File → Exit

### 5. 查同步客户端
```powershell
Get-Process | Where-Object {$_.Name -like '*baidu*' -or $_.Name -like '*sync*'}
```
→ 暂停同步，完成后恢复

## Junction 删除专用
```cmd
cmd /c rmdir D:\path\to\junction
```
**不能用 `rm -rf`**——会穿透 junction 删数据。

## 工具陷阱

- **Git Bash robocopy**：MSYS 路径转换会毁参数 → 换 PowerShell
- **Python `/c/` 路径**：`glob.glob('/c/...')` 返回空 → 改 `C:/...`
- **printf `\04` 转义**：`printf "D:\04-agents"` 把 `\04` 吃成 EOT → 用 Python `chr(92)`

## 原则

- 先检查 cwd（最常见）
- 先温和后暴力（切目录 > 关窗口 > 杀进程）
- 同步客户端必须暂停（否则边移边同步丢数据）
- MCP 需要重启宿主（Codex/Claude Desktop），不能只停 shell
