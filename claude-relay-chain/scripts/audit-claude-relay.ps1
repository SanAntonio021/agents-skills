#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$CcSwitchDb = (Join-Path $env:USERPROFILE '.cc-switch\cc-switch.db'),
    [string]$CcSwitchSettings = (Join-Path $env:USERPROFILE '.cc-switch\settings.json'),
    [string]$ClaudeSettings = (Join-Path $env:USERPROFILE '.claude\settings.json'),
    [string]$DesktopConfigLibrary = (Join-Path $env:LOCALAPPDATA 'Claude-3p\configLibrary'),
    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$checks = New-Object 'System.Collections.Generic.List[object]'
$recommendations = New-Object 'System.Collections.Generic.List[string]'

function Add-Check {
    param(
        [string]$Area,
        [ValidateSet('PASS', 'INFO', 'WARN', 'FAIL', 'UNAVAILABLE')]
        [string]$Status,
        [string]$Detail
    )

    $checks.Add([pscustomobject][ordered]@{
        area = $Area
        status = $Status
        detail = $Detail
    })
}

function Add-Recommendation {
    param([string]$Text)

    if (-not $recommendations.Contains($Text)) {
        $recommendations.Add($Text)
    }
}

function Get-PropertyValue {
    param(
        [AllowNull()]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

function Read-JsonFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-SafeUrl {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return 'absent'
    }

    try {
        $uri = [Uri]$Value
        if (-not $uri.IsAbsoluteUri) {
            return '<invalid or redacted>'
        }

        $builder = New-Object System.UriBuilder($uri)
        $builder.UserName = ''
        $builder.Password = ''
        $builder.Query = ''
        $builder.Fragment = ''
        return $builder.Uri.AbsoluteUri.TrimEnd('/')
    }
    catch {
        return '<invalid or redacted>'
    }
}

function Get-NormalizedUrl {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    try {
        $uri = [Uri]$Value
        if (-not $uri.IsAbsoluteUri) {
            return $null
        }

        $portPart = ''
        if (-not $uri.IsDefaultPort) {
            $portPart = ':' + $uri.Port
        }
        $path = $uri.AbsolutePath.TrimEnd('/')
        return ('{0}://{1}{2}{3}' -f $uri.Scheme.ToLowerInvariant(), $uri.Host.ToLowerInvariant(), $portPart, $path)
    }
    catch {
        return $null
    }
}

function Get-ModelCount {
    param([AllowNull()]$Value)

    if ($null -eq $Value) {
        return 0
    }

    if ($Value -is [string]) {
        if ([string]::IsNullOrWhiteSpace($Value)) {
            return 0
        }
        try {
            $parsed = $Value | ConvertFrom-Json
            return @($parsed).Count
        }
        catch {
            return -1
        }
    }

    return @($Value).Count
}

function Get-RegistryPolicySummary {
    param(
        [string]$Label,
        [string]$Path
    )

    $summary = [ordered]@{
        label = $Label
        path = $Path
        present = $false
        propertyCount = 0
        inferenceProvider = $null
        gatewayBaseUrl = 'absent'
        credentialPresent = $false
    }

    try {
        if (-not (Test-Path -LiteralPath $Path)) {
            return [pscustomobject]$summary
        }

        $item = Get-ItemProperty -LiteralPath $Path
        $names = @($item.PSObject.Properties.Name | Where-Object { $_ -notmatch '^PS(Path|ParentPath|ChildName|Drive|Provider)$' })
        $summary.present = $true
        $summary.propertyCount = $names.Count
        $summary.inferenceProvider = Get-PropertyValue -Object $item -Name 'inferenceProvider'
        $summary.gatewayBaseUrl = Get-SafeUrl -Value (Get-PropertyValue -Object $item -Name 'inferenceGatewayBaseUrl')
        $credential = Get-PropertyValue -Object $item -Name 'inferenceGatewayApiKey'
        $summary.credentialPresent = -not [string]::IsNullOrWhiteSpace([string]$credential)
    }
    catch {
        $summary.present = $true
        $summary['readError'] = $_.Exception.GetType().Name
    }

    return [pscustomobject]$summary
}

function Invoke-CcSwitchDbAudit {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject]@{
            available = $false
            reason = 'database file not found'
            providers = @()
            proxyConfig = @()
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $python) {
        return [pscustomobject]@{
            available = $false
            reason = 'Python 3 not found; SQLite inspection skipped'
            providers = @()
            proxyConfig = @()
        }
    }

    $pythonCode = @'
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def parse_json(raw):
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def safe_url(value):
    if not isinstance(value, str) or not value.strip():
        return "absent"
    try:
        parts = urlsplit(value.strip())
        if not parts.scheme or not parts.hostname:
            return "<invalid or redacted>"
        host = parts.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parts.port is not None:
            host = f"{host}:{parts.port}"
        path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme.lower(), host.lower(), path, "", ""))
    except Exception:
        return "<invalid or redacted>"


