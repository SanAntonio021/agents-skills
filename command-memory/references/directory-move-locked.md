# 目录移动/删除被占用排查

## 症状

```
mv: cannot remove 'D:/path': Device or resource busy
Remove-Item: 另一个程序正在使用此文件，进程无法访问
Rename-Item: The process cannot access the file because it is being used by another process.
```

## 本次迁移实战 (2026-07-08/09/10)

| 场景 | 根因 | 解决 |
|---|---|---|
| `mv /d/Workspace/04-agents` 失败 | VS Code cwd 压住目录 | 关掉 VS Code |
| `rm LabData/04-agents/.venv` 失败 | paper-search-mcp 僵尸进程持有句柄 | `taskkill /F /IM python.exe` |
| `mv BaiduSyncdisk/04-agents` 失败 | 百度云客户端监视 | 暂停同步 |
| PowerPoint 锁 `申报书本子/` | Office 进程未退出 | `taskkill /F /IM POWERPNT.EXE` |
| 删 junction 失败 | 当前 shell cwd 在 junction | `cd /` 后再删 |
| 删掉的目录几秒后重生 | 宿主应用（Codex Desktop）重拉 MCP 子进程，继承旧 cwd 并重建目录 | 关宿主整棵进程树再删 |
| `Rename-Item BaiduSyncdisk/04-agents` 失败 | Codex Desktop 子进程（`node_repl.exe`、`node.exe`、`cmd.exe`）cwd 仍在旧目录 | 用全进程 cwd 扫描定位，只杀精确命中的子进程后重试；不必先杀 `codex.exe` 主进程 |

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

**宿主重生陷阱**：宿主应用（Codex Desktop / Claude Desktop / VS Code 扩展）还活着时，杀掉 MCP 子进程（node/cmd/python）几秒内会被重拉；新子进程继承会话记录的旧 cwd，甚至把刚删掉的目录重建成空骨架（`.git`/`.codex` 等空目录）。目录"删了又复活"就是此症状——先关宿主整棵进程树，再删目录（2026-07-09 实战确认）。

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

### 6. 全进程 cwd 扫描（前面都查不到时）

`Get-Process` 的 Path/CommandLine 只反映 exe 位置和启动参数，不反映工作目录；压住目录的常是 cwd 停在里面、命令行完全无关的进程。读 PEB 扫全部进程的 cwd：

```powershell
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class ProcCwd {
  [DllImport("ntdll.dll")] static extern int NtQueryInformationProcess(IntPtr h, int cls, ref PBI pbi, int len, out int retLen);
  [StructLayout(LayoutKind.Sequential)] struct PBI { public IntPtr R1; public IntPtr PebBaseAddress; public IntPtr R2a; public IntPtr R2b; public IntPtr Pid; public IntPtr R3; }
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int access, bool inherit, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out IntPtr read);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  public static string GetCwd(int pid) {
    IntPtr h = OpenProcess(0x0410, false, pid);
    if (h == IntPtr.Zero) return null;
    try {
      PBI pbi = new PBI(); int rl;
      if (NtQueryInformationProcess(h, 0, ref pbi, Marshal.SizeOf(typeof(PBI)), out rl) != 0) return null;
      byte[] p = new byte[8]; IntPtr rd;
      if (!ReadProcessMemory(h, (IntPtr)((long)pbi.PebBaseAddress + 0x20), p, 8, out rd)) return null;
      long pp = BitConverter.ToInt64(p, 0);
      byte[] us = new byte[16];
      if (!ReadProcessMemory(h, (IntPtr)(pp + 0x38), us, 16, out rd)) return null;
      short len = BitConverter.ToInt16(us, 0);
      long bp = BitConverter.ToInt64(us, 8);
      if (len <= 0 || bp == 0) return "";
      byte[] s = new byte[len];
      if (!ReadProcessMemory(h, (IntPtr)bp, s, len, out rd)) return null;
      return Encoding.Unicode.GetString(s);
    } finally { CloseHandle(h); }
  }
}
'@

Get-Process | ForEach-Object {
  $cwd = [ProcCwd]::GetCwd($_.Id)
  if ($cwd -and $cwd.Contains('<TARGET_DIR_KEYWORD>')) {
    [PSCustomObject]@{ Id = $_.Id; Name = $_.ProcessName; Cwd = $cwd }
  }
} | Format-Table -AutoSize
```

- Add-Type 定义和扫描必须在**同一条命令**里发出：每次工具调用都是新 PowerShell 进程，类型不跨调用存活（分两次调用会报 `Unable to find type`）。
- 偏移量只适用于 64 位 Windows（PEB+0x20 → ProcessParameters，ProcessParameters+0x38 → CurrentDirectory）。
- 提权/系统进程 OpenProcess 失败返回 null 属正常；扫描无命中但目录仍锁 → 锁在提权进程或非 cwd 的目录句柄上，改用管理员权限 handle64（见 `archive-and-file-ops.md` 的 windows-dir-rename-lock-diagnosis）。
- 2026-07-09 实战：常规方法全部无果后，此法一次定位 11 个 cwd 停在已迁走目录里的 cmd/node/node_repl 进程。
- 2026-07-10 实战：`handle64` 精确目录查询无结果或长时间不返回，但 cwd 扫描一次定位 10 个 Codex Desktop 子进程；`Stop-Process -Id <PID> -Force` 精确停止后，`Rename-Item -LiteralPath <OLD_DIR> -NewName <NEW_NAME>` 立即成功。

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
- MCP 需要关宿主（Codex/Claude Desktop），不能只杀子进程——宿主会重拉子进程并在旧 cwd 重建刚删掉的目录
