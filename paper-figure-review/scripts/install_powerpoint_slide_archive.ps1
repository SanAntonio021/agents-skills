[CmdletBinding()]
param(
    [string]$SourcePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Release-ComObject {
    param([object]$InputObject)
    if ($null -ne $InputObject -and [Runtime.InteropServices.Marshal]::IsComObject($InputObject)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($InputObject)
    }
}

function Assert-PowerPointClosed {
    $running = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue)
    if ($running.Count -gt 0) {
        throw '安装前请关闭 PowerPoint；脚本不会结束用户正在运行的 PowerPoint。'
    }
}

function Find-PowerPointAddIn {
    param(
        [object]$Application,
        [string]$ExpectedPath
    )

    for ($index = 1; $index -le $Application.AddIns.Count; $index++) {
        $candidate = $Application.AddIns.Item($index)
        $candidatePath = $candidate.FullName
        if ([string]::Equals([IO.Path]::GetFullPath($candidatePath), $ExpectedPath, [StringComparison]::OrdinalIgnoreCase)) {
            return $candidate
        }
        Release-ComObject $candidate
    }
    return $null
}

Assert-PowerPointClosed

$skillRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($SourcePath)) {
    $SourcePath = Join-Path $skillRoot 'assets\powerpoint-slide-archive\PaperFigureSlideArchive.ppam'
}
$SourcePath = [IO.Path]::GetFullPath($SourcePath)
if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "找不到待安装 PPAM：$SourcePath"
}

$trustedDirectory = [IO.Path]::GetFullPath((Join-Path $env:APPDATA 'Microsoft\AddIns'))
[IO.Directory]::CreateDirectory($trustedDirectory) | Out-Null
$targetPath = [IO.Path]::Combine($trustedDirectory, 'PaperFigureSlideArchive.ppam')
$transactionId = [Guid]::NewGuid().ToString('N')
$stagedPath = [IO.Path]::Combine($trustedDirectory, ".PaperFigureSlideArchive.$transactionId.staged.ppam")
$backupPath = [IO.Path]::Combine($trustedDirectory, ".PaperFigureSlideArchive.$transactionId.backup.ppam")
$hadExistingTarget = Test-Path -LiteralPath $targetPath -PathType Leaf
$targetPlaced = $false
$installSucceeded = $false
$powerPoint = $null
$addIn = $null
$result = $null

[IO.File]::Copy($SourcePath, $stagedPath, $true)
try {
    if ($hadExistingTarget) {
        [IO.File]::Move($targetPath, $backupPath)
    }
    [IO.File]::Move($stagedPath, $targetPath)
    $targetPlaced = $true

    try {
        $powerPoint = New-Object -ComObject PowerPoint.Application
        $addIn = Find-PowerPointAddIn -Application $powerPoint -ExpectedPath $targetPath
        if ($null -eq $addIn) {
            $addIn = $powerPoint.AddIns.Add($targetPath)
        }
        $addIn.Registered = -1
        $addIn.Loaded = -1

        $registered = $addIn.Registered
        $loaded = $addIn.Loaded
        if ($registered -ne -1 -or $loaded -ne -1) {
            throw 'PowerPoint 未确认加载项已注册并加载。'
        }
    }
    finally {
        if ($null -ne $powerPoint) {
            try { $powerPoint.Quit() } catch {}
        }
        Release-ComObject $addIn
        Release-ComObject $powerPoint
        $addIn = $null
        $powerPoint = $null
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }

    $result = [pscustomobject]@{
        status = 'installed'
        path = $targetPath
        sha256 = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash
        registered = $true
        loaded = $true
        replaced_existing = $hadExistingTarget
    }
    if (Test-Path -LiteralPath $backupPath) {
        [IO.File]::Delete($backupPath)
    }
    $installSucceeded = $true
}
catch {
    $installError = $_
    try {
        if ($targetPlaced -and (Test-Path -LiteralPath $targetPath)) {
            [IO.File]::Delete($targetPath)
        }
        if (Test-Path -LiteralPath $backupPath) {
            [IO.File]::Move($backupPath, $targetPath)
        }
    }
    catch {
        throw "安装失败，且原版本回滚失败。安装错误：$($installError.Exception.Message)；回滚错误：$($_.Exception.Message)"
    }
    throw $installError
}
finally {
    if ($null -ne $powerPoint) {
        try { $powerPoint.Quit() } catch {}
    }
    Release-ComObject $addIn
    Release-ComObject $powerPoint
    if (Test-Path -LiteralPath $stagedPath) {
        [IO.File]::Delete($stagedPath)
    }
    if ($installSucceeded -and (Test-Path -LiteralPath $backupPath)) {
        [IO.File]::Delete($backupPath)
    }
}

$result | ConvertTo-Json -Depth 3