def route_summary(routes):
    if not isinstance(routes, dict):
        return 0, 0, []
    non_identity = 0
    pairs = []
    for source, config in routes.items():
        target = config.get("model") if isinstance(config, dict) else None
        if isinstance(target, str) and target and target != source:
            non_identity += 1
        pairs.append({"source": str(source), "target": str(target or "absent")})
    return len(routes), non_identity, pairs


db_path = Path(os.environ["CLAUDE_RELAY_AUDIT_DB"]).resolve().as_posix()
connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row

providers = []
for row in connection.execute(
    "SELECT id, app_type, name, provider_type, settings_config, meta, is_current "
    "FROM providers WHERE app_type IN ('claude', 'claude-desktop') AND is_current = 1 "
    "ORDER BY app_type"
):
    settings = parse_json(row["settings_config"])
    meta = parse_json(row["meta"])
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    routes = meta.get("claudeDesktopModelRoutes")
    route_count, non_identity_count, route_pairs = route_summary(routes)
    providers.append({
        "id": row["id"],
        "appType": row["app_type"],
        "name": row["name"],
        "providerType": row["provider_type"],
        "baseUrl": safe_url(env.get("ANTHROPIC_BASE_URL")),
        "credentialPresent": bool(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY")),
        "model": settings.get("model") or env.get("ANTHROPIC_MODEL") or "absent",
        "desktopMode": meta.get("claudeDesktopMode") or "unknown",
        "apiFormat": meta.get("apiFormat") or "unknown",
        "routeCount": route_count,
        "nonIdentityRouteCount": non_identity_count,
        "routes": route_pairs,
    })

proxy_config = []
columns = {row[1] for row in connection.execute("PRAGMA table_info(proxy_config)")}
wanted = [
    "app_type", "proxy_enabled", "enabled", "listen_address", "listen_port",
    "auto_failover_enabled", "live_takeover_active"
]
selected = [name for name in wanted if name in columns]
if selected:
    sql = "SELECT " + ", ".join(selected) + " FROM proxy_config WHERE app_type IN ('claude', 'claude-desktop')"
    for row in connection.execute(sql):
        proxy_config.append({name: row[name] for name in selected})

connection.close()
print(json.dumps({"available": True, "providers": providers, "proxyConfig": proxy_config}, ensure_ascii=False))
'@

    $oldDbEnvironment = [Environment]::GetEnvironmentVariable('CLAUDE_RELAY_AUDIT_DB', 'Process')
    $oldPythonIoEncoding = [Environment]::GetEnvironmentVariable('PYTHONIOENCODING', 'Process')
    $oldPythonUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('CLAUDE_RELAY_AUDIT_DB', $Path, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8', 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'Process')
        $rawOutput = $pythonCode | & $python.Source - 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($rawOutput -join ''))) {
            throw 'Python SQLite audit failed'
        }
        return (($rawOutput -join "`n") | ConvertFrom-Json)
    }
    catch {
        return [pscustomobject]@{
            available = $false
            reason = $_.Exception.Message
            providers = @()
            proxyConfig = @()
        }
    }
    finally {
        [Environment]::SetEnvironmentVariable('CLAUDE_RELAY_AUDIT_DB', $oldDbEnvironment, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', $oldPythonIoEncoding, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONUTF8', $oldPythonUtf8, 'Process')
    }
}

$surfaces = [ordered]@{
    ccSwitch = [ordered]@{}
    standaloneClaudeCode = [ordered]@{}
    desktop3p = [ordered]@{}
}

