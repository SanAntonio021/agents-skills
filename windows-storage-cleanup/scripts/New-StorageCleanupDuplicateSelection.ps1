#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ScanPath,
    [Parameter(Mandatory)][string]$OutputPath,
    [string[]]$GroupIds=@()
)
$ErrorActionPreference='Stop'
try{
    if(-not $IsWindows){throw 'This tool requires Windows and PowerShell 7.'}
    Import-Module (Join-Path $PSScriptRoot 'StorageCleanup.psm1') -Force
    $result=New-StorageCleanupDuplicateSelection -ScanPath $ScanPath -OutputPath $OutputPath -GroupIds $GroupIds
    $result|ConvertTo-Json -Depth 16
    exit $result.exitCode
}catch{
    [Console]::Error.WriteLine((@{mode='DuplicateSelection';outcome='blocked';exitCode=1;error=$_.Exception.Message}|ConvertTo-Json -Compress))
    exit 1
}
