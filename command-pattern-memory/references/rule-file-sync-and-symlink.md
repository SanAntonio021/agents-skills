# 规则文件不同步与软链修复

## 这份说明管什么

当两个本地规则文件看起来没同步上时，先分清它们各自是什么，再决定修软链、临时复制，还是只改源文件。不要一上来就直接覆盖。

## 先按这个顺序判断

1. 先确认两边内容是不是真的不同。
2. 再看当前正在用的那份是不是软链。
3. 如果是软链，再看它指向对不对。
4. 如果不是软链，再看它是不是后来复制出来的旧副本。
5. 只有分清这一步，才决定后面是修软链、先临时复制，还是只改源文件。
6. 如果只能先复制，要明确告诉用户这只是临时对齐，不是自动同步。

### Pattern: powershell-rule-file-sync-inspect
- scenario: 比较两个本地规则文件，并判断它们分别是源文件、软链入口，还是普通副本
- use_when: 源文件已经更新，但另一个本地文件还是旧内容，后面的修法取决于先分清两边各是什么
- shell: PowerShell
- validated_shape:
  ```powershell
  $paths = @("<PRIMARY_PATH>", "<SECONDARY_PATH>")
  foreach ($p in $paths) {
    Get-Item -LiteralPath $p -Force | Select-Object FullName, LinkType, Target, Attributes, LastWriteTime
  }
  $left = Get-Content -LiteralPath "<PRIMARY_PATH>" -Encoding UTF8 -Raw
  $right = Get-Content -LiteralPath "<SECONDARY_PATH>" -Encoding UTF8 -Raw
  $left -eq $right
  ```
- substitute_only: `<PRIMARY_PATH>`, `<SECONDARY_PATH>`
- preflight: `Test-Path "<PRIMARY_PATH>"`; `Test-Path "<SECONDARY_PATH>"`; 如果其中一边应该是当前实际入口，先确认应用或规则加载器确实读的是那一边
- env: none
- avoid: 没看清是不是软链就直接覆盖；只看名字一样就当成同一种文件；只比时间戳、不读内容
- success_signal: 能明确说清哪边是源文件、哪边是当前入口、有没有软链，以及内容是不是真的不同
- capture_rule: 只要遇到两个本地规则文件没同步上，而第一步又必须先分清它们的角色，就复用这一条

### Pattern: powershell-cmd-mklink-file-fallback
- scenario: PowerShell 建文件软链失败后，改用 `cmd /c mklink` 继续修复
- use_when: 目标文件存在，你希望一个本地规则文件跟着另一个走，而且 `New-Item -ItemType SymbolicLink` 已经失败，或在当前会话里不稳定
- shell: PowerShell + cmd.exe
- validated_shape:
  ```powershell
  if (Test-Path "<LINK_PATH>") {
    Move-Item -LiteralPath "<LINK_PATH>" -Destination "<BACKUP_PATH>" -Force
  }
  cmd /c mklink "<LINK_PATH>" "<TARGET_PATH>"
  Get-Item -LiteralPath "<LINK_PATH>" -Force | Select-Object FullName, LinkType, Target
  ```
- substitute_only: `<LINK_PATH>`, `<BACKUP_PATH>`, `<TARGET_PATH>`
- preflight: `Test-Path "<TARGET_PATH>"`; 确认 `<LINK_PATH>` 的父目录存在；如果旧文件里可能还有独有改动，先备份；如果刚打开 Developer Mode，但当前会话还像拿着旧权限，先重开应用或终端再试
- env: none
- avoid: 备份前就删掉唯一副本；目标不存在还直接跑 `mklink`；不检查 `LinkType` 和 `Target` 就宣布成功；同一个失败的 PowerShell 写法反复重试
- success_signal: `Get-Item` 能看到 `LinkType` 是 `SymbolicLink`，而且 `Target` 指向你想要的源文件
- capture_rule: 只要是 PowerShell 建软链失败，但同一环境里改用 `cmd /c mklink` 成功，就复用这一条

### Pattern: powershell-rule-file-temp-copy-sync
- scenario: 软链暂时建不了时，先用复制把内容临时对齐
- use_when: 用户现在就要两边内容一致，但软链修复被权限、应用状态或时间压力卡住了
- shell: PowerShell
- validated_shape:
  ```powershell
  if (Test-Path "<TARGET_PATH>") {
    Copy-Item -LiteralPath "<TARGET_PATH>" -Destination "<BACKUP_PATH>" -Force
  }
  Copy-Item -LiteralPath "<SOURCE_PATH>" -Destination "<TARGET_PATH>" -Force
  ```
- substitute_only: `<SOURCE_PATH>`, `<TARGET_PATH>`, `<BACKUP_PATH>`
- preflight: `Test-Path "<SOURCE_PATH>"`; 复制前先确认 `<SOURCE_PATH>` 才是真正的源文件；如果 `<TARGET_PATH>` 可能还有独有改动，先备份
- env: none
- avoid: 把这说成自动同步；还没分清哪边才是源文件就直接复制；不提醒用户后面不会自动跟着变
- success_signal: 目标文件内容已经和源文件一致，而且已经明确告诉用户这只是临时对齐
- capture_rule: 只要更稳的短期做法是先把内容对齐、把真正的软链修复放到后面，就复用这一条