# CC Switch process and version
$ccSwitchProcess = Get-Process -Name 'cc-switch' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $ccSwitchProcess) {
    Add-Check -Area 'CC Switch process' -Status 'WARN' -Detail 'cc-switch process is not running.'
    Add-Recommendation 'Confirm whether CC Switch should be running before proposing any restart.'
    $surfaces.ccSwitch.processRunning = $false
}
else {
    $surfaces.ccSwitch.processRunning = $true
    $surfaces.ccSwitch.processId = $ccSwitchProcess.Id
    $version = 'unknown'
    try {
        if (-not [string]::IsNullOrWhiteSpace($ccSwitchProcess.Path)) {
            $version = (Get-Item -LiteralPath $ccSwitchProcess.Path).VersionInfo.ProductVersion
        }
    }
    catch {
        $version = 'unknown'
    }
    $surfaces.ccSwitch.version = $version
    Add-Check -Area 'CC Switch process' -Status 'PASS' -Detail ("running; version={0}; pid={1}" -f $version, $ccSwitchProcess.Id)
}

# CC Switch settings
$ccSettings = $null
try {
    $ccSettings = Read-JsonFile -Path $CcSwitchSettings
    if ($null -eq $ccSettings) {
        Add-Check -Area 'CC Switch settings' -Status 'WARN' -Detail 'settings.json was not found.'
    }
    else {
        $currentClaude = Get-PropertyValue -Object $ccSettings -Name 'currentProviderClaude'
        $currentDesktop = Get-PropertyValue -Object $ccSettings -Name 'currentProviderClaudeDesktop'
        $surfaces.ccSwitch.currentProviderClaude = $currentClaude
        $surfaces.ccSwitch.currentProviderClaudeDesktop = $currentDesktop
        Add-Check -Area 'CC Switch provider selectors' -Status 'INFO' -Detail ("Claude={0}; Claude Desktop={1}" -f ($currentClaude -as [string]), ($currentDesktop -as [string]))
    }
}
catch {
    Add-Check -Area 'CC Switch settings' -Status 'WARN' -Detail ("could not parse settings.json: {0}" -f $_.Exception.GetType().Name)
}

# Standalone Claude Code settings
try {
    $claude = Read-JsonFile -Path $ClaudeSettings
    if ($null -eq $claude) {
        Add-Check -Area 'Standalone Claude Code' -Status 'WARN' -Detail '.claude\settings.json was not found.'
        $surfaces.standaloneClaudeCode.settingsPresent = $false
    }
    else {
        $envObject = Get-PropertyValue -Object $claude -Name 'env'
        $baseUrl = Get-PropertyValue -Object $envObject -Name 'ANTHROPIC_BASE_URL'
        $authToken = Get-PropertyValue -Object $envObject -Name 'ANTHROPIC_AUTH_TOKEN'
        $apiKey = Get-PropertyValue -Object $envObject -Name 'ANTHROPIC_API_KEY'
        $model = Get-PropertyValue -Object $claude -Name 'model'
        $effort = Get-PropertyValue -Object $claude -Name 'effortLevel'
        $credentialPresent = (-not [string]::IsNullOrWhiteSpace([string]$authToken)) -or (-not [string]::IsNullOrWhiteSpace([string]$apiKey))

        $surfaces.standaloneClaudeCode.settingsPresent = $true
        $surfaces.standaloneClaudeCode.baseUrl = Get-SafeUrl -Value $baseUrl
        $surfaces.standaloneClaudeCode.credentialPresent = $credentialPresent
        $surfaces.standaloneClaudeCode.model = $model
        $surfaces.standaloneClaudeCode.effortLevel = $effort
        Add-Check -Area 'Standalone Claude Code' -Status 'INFO' -Detail ("baseUrl={0}; credential={1}; model={2}; effort={3}" -f (Get-SafeUrl -Value $baseUrl), $(if ($credentialPresent) { 'present' } else { 'absent' }), ($model -as [string]), ($effort -as [string]))
    }
}
catch {
    Add-Check -Area 'Standalone Claude Code' -Status 'WARN' -Detail ("could not parse settings.json: {0}" -f $_.Exception.GetType().Name)
}

# Desktop managed policy precedence
$hklmPolicy = Get-RegistryPolicySummary -Label 'HKLM' -Path 'HKLM:\SOFTWARE\Policies\Claude'
$hkcuPolicy = Get-RegistryPolicySummary -Label 'HKCU' -Path 'HKCU:\SOFTWARE\Policies\Claude'
$surfaces.desktop3p.hklmPolicy = $hklmPolicy
$surfaces.desktop3p.hkcuPolicy = $hkcuPolicy

