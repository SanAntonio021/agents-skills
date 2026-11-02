#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('Check', 'Execute', 'Resume', 'Status', 'Verify')]
    [string]$Mode = 'Check',
    [Parameter(Mandatory)]
    [string]$ManifestPath,
    [string]$StateDirectory,
    [string[]]$ItemIds
)

$ErrorActionPreference = 'Stop'
try {
    if (-not $IsWindows) { throw 'This tool requires Windows and PowerShell 7.' }
    Import-Module (Join-Path $PSScriptRoot 'StorageCleanup.psm1') -Force
    $arguments = @{ Mode = $Mode; ManifestPath = $ManifestPath }
    if ($StateDirectory) { $arguments.StateDirectory = $StateDirectory }
    if ($PSBoundParameters.ContainsKey('ItemIds')) { $arguments.ItemIds = @($ItemIds | ForEach-Object { $_.Split(',') }) }
    $result = Invoke-StorageCleanup @arguments
    $result | ConvertTo-Json -Depth 32
    exit $result.exitCode
}
catch {
    [Console]::Error.WriteLine((@{
        mode = $Mode
        outcome = 'blocked'
        exitCode = 1
        error = $_.Exception.Message
    } | ConvertTo-Json -Compress))
    exit 1
}
