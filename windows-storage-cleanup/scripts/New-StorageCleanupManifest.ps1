#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SelectionPath,
    [Parameter(Mandatory)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
try {
    if (-not $IsWindows) { throw 'This tool requires Windows and PowerShell 7.' }
    Import-Module (Join-Path $PSScriptRoot 'StorageCleanup.psm1') -Force
    $result = New-StorageCleanupManifest -SelectionPath $SelectionPath -OutputPath $OutputPath
    $result | ConvertTo-Json -Depth 16
    exit $result.exitCode
}
catch {
    [Console]::Error.WriteLine((@{
        mode = 'Manifest'
        outcome = 'blocked'
        exitCode = 1
        error = $_.Exception.Message
    } | ConvertTo-Json -Compress))
    exit 1
}