$desktopConfigSource = 'local configLibrary'
if ($hklmPolicy.present) {
    $desktopConfigSource = 'HKLM managed policy'
    Add-Check -Area 'Desktop 3P configuration source' -Status 'INFO' -Detail ("HKLM managed policy present; propertyCount={0}; local profile may be ignored." -f $hklmPolicy.propertyCount)
}
elseif ($hkcuPolicy.present) {
    $desktopConfigSource = 'HKCU managed policy'
    Add-Check -Area 'Desktop 3P configuration source' -Status 'INFO' -Detail ("HKCU managed policy present; propertyCount={0}; local profile may be ignored." -f $hkcuPolicy.propertyCount)
}
else {
    Add-Check -Area 'Desktop 3P configuration source' -Status 'PASS' -Detail 'no HKLM/HKCU managed policy detected; local configLibrary is active source.'
}
$surfaces.desktop3p.configSource = $desktopConfigSource

# Desktop local applied profile
$desktopProfileRawBaseUrl = $null
$desktopAppliedId = $null
try {
    $metaPath = Join-Path $DesktopConfigLibrary '_meta.json'
    $desktopMeta = Read-JsonFile -Path $metaPath
    if ($null -eq $desktopMeta) {
        Add-Check -Area 'Desktop 3P applied profile' -Status 'WARN' -Detail '_meta.json was not found.'
        Add-Recommendation 'Open Claude Desktop third-party inference configuration and confirm which profile is applied.'
    }
    else {
        $desktopAppliedId = Get-PropertyValue -Object $desktopMeta -Name 'appliedId'
        $profileName = 'unknown'
        foreach ($entry in @(Get-PropertyValue -Object $desktopMeta -Name 'entries')) {
            if ((Get-PropertyValue -Object $entry -Name 'id') -eq $desktopAppliedId) {
                $profileName = Get-PropertyValue -Object $entry -Name 'name'
                break
            }
        }

        $profilePath = Join-Path $DesktopConfigLibrary (([string]$desktopAppliedId) + '.json')
        $profile = Read-JsonFile -Path $profilePath
        if ($null -eq $profile) {
            Add-Check -Area 'Desktop 3P applied profile' -Status 'FAIL' -Detail ("appliedId={0}; profile file missing." -f $desktopAppliedId)
            Add-Recommendation 'Re-apply a valid Desktop 3P profile after explicit approval.'
        }
        else {
            $desktopProfileRawBaseUrl = Get-PropertyValue -Object $profile -Name 'inferenceGatewayBaseUrl'
            $provider = Get-PropertyValue -Object $profile -Name 'inferenceProvider'
            $authScheme = Get-PropertyValue -Object $profile -Name 'inferenceGatewayAuthScheme'
            if ([string]::IsNullOrWhiteSpace([string]$authScheme)) {
                $authScheme = 'default/unspecified'
            }
            $credential = Get-PropertyValue -Object $profile -Name 'inferenceGatewayApiKey'
            $credentialPresent = -not [string]::IsNullOrWhiteSpace([string]$credential)
            $modelCount = Get-ModelCount -Value (Get-PropertyValue -Object $profile -Name 'inferenceModels')

            $surfaces.desktop3p.appliedId = $desktopAppliedId
            $surfaces.desktop3p.appliedName = $profileName
            $surfaces.desktop3p.inferenceProvider = $provider
            $surfaces.desktop3p.gatewayBaseUrl = Get-SafeUrl -Value $desktopProfileRawBaseUrl
            $surfaces.desktop3p.authScheme = $authScheme
            $surfaces.desktop3p.credentialPresent = $credentialPresent
            $surfaces.desktop3p.inferenceModelCount = $modelCount
            Add-Check -Area 'Desktop 3P applied profile' -Status 'INFO' -Detail ("name={0}; id={1}; provider={2}; baseUrl={3}; authScheme={4}; credential={5}; inferenceModels={6}" -f $profileName, $desktopAppliedId, $provider, (Get-SafeUrl -Value $desktopProfileRawBaseUrl), $authScheme, $(if ($credentialPresent) { 'present' } else { 'absent' }), $modelCount)

            if ($provider -ne 'gateway') {
                Add-Check -Area 'Desktop 3P provider type' -Status 'WARN' -Detail ("applied inferenceProvider is {0}, not gateway." -f $provider)
            }
            elseif (-not $credentialPresent) {
                Add-Check -Area 'Desktop 3P credential' -Status 'WARN' -Detail 'gateway credential is absent; value was not displayed.'
            }
        }
    }
}
catch {
    Add-Check -Area 'Desktop 3P applied profile' -Status 'WARN' -Detail ("could not inspect local profile: {0}" -f $_.Exception.GetType().Name)
}

