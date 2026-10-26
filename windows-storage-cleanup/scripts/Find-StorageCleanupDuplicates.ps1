#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string[]]$Roots,
    [string[]]$PreferredRoots=@(),
    [string]$OutputPath,
    [long]$MinBytes=1
)
$ErrorActionPreference='Stop'
try{
    if(-not $IsWindows){throw 'This tool requires Windows and PowerShell 7.'}
    Import-Module (Join-Path $PSScriptRoot 'StorageCleanup.psm1') -Force
    $arguments=@{Roots=$Roots;PreferredRoots=$PreferredRoots;MinBytes=$MinBytes}
    if($OutputPath){$arguments.OutputPath=$OutputPath}
    $result=New-StorageCleanupDuplicateScan @arguments
    $result|ConvertTo-Json -Depth 32
    exit $result.exitCode
}catch{
    [Console]::Error.WriteLine((@{mode='DuplicateScan';outcome='blocked';exitCode=1;error=$_.Exception.Message}|ConvertTo-Json -Compress))
    exit 1
}
