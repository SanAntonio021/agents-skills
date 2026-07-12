[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Release-ComObject {
    param([object]$InputObject)
    if ($null -ne $InputObject -and [Runtime.InteropServices.Marshal]::IsComObject($InputObject)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($InputObject)
    }
}

$running = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    throw '卸载前请关闭 PowerPoint；脚本不会结束用户正在运行的 PowerPoint。'
}

$trustedDirectory = [IO.Path]::GetFullPath((Join-Path $env:APPDATA 'Microsoft\AddIns'))
$targetPath = [IO.Path]::Combine($trustedDirectory, 'PaperFigureSlideArchive.ppam')
$powerPoint = $null
$candidate = $null
$removedFromCollection = $false

try {
    $powerPoint = New-Object -ComObject PowerPoint.Application
    for ($index = $powerPoint.AddIns.Count; $index -ge 1; $index--) {
        $candidate = $powerPoint.AddIns.Item($index)
        $candidatePath = [IO.Path]::GetFullPath($candidate.FullName)
        if ([string]::Equals($candidatePath, $targetPath, [StringComparison]::OrdinalIgnoreCase)) {
            $candidate.Loaded = 0
            $candidate.Registered = 0
            try {
                $powerPoint.AddIns.Remove($index)
                $removedFromCollection = $true
            }
            catch {
                $removedFromCollection = ($candidate.Registered -eq 0 -and $candidate.Loaded -eq 0)
            }
            Release-ComObject $candidate
            $candidate = $null
            break
        }
        Release-ComObject $candidate
        $candidate = $null
    }

    $powerPoint.Quit()
    Release-ComObject $powerPoint
    $powerPoint = $null
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()

    if (Test-Path -LiteralPath $targetPath) {
        [IO.File]::Delete($targetPath)
    }

    [pscustomobject]@{
        status = 'uninstalled'
        path = $targetPath
        file_removed = -not (Test-Path -LiteralPath $targetPath)
        registration_removed = $removedFromCollection
    } | ConvertTo-Json -Depth 3
}
finally {
    Release-ComObject $candidate
    if ($null -ne $powerPoint) {
        try { $powerPoint.Quit() } catch {}
    }
    Release-ComObject $powerPoint
}