# CC Switch database
$dbAudit = Invoke-CcSwitchDbAudit -Path $CcSwitchDb
$surfaces.ccSwitch.dbAuditAvailable = [bool](Get-PropertyValue -Object $dbAudit -Name 'available')
$desktopProvider = $null
$claudeProvider = $null
$proxyRow = $null
if (-not $surfaces.ccSwitch.dbAuditAvailable) {
    $reason = Get-PropertyValue -Object $dbAudit -Name 'reason'
    Add-Check -Area 'CC Switch database' -Status 'UNAVAILABLE' -Detail ([string]$reason)
    Add-Recommendation 'Do not infer CC Switch direct/proxy mode until the database can be inspected read-only.'
}
else {
    Add-Check -Area 'CC Switch database' -Status 'PASS' -Detail 'opened with SQLite mode=ro; only redacted fields were returned.'
    foreach ($provider in @(Get-PropertyValue -Object $dbAudit -Name 'providers')) {
        $appType = Get-PropertyValue -Object $provider -Name 'appType'
        if ($appType -eq 'claude-desktop') {
            $desktopProvider = $provider
        }
        elseif ($appType -eq 'claude') {
            $claudeProvider = $provider
        }
    }
    foreach ($row in @(Get-PropertyValue -Object $dbAudit -Name 'proxyConfig')) {
        if ((Get-PropertyValue -Object $row -Name 'app_type') -eq 'claude') {
            $proxyRow = $row
            break
        }
    }

    if ($null -eq $claudeProvider) {
        Add-Check -Area 'CC Switch Claude provider' -Status 'WARN' -Detail 'no current app_type=claude provider was found.'
    }
    else {
        $surfaces.ccSwitch.claudeProvider = $claudeProvider
        Add-Check -Area 'CC Switch Claude provider' -Status 'INFO' -Detail ("name={0}; baseUrl={1}; credential={2}; model={3}" -f (Get-PropertyValue -Object $claudeProvider -Name 'name'), (Get-PropertyValue -Object $claudeProvider -Name 'baseUrl'), $(if (Get-PropertyValue -Object $claudeProvider -Name 'credentialPresent') { 'present' } else { 'absent' }), (Get-PropertyValue -Object $claudeProvider -Name 'model'))
    }

    if ($null -eq $desktopProvider) {
        Add-Check -Area 'CC Switch Claude Desktop provider' -Status 'FAIL' -Detail 'no current app_type=claude-desktop provider was found.'
        Add-Recommendation 'Select or create a Claude Desktop provider in CC Switch only after explicit approval.'
    }
    else {
        $mode = [string](Get-PropertyValue -Object $desktopProvider -Name 'desktopMode')
        $apiFormat = [string](Get-PropertyValue -Object $desktopProvider -Name 'apiFormat')
        $routeCount = [int](Get-PropertyValue -Object $desktopProvider -Name 'routeCount')
        $nonIdentityRouteCount = [int](Get-PropertyValue -Object $desktopProvider -Name 'nonIdentityRouteCount')
        $surfaces.ccSwitch.claudeDesktopProvider = $desktopProvider
        $surfaces.ccSwitch.claudeDesktopMode = $mode
        Add-Check -Area 'CC Switch Claude Desktop provider' -Status 'INFO' -Detail ("name={0}; mode={1}; apiFormat={2}; baseUrl={3}; credential={4}; routes={5}; nonIdentityRoutes={6}" -f (Get-PropertyValue -Object $desktopProvider -Name 'name'), $mode, $apiFormat, (Get-PropertyValue -Object $desktopProvider -Name 'baseUrl'), $(if (Get-PropertyValue -Object $desktopProvider -Name 'credentialPresent') { 'present' } else { 'absent' }), $routeCount, $nonIdentityRouteCount)

        if ($mode -eq 'direct') {
            if ($apiFormat -ne 'anthropic') {
                Add-Check -Area 'CC Switch Desktop mode validity' -Status 'FAIL' -Detail ("direct mode requires apiFormat=anthropic; actual={0}." -f $apiFormat)
                Add-Recommendation 'Use local routing/model mapping for a non-Anthropic upstream; wait for approval before changing mode.'
            }
            elseif ($nonIdentityRouteCount -gt 0) {
                Add-Check -Area 'CC Switch Desktop mode validity' -Status 'FAIL' -Detail 'direct mode contains non-identity model mappings.'
                Add-Recommendation 'Use local routing/model mapping for translated model names; wait for approval before changing mode.'
            }
            else {
                Add-Check -Area 'CC Switch Desktop mode validity' -Status 'PASS' -Detail 'direct mode uses Anthropic format and has no non-identity model mapping.'
            }
        }
        elseif ($mode -eq 'proxy') {
            if ($routeCount -lt 1) {
                Add-Check -Area 'CC Switch Desktop mode validity' -Status 'FAIL' -Detail 'proxy mode has no model route mapping.'
                Add-Recommendation 'Define at least one Claude model route after explicit approval.'
            }
            else {
                Add-Check -Area 'CC Switch Desktop mode validity' -Status 'PASS' -Detail ("proxy mode has {0} model route mapping(s)." -f $routeCount)
            }
        }
        else {
            Add-Check -Area 'CC Switch Desktop mode validity' -Status 'WARN' -Detail ("desktop mode is unknown: {0}" -f $mode)
            Add-Recommendation 'Do not choose direct or proxy remediation until the provider mode is explicit.'
        }
    }
}

