param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
if(-not [IO.Path]::IsPathRooted($Destination)){throw 'Destination must be an absolute path.'}
$target=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $target){throw 'Choose a new directory; existing projects are never overwritten.'}
$source=Join-Path (Split-Path $PSScriptRoot) 'assets\workbench'
if(-not (Test-Path -LiteralPath (Join-Path $source 'Template_Demo.m'))){throw 'Template incomplete.'}
Copy-Item -LiteralPath $source -Destination $target -Recurse
Write-Output "Template copied to $target. Start with Template_Demo; no hardware was accessed."
