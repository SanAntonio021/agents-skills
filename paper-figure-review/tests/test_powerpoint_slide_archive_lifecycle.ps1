[CmdletBinding()]
param(
    [string]$SourcePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Convert-ScriptJson {
    param(
        [object[]]$Output,
        [string]$Step
    )

    $text = ($Output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "$Step 没有返回验证结果。"
    }
    return $text | ConvertFrom-Json
}

if (@(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue).Count -gt 0) {
    throw '生命周期测试前请关闭 PowerPoint；脚本不会结束用户正在运行的 PowerPoint。'
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$installScript = Join-Path $skillRoot 'scripts\install_powerpoint_slide_archive.ps1'
$uninstallScript = Join-Path $skillRoot 'scripts\uninstall_powerpoint_slide_archive.ps1'
if ([string]::IsNullOrWhiteSpace($SourcePath)) {
    $SourcePath = Join-Path $skillRoot 'assets\powerpoint-slide-archive\PaperFigureSlideArchive.ppam'
}
$SourcePath = [IO.Path]::GetFullPath($SourcePath)
if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "找不到生命周期测试所需 PPAM：$SourcePath"
}

$targetPath = [IO.Path]::GetFullPath((Join-Path $env:APPDATA 'Microsoft\AddIns\PaperFigureSlideArchive.ppam'))
$sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash

$firstInstall = Convert-ScriptJson -Step '首次安装' -Output @(& $installScript -SourcePath $SourcePath)
Assert-True ($firstInstall.status -eq 'installed') '首次安装未报告成功。'
Assert-True (Test-Path -LiteralPath $targetPath -PathType Leaf) '首次安装后 PPAM 不存在。'
Assert-True ((Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash -eq $sourceHash) '首次安装后的 PPAM 哈希不匹配。'

$secondInstall = Convert-ScriptJson -Step '同路径重装' -Output @(& $installScript -SourcePath $SourcePath)
Assert-True ($secondInstall.status -eq 'installed') '同路径重装未报告成功。'
Assert-True ([bool]$secondInstall.replaced_existing) '同路径重装没有识别现有 PPAM。'
Assert-True ((Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash -eq $sourceHash) '重装后的 PPAM 哈希不匹配。'

$uninstall = Convert-ScriptJson -Step '卸载' -Output @(& $uninstallScript)
Assert-True ($uninstall.status -eq 'uninstalled') '卸载未报告成功。'
Assert-True ([bool]$uninstall.file_removed) '卸载后 PPAM 文件仍存在。'
Assert-True ([bool]$uninstall.registration_removed) '卸载后加载项注册仍存在。'
Assert-True (-not (Test-Path -LiteralPath $targetPath)) '卸载后目标路径仍存在。'

$finalInstall = Convert-ScriptJson -Step '最终重装' -Output @(& $installScript -SourcePath $SourcePath)
Assert-True ($finalInstall.status -eq 'installed') '最终重装未报告成功。'
Assert-True (Test-Path -LiteralPath $targetPath -PathType Leaf) '最终重装后 PPAM 不存在。'
Assert-True ((Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash -eq $sourceHash) '最终重装后的 PPAM 哈希不匹配。'

[pscustomobject]@{
    status = 'passed'
    first_install = $true
    reinstall = $true
    uninstall = $true
    final_install = $true
    path = $targetPath
    sha256 = $sourceHash
} | ConvertTo-Json -Depth 3