# Listener state, based on DB when available
$listenAddress = '127.0.0.1'
$listenPort = 15721
if ($null -ne $proxyRow) {
    $dbAddress = Get-PropertyValue -Object $proxyRow -Name 'listen_address'
    $dbPort = Get-PropertyValue -Object $proxyRow -Name 'listen_port'
    if (-not [string]::IsNullOrWhiteSpace([string]$dbAddress)) {
        $listenAddress = [string]$dbAddress
    }
    if ($null -ne $dbPort) {
        $listenPort = [int]$dbPort
    }
    $surfaces.ccSwitch.proxyConfig = $proxyRow
}

$listenerFound = $false
try {
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $listenerFound = @(
            Get-NetTCPConnection -State Listen -LocalPort $listenPort -ErrorAction SilentlyContinue
        ).Count -gt 0
    }
}
catch {
    $listenerFound = $false
}
$surfaces.ccSwitch.listenAddress = $listenAddress
$surfaces.ccSwitch.listenPort = $listenPort
$surfaces.ccSwitch.listenerFound = $listenerFound
if ($listenerFound) {
    Add-Check -Area 'CC Switch listener' -Status 'PASS' -Detail ("port {0} is listening; configured address={1}." -f $listenPort, $listenAddress)
}
else {
    Add-Check -Area 'CC Switch listener' -Status 'WARN' -Detail ("port {0} is not listening; configured address={1}." -f $listenPort, $listenAddress)
}

# Cross-check CC Switch selectors against current DB records.
if ($null -ne $ccSettings -and $null -ne $desktopProvider) {
    $selector = [string](Get-PropertyValue -Object $ccSettings -Name 'currentProviderClaudeDesktop')
    $dbId = [string](Get-PropertyValue -Object $desktopProvider -Name 'id')
    if ($selector -eq $dbId) {
        Add-Check -Area 'Claude Desktop provider selector consistency' -Status 'PASS' -Detail 'settings.json selector matches providers.is_current.'
    }
    else {
        Add-Check -Area 'Claude Desktop provider selector consistency' -Status 'FAIL' -Detail 'settings.json selector does not match providers.is_current.'
        Add-Recommendation 'Re-apply the intended Claude Desktop provider after explicit approval; do not hand-edit both stores blindly.'
    }
}
if ($null -ne $ccSettings -and $null -ne $claudeProvider) {
    $selector = [string](Get-PropertyValue -Object $ccSettings -Name 'currentProviderClaude')
    $dbId = [string](Get-PropertyValue -Object $claudeProvider -Name 'id')
    if ($selector -eq $dbId) {
        Add-Check -Area 'Claude provider selector consistency' -Status 'PASS' -Detail 'settings.json selector matches providers.is_current.'
    }
    else {
        Add-Check -Area 'Claude provider selector consistency' -Status 'FAIL' -Detail 'settings.json selector does not match providers.is_current.'
    }
}

