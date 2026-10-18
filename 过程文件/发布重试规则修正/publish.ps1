param([ValidateSet('rules','codex')][string]$Batch,[switch]$VerifyOnly,[switch]$Preflight,[string]$ReceiptSuffix='')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Text.UTF8Encoding]::new($false)
$env:GIT_CONFIG_COUNT='2'
$env:GIT_CONFIG_KEY_0='http.sslBackend'
$env:GIT_CONFIG_VALUE_0='openssl'
$env:GIT_CONFIG_KEY_1='http.version'
$env:GIT_CONFIG_VALUE_1='HTTP/1.1'
Import-Module 'D:/BaiduSyncdisk/.agents/automation/ccswitch-skill-sync/CcSwitchSkillSync.psm1' -DisableNameChecking
# Let the supported helper inherit explicit proxies or use the current WinINET proxy.
if($Batch -eq 'rules'){
    $targets=@('agent-rules','skill-check')
    $commit=(git -C 'D:/BaiduSyncdisk/.agents/skills' rev-parse c3db54b).Trim()
}else{
    $targets=@('codex-relay-chain')
    $commit='36677c448ee8b5fdd0a5b356c8dd4695e665212a'
}
$phase=if($Preflight){'preverify'}elseif($VerifyOnly){'verify'}else{'sync'}
$path=Join-Path $PSScriptRoot "$Batch-$phase$ReceiptSuffix.json"
if(Test-Path -LiteralPath $path){throw "Receipt already exists: $path"}
$r=Invoke-CcSwitchSkillSync -Skills $targets -ExpectedRemoteCommit $commit -AllowHistoricalCommit -UpdateTimeoutSeconds 180 -VerifyOnly:($VerifyOnly -or $Preflight)
$r | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $path -Encoding UTF8
$r | Select-Object ok,status,exit_code,message,errors | ConvertTo-Json -Depth 5
exit $r.exit_code
