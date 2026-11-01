#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$CcSwitchDb = (Join-Path $env:USERPROFILE '.cc-switch\cc-switch.db'),
    [string]$CcSwitchSettings = (Join-Path $env:USERPROFILE '.cc-switch\settings.json'),
    [string]$ClaudeSettings = (Join-Path $env:USERPROFILE '.claude\settings.json'),
    [string]$DesktopConfigLibrary = (Join-Path $env:LOCALAPPDATA 'Claude-3p\configLibrary'),
    [switch]$AsJson,
    [string]$DesktopBridge,
    [string]$DesktopStateRoot = (Join-Path $env:LOCALAPPDATA 'ccswitch-desktop')
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

function Invoke-CcSwitchDesktopAudit {
    # CcSwitchDb is retained for compatibility and is never opened.
    $unavailable = [ordered]@{
        available = $false
        reason = 'desktop_bridge_unavailable'
        source = 'official-desktop-cdp'
        databaseRead = $false
        providers = @()
        proxyConfig = @()
    }
    try {
        $bridgePath = $DesktopBridge
        if ([string]::IsNullOrWhiteSpace($bridgePath)) {
            $bridgePath = $env:CCSWITCH_DESKTOP_MODULE
        }
        if ([string]::IsNullOrWhiteSpace($bridgePath)) {
            # Works in the maintained source tree. Runtime copies use an explicit path.
            $bridgePath = Join-Path $PSScriptRoot '..\..\..\automation\ccswitch-desktop\CcSwitchDesktop.psm1'
        }
        if (-not [IO.Path]::IsPathRooted($bridgePath) -or
            -not (Test-Path -LiteralPath $bridgePath -PathType Leaf)) {
            return [pscustomobject]$unavailable
        }
        $bridge = Import-Module -Name $bridgePath -Scope Local -PassThru -ErrorAction Stop
        $invoke = $bridge.ExportedCommands['Invoke-CcSwitchDesktopRequest']
        if ($null -eq $invoke) { return [pscustomobject]$unavailable }
        $receipt = & $invoke -Action 'claude-diagnostics' -Request @{TimeoutSeconds=5} -StateRoot $DesktopStateRoot
        if ((Get-PropertyValue -Object $receipt -Name 'exit_code') -ne 0 -or
            (Get-PropertyValue -Object $receipt -Name 'diagnostic_schema_version') -ne 2) {
            $reason = [string](Get-PropertyValue -Object $receipt -Name 'error_code')
            if ($reason -match '^[a-z_]{1,100}$') { $unavailable.reason = $reason }
            return [pscustomobject]$unavailable
        }
        return $receipt
    }
    catch {
        return [pscustomobject]$unavailable
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

# Official desktop query; the legacy database argument is never accessed.
$desktopAudit = Invoke-CcSwitchDesktopAudit
$surfaces.ccSwitch.dbAuditAvailable = $false
$surfaces.ccSwitch.databaseRead = $false
$surfaces.ccSwitch.auditSource = 'official-desktop-cdp'
$surfaces.ccSwitch.desktopAuditAvailable = [bool](Get-PropertyValue -Object $desktopAudit -Name 'available')
$desktopProvider = $null
$claudeProvider = $null
$proxyRow = $null
if (-not $surfaces.ccSwitch.desktopAuditAvailable) {
    $reason = Get-PropertyValue -Object $desktopAudit -Name 'reason'
    Add-Check -Area 'CC Switch official desktop' -Status 'UNAVAILABLE' -Detail ([string]$reason)
    Add-Recommendation 'Do not infer CC Switch direct/proxy mode until official desktop queries are available.'
}
else {
    Add-Check -Area 'CC Switch official desktop' -Status 'PASS' -Detail 'official queries succeeded; only redacted fields were returned; database was not opened.'
    $surfaces.ccSwitch.unavailableFields = @(Get-PropertyValue -Object $desktopAudit -Name 'unavailableFields')
    Add-Check -Area 'CC Switch historical failover evidence' -Status 'UNAVAILABLE' -Detail 'Auto-failover configuration, provider health and request history are not exposed by this diagnostic contract.'
    foreach ($provider in @(Get-PropertyValue -Object $desktopAudit -Name 'providers')) {
        $appType = Get-PropertyValue -Object $provider -Name 'appType'
        if ($appType -eq 'claude-desktop') {
            $desktopProvider = $provider
        }
        elseif ($appType -eq 'claude') {
            $claudeProvider = $provider
        }
    }
    foreach ($row in @(Get-PropertyValue -Object $desktopAudit -Name 'proxyConfig')) {
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

# Listener state; runtime address when available, otherwise an unverified default
$listenAddress = '127.0.0.1'
$listenPort = 15721
if ($null -ne $proxyRow) {
    $runtimeAddress = Get-PropertyValue -Object $proxyRow -Name 'listen_address'
    $runtimePort = Get-PropertyValue -Object $proxyRow -Name 'listen_port'
    if (-not [string]::IsNullOrWhiteSpace([string]$runtimeAddress)) {
        $listenAddress = [string]$runtimeAddress
    }
    if ($null -ne $runtimePort) {
        $listenPort = [int]$runtimePort
    }
    $surfaces.ccSwitch.proxyConfig = $proxyRow
}

$surfaces.ccSwitch.listenerSource = $(if ($null -ne $proxyRow) { 'official_runtime' } else { 'unverified_default' })
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
    Add-Check -Area 'CC Switch listener' -Status 'PASS' -Detail ("port {0} is listening; observed/default address={1}." -f $listenPort, $listenAddress)
}
else {
    Add-Check -Area 'CC Switch listener' -Status 'WARN' -Detail ("port {0} is not listening; observed/default address={1}." -f $listenPort, $listenAddress)
}

# Cross-check file selectors against official current-provider queries.
if ($null -ne $ccSettings -and $null -ne $desktopProvider) {
    $selector = [string](Get-PropertyValue -Object $ccSettings -Name 'currentProviderClaudeDesktop')
    $queriedId = [string](Get-PropertyValue -Object $desktopProvider -Name 'id')
    if ($selector -eq $queriedId) {
        Add-Check -Area 'Claude Desktop provider selector consistency' -Status 'PASS' -Detail 'settings.json selector matches official get_current_provider.'
    }
    else {
        Add-Check -Area 'Claude Desktop provider selector consistency' -Status 'FAIL' -Detail 'settings.json selector does not match official get_current_provider.'
        Add-Recommendation 'Re-apply the intended Claude Desktop provider after explicit approval; do not hand-edit both stores blindly.'
    }
}
if ($null -ne $ccSettings -and $null -ne $claudeProvider) {
    $selector = [string](Get-PropertyValue -Object $ccSettings -Name 'currentProviderClaude')
    $queriedId = [string](Get-PropertyValue -Object $claudeProvider -Name 'id')
    if ($selector -eq $queriedId) {
        Add-Check -Area 'Claude provider selector consistency' -Status 'PASS' -Detail 'settings.json selector matches official get_current_provider.'
    }
    else {
        Add-Check -Area 'Claude provider selector consistency' -Status 'FAIL' -Detail 'settings.json selector does not match official get_current_provider.'
    }
}

# Compare active local Desktop profile with CC Switch's expected route only when local config is authoritative.
if ($desktopConfigSource -eq 'local configLibrary' -and $null -ne $desktopProvider -and -not [string]::IsNullOrWhiteSpace([string]$desktopProfileRawBaseUrl)) {
    $mode = [string](Get-PropertyValue -Object $desktopProvider -Name 'desktopMode')
    $expectedBaseUrl = $null
    if ($mode -eq 'direct') {
        $expectedBaseUrl = [string](Get-PropertyValue -Object $desktopProvider -Name 'baseUrl')
    }
    elseif ($mode -eq 'proxy' -and $null -ne $proxyRow) {
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
    schemaVersion = 2
    ccSwitchSource = 'official-desktop-cdp'
    databaseRead = $false
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
Write-Output 'No business configuration was changed. Official queries use the local desktop channel; the database was not opened.'

exit 0