# Compare active local Desktop profile with CC Switch's expected route only when local config is authoritative.
if ($desktopConfigSource -eq 'local configLibrary' -and $null -ne $desktopProvider -and -not [string]::IsNullOrWhiteSpace([string]$desktopProfileRawBaseUrl)) {
    $mode = [string](Get-PropertyValue -Object $desktopProvider -Name 'desktopMode')
    $expectedBaseUrl = $null
    if ($mode -eq 'direct') {
        $expectedBaseUrl = [string](Get-PropertyValue -Object $desktopProvider -Name 'baseUrl')
    }
    elseif ($mode -eq 'proxy') {
        $hostForProfile = $listenAddress
        if ($hostForProfile -in @('0.0.0.0', '::', '[::]')) {
            $hostForProfile = '127.0.0.1'
        }
        if ($hostForProfile.Contains(':') -and -not $hostForProfile.StartsWith('[')) {
            $hostForProfile = '[' + $hostForProfile + ']'
        }
        $expectedBaseUrl = 'http://{0}:{1}/claude-desktop' -f $hostForProfile, $listenPort
    }

    if (-not [string]::IsNullOrWhiteSpace($expectedBaseUrl)) {
        $actualNormalized = Get-NormalizedUrl -Value $desktopProfileRawBaseUrl
        $expectedNormalized = Get-NormalizedUrl -Value $expectedBaseUrl
        $surfaces.desktop3p.expectedGatewayBaseUrl = Get-SafeUrl -Value $expectedBaseUrl
        if ($actualNormalized -eq $expectedNormalized) {
            Add-Check -Area 'Desktop profile and CC Switch consistency' -Status 'PASS' -Detail ("applied base URL matches {0} mode expectation." -f $mode)
        }
        else {
            Add-Check -Area 'Desktop profile and CC Switch consistency' -Status 'FAIL' -Detail ("mode={0}; expected={1}; actual={2}" -f $mode, (Get-SafeUrl -Value $expectedBaseUrl), (Get-SafeUrl -Value $desktopProfileRawBaseUrl))
            Add-Recommendation 'Inspect managed-policy precedence and re-apply the intended Desktop provider only after explicit approval.'
        }
    }
}

$failCount = @($checks | Where-Object { $_.status -eq 'FAIL' }).Count
$warnCount = @($checks | Where-Object { $_.status -eq 'WARN' }).Count
$unavailableCount = @($checks | Where-Object { $_.status -eq 'UNAVAILABLE' }).Count
$overall = 'PASS'
if ($failCount -gt 0) {
    $overall = 'FAIL'
}
elseif ($warnCount -gt 0 -or $unavailableCount -gt 0) {
    $overall = 'WARN'
}

if ($recommendations.Count -eq 0) {
    Add-Recommendation 'Static checks are consistent. Do not claim end-to-end success until approved model discovery, Messages streaming, tool use, and target-surface checks pass.'
}
else {
    Add-Recommendation 'Keep all remediation read-only until the user explicitly approves the exact backup, change, restart, verification, and rollback plan.'
}

$result = [pscustomobject][ordered]@{
    tool = 'audit-claude-relay'
    schemaVersion = 1
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    readOnly = $true
    secretsRedacted = $true
    overall = $overall
    summary = [pscustomobject][ordered]@{
        failed = $failCount
        warnings = $warnCount
        unavailable = $unavailableCount
        totalChecks = $checks.Count
    }
    surfaces = [pscustomobject]$surfaces
    checks = $checks.ToArray()
    recommendations = $recommendations.ToArray()
}

if ($AsJson) {
    $result | ConvertTo-Json -Depth 12
    exit 0
}

Write-Output 'Claude relay audit (read-only; secrets redacted)'
Write-Output ("Generated: {0}" -f $result.generatedAt)
Write-Output ("Overall: {0}" -f $result.overall)
Write-Output ''
foreach ($check in $checks) {
    Write-Output ("[{0}] {1}: {2}" -f $check.status, $check.area, $check.detail)
}
Write-Output ''
Write-Output 'Recommendations:'
foreach ($item in $recommendations) {
    Write-Output ('- ' + $item)
}
Write-Output ''
Write-Output 'No files, registry values, database rows, processes, or network endpoints were changed.'

exit 0
