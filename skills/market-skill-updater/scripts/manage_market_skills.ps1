param(
    [ValidateSet("check", "update", "repair")]
    [string]$Mode = "check",

    [ValidateSet("workspace", "global")]
    [string]$Scope = "workspace",

    [switch]$Json
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-PreferredNpmCacheDirectory {
    if (-not [string]::IsNullOrWhiteSpace($env:npm_config_cache)) {
        return $env:npm_config_cache
    }

    if (-not [string]::IsNullOrWhiteSpace($env:NPM_CONFIG_CACHE)) {
        return $env:NPM_CONFIG_CACHE
    }

    try {
        $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..\..")).Path
    } catch {
        $repoRoot = (Join-Path $HOME ".agents")
    }

    return (Join-Path $repoRoot ".tmp\npm-cache")
}

function Remove-Ansi {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    $escape = [char]27
    return ($Text -replace "$escape\[[0-?]*[ -/]*[@-~]", "").Trim()
}

function Invoke-SkillsCommand {
    param([string]$CommandLine)

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/d /s /c `"$CommandLine`""
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    $cacheDir = Get-PreferredNpmCacheDirectory
    $hadOriginalCache = $false
    $originalCache = $null

    try {
        if (-not [string]::IsNullOrWhiteSpace($cacheDir)) {
            New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
            $hadOriginalCache = Test-Path Env:\npm_config_cache
            if ($hadOriginalCache) {
                $originalCache = $env:npm_config_cache
            }
            $env:npm_config_cache = $cacheDir
        }

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $null = $process.Start()

        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
    } finally {
        if (-not [string]::IsNullOrWhiteSpace($cacheDir)) {
            if ($hadOriginalCache) {
                $env:npm_config_cache = $originalCache
            } else {
                Remove-Item Env:\npm_config_cache -ErrorAction SilentlyContinue
            }
        }
    }

    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        $parts += $stdout
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        $parts += $stderr
    }

    [pscustomobject]@{
        command   = $CommandLine
        exit_code = $process.ExitCode
        stdout    = (Remove-Ansi -Text $stdout)
        stderr    = (Remove-Ansi -Text $stderr)
        output    = (Remove-Ansi -Text ($parts -join [Environment]::NewLine))
        cache_dir = $cacheDir
    }
}

function Convert-InstalledSkills {
    param([string]$JsonText)

    if ([string]::IsNullOrWhiteSpace($JsonText)) {
        return @()
    }

    $parsed = $JsonText | ConvertFrom-Json

    if ($null -eq $parsed) {
        return @()
    }

    if ($parsed -is [System.Array]) {
        return @($parsed)
    }

    if ($parsed.PSObject.Properties.Name -contains "skills") {
        return @($parsed.skills)
    }

    return @($parsed)
}

function Get-SkillLabels {
    param([object[]]$Skills)

    $labels = @()
    foreach ($skill in $Skills) {
        $matched = $false

        if ($skill -is [string]) {
            $labels += $skill
            continue
        }

        foreach ($propertyName in @("name", "skill", "id", "package", "repo")) {
            if (($skill.PSObject.Properties.Name -contains $propertyName) -and $skill.$propertyName) {
                $labels += [string]$skill.$propertyName
                $matched = $true
                break
            }
        }

        if ($matched) {
            continue
        }

        $labels += ($skill | ConvertTo-Json -Compress -Depth 8)
    }

    return @($labels)
}

function Get-SkillPaths {
    param([object[]]$Skills)

    $paths = @()
    foreach ($skill in $Skills) {
        if (
            ($skill -isnot [string]) -and
            ($skill.PSObject.Properties.Name -contains "path") -and
            $skill.path
        ) {
            $paths += [string]$skill.path
        }
    }

    return @($paths | Select-Object -Unique)
}

function Get-DefaultGlobalSkillRoots {
    return @(
        (Join-Path $HOME ".agents\skills"),
        (Join-Path $HOME ".codex\skills")
    ) | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    } | Select-Object -Unique
}

function Get-GlobalSkillRoots {
    param([string[]]$ListedGlobalPaths)

    $roots = New-Object System.Collections.Generic.List[string]

    foreach ($path in $ListedGlobalPaths) {
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            $roots.Add((Split-Path -Parent $path))
        }
    }

    foreach ($defaultRoot in (Get-DefaultGlobalSkillRoots)) {
        $roots.Add($defaultRoot)
    }

    return @($roots | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    } | Select-Object -Unique)
}

function Get-PrimaryGlobalSkillRoot {
    param([string[]]$GlobalRoots)

    if ($GlobalRoots.Count -gt 0) {
        return $GlobalRoots[0]
    }

    return ((Get-DefaultGlobalSkillRoots) | Select-Object -First 1)
}

function Get-PhysicalGlobalSkillDirs {
    param([string[]]$Roots)

    $dirs = @()
    foreach ($root in $Roots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }

        foreach ($dir in @(Get-ChildItem -LiteralPath $root -Directory -Force | Where-Object {
            $_.Name -ne ".system"
        })) {
            $dirs += $dir
        }
    }

    return $dirs
}

function Get-DirectoryEntries {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }

    return @(Get-ChildItem -LiteralPath $Path -Force)
}

function Get-GlobalSkillInventory {
    param(
        [string[]]$ListedGlobalPaths,
        [string[]]$GlobalRoots
    )

    $dirs = @(Get-PhysicalGlobalSkillDirs -Roots $GlobalRoots)

    return @($dirs | ForEach-Object {
        $entries = @(Get-DirectoryEntries -Path $_.FullName)

        [pscustomobject]@{
            name       = $_.Name
            path       = $_.FullName
            root       = (Split-Path -Parent $_.FullName)
            is_listed  = ($_.FullName -in $ListedGlobalPaths)
            entry_count = $entries.Count
            is_empty   = ($entries.Count -eq 0)
        }
    })
}

function Get-UpdateCandidatesFromCheckOutput {
    param([string]$CheckOutput)

    if ([string]::IsNullOrWhiteSpace($CheckOutput)) {
        return @()
    }

    $candidates = New-Object System.Collections.Generic.List[string]
    $upArrow = [char]0x2191

    foreach ($line in ($CheckOutput -split "\r?\n")) {
        if ($line -match "^\s*${upArrow}\s+(.+?)\s*$") {
            $candidates.Add($Matches[1])
        }
    }

    return @($candidates)
}

function Emit-Result {
    param(
        [System.Collections.IDictionary]$Result,
        [switch]$AsJson
    )

    if ($AsJson) {
        Write-Output ([pscustomobject]$Result | ConvertTo-Json -Depth 20)
        return
    }

    if (
        ($Result["scope"] -eq "global") -and
        $Result.Contains("listed_global_count")
    ) {
        $lines = @(
            ("Scope: {0}" -f $Result["scope"]),
            ("Mode: {0}" -f $Result["mode"]),
            ("Status: {0}" -f $Result["status"]),
            ("Listed global skills: {0}" -f $Result["listed_global_count"]),
            ("Detected global directories: {0}" -f $Result["detected_global_count"]),
            ("Update candidates: {0}" -f $Result["update_candidate_count"]),
            ("Repairable empty residuals: {0}" -f $Result["repairable_empty_residual_count"])
        )

        if ($Result.Contains("global_skill_roots") -and $Result["global_skill_roots"]) {
            $lines += ("Global skill roots: {0}" -f ($Result["global_skill_roots"] -join ", "))
        } elseif ($Result.Contains("global_skill_root") -and $Result["global_skill_root"]) {
            $lines += ("Global skill root: {0}" -f $Result["global_skill_root"])
        }

        if ($Result["listed_global_count"] -gt 0) {
            $lines += ("Listed global list: {0}" -f ($Result["listed_global"] -join ", "))
        }

        if ($Result["detected_global_count"] -gt 0) {
            $lines += ("Detected global list: {0}" -f ($Result["detected_global"] -join ", "))
        }

        if ($Result["unlisted_global_count"] -gt 0) {
            $lines += ("Unlisted global directories: {0}" -f ($Result["unlisted_global"] -join ", "))
        }

        if ($Result["update_candidate_count"] -gt 0) {
            $lines += ("Update candidate list: {0}" -f ($Result["update_candidates"] -join ", "))
        }

        if ($Result["repairable_empty_residual_count"] -gt 0) {
            $lines += ("Repairable empty residual list: {0}" -f ($Result["repairable_empty_residual"] -join ", "))
        }

        if ($Result.Contains("nonempty_unlisted_global_count") -and ($Result["nonempty_unlisted_global_count"] -gt 0)) {
            $lines += ("Non-empty unlisted global directories: {0}" -f ($Result["nonempty_unlisted_global"] -join ", "))
        }

        if ($Result.Contains("repaired_count")) {
            $lines += ("Repaired residuals: {0}" -f $Result["repaired_count"])
        }

        if ($Result.Contains("repaired") -and ($Result["repaired_count"] -gt 0)) {
            $lines += ("Repaired list: {0}" -f ($Result["repaired"] -join ", "))
        }

        if ($Result.Contains("repair_failed_count") -and ($Result["repair_failed_count"] -gt 0)) {
            $lines += ("Repair failed list: {0}" -f ($Result["repair_failed"] -join ", "))
        }
    } else {
        $lines = @(
            ("Scope: {0}" -f $Result["scope"]),
            ("Mode: {0}" -f $Result["mode"]),
            ("Status: {0}" -f $Result["status"]),
            ("Installed skills: {0}" -f $Result["installed_count"])
        )

        if ($Result["installed_count"] -gt 0) {
            $lines += ("Installed list: {0}" -f ($Result["installed"] -join ", "))
        }
    }

    if ($Result.Contains("note") -and $Result["note"]) {
        $lines += ("Note: {0}" -f $Result["note"])
    }

    if ($Result.Contains("check_output") -and $Result["check_output"]) {
        $lines += ""
        $lines += "Check output:"
        $lines += $Result["check_output"]
    }

    if ($Result.Contains("update_output") -and $Result["update_output"]) {
        $lines += ""
        $lines += "Update output:"
        $lines += $Result["update_output"]
    }

    if ($Result.Contains("error") -and $Result["error"]) {
        $lines += ("Error: {0}" -f $Result["error"])
    }

    Write-Output ($lines -join [Environment]::NewLine)
}

$result = [ordered]@{
    skill_manager = "npx skills"
    mode          = $Mode
    scope         = $Scope
    timestamp     = (Get-Date).ToString("s")
    cache_dir     = (Get-PreferredNpmCacheDirectory)
}

if ($Scope -eq "global" -and $Mode -eq "update") {
    $result.status = "blocked"
    $result.installed_count = 0
    $result.installed = @()
    $result.error = "Global update is intentionally blocked because the current skills CLI help does not document stable global update semantics."
    Emit-Result -Result $result -AsJson:$Json
    exit 1
}

if ($Scope -eq "workspace" -and $Mode -eq "repair") {
    $result.status = "blocked"
    $result.installed_count = 0
    $result.installed = @()
    $result.error = "Residual directory repair is only supported for global scope."
    Emit-Result -Result $result -AsJson:$Json
    exit 1
}

if ($Scope -eq "global" -and ($Mode -eq "check" -or $Mode -eq "repair")) {
    $listCommand = "npx skills ls -g --json"
    $listRun = Invoke-SkillsCommand -CommandLine $listCommand

    if ($listRun.exit_code -ne 0) {
        $globalError = [ordered]@{
            skill_manager   = "npx skills"
            mode            = "check"
            scope           = "global"
            timestamp       = (Get-Date).ToString("s")
            list_command    = $listCommand
            list_exit_code  = $listRun.exit_code
            status          = "list_failed"
            installed_count = 0
            installed       = @()
            error           = $listRun.output
        }

        Emit-Result -Result $globalError -AsJson:$Json
        exit 1
    }

    $globalItems = @(Convert-InstalledSkills -JsonText $listRun.stdout)
    $listedGlobal = @(Get-SkillLabels -Skills $globalItems)
    $listedGlobalPaths = @(Get-SkillPaths -Skills $globalItems)
    $globalSkillRoots = @(Get-GlobalSkillRoots -ListedGlobalPaths $listedGlobalPaths)
    $inventory = @(Get-GlobalSkillInventory -ListedGlobalPaths $listedGlobalPaths -GlobalRoots $globalSkillRoots)
    $detectedGlobal = @($inventory | ForEach-Object { $_.name })
    $detectedGlobalPaths = @($inventory | ForEach-Object { $_.path })
    $unlistedGlobal = @($inventory | Where-Object { -not $_.is_listed } | ForEach-Object { $_.name })
    $unlistedGlobalPaths = @($inventory | Where-Object { -not $_.is_listed } | ForEach-Object { $_.path })
    $repairableEmptyResidual = @($inventory | Where-Object { (-not $_.is_listed) -and $_.is_empty })
    $repairableEmptyResidualNames = @($repairableEmptyResidual | ForEach-Object { $_.name })
    $repairableEmptyResidualPaths = @($repairableEmptyResidual | ForEach-Object { $_.path })
    $nonemptyUnlistedGlobal = @($inventory | Where-Object { (-not $_.is_listed) -and (-not $_.is_empty) } | ForEach-Object { $_.name })
    $nonemptyUnlistedGlobalPaths = @($inventory | Where-Object { (-not $_.is_listed) -and (-not $_.is_empty) } | ForEach-Object { $_.path })

    $checkRun = Invoke-SkillsCommand -CommandLine "npx skills check"
    $updateCandidates = @()
    if ($checkRun.exit_code -eq 0) {
        $updateCandidates = @(Get-UpdateCandidatesFromCheckOutput -CheckOutput $checkRun.output)
    }

    $globalResult = [ordered]@{
        skill_manager          = "npx skills"
        mode                   = $Mode
        scope                  = "global"
        timestamp              = (Get-Date).ToString("s")
        cache_dir              = $listRun.cache_dir
        global_skill_root      = (Get-PrimaryGlobalSkillRoot -GlobalRoots $globalSkillRoots)
        global_skill_roots     = $globalSkillRoots
        list_command           = $listCommand
        list_exit_code         = $listRun.exit_code
        listed_global_count    = $listedGlobal.Count
        listed_global          = $listedGlobal
        listed_global_paths    = $listedGlobalPaths
        detected_global_count  = $detectedGlobal.Count
        detected_global        = $detectedGlobal
        detected_global_paths  = $detectedGlobalPaths
        unlisted_global_count  = $unlistedGlobal.Count
        unlisted_global        = $unlistedGlobal
        unlisted_global_paths  = $unlistedGlobalPaths
        repairable_empty_residual_count = $repairableEmptyResidualNames.Count
        repairable_empty_residual       = $repairableEmptyResidualNames
        repairable_empty_residual_paths = $repairableEmptyResidualPaths
        nonempty_unlisted_global_count  = $nonemptyUnlistedGlobal.Count
        nonempty_unlisted_global        = $nonemptyUnlistedGlobal
        nonempty_unlisted_global_paths  = $nonemptyUnlistedGlobalPaths
        check_command          = $checkRun.command
        check_exit_code        = $checkRun.exit_code
        update_candidate_count = $updateCandidates.Count
        update_candidates      = $updateCandidates
        status                 = if ($Mode -eq "repair") {
            "repair_pending"
        } elseif ($checkRun.exit_code -ne 0) {
            "global_check_failed"
        } elseif (($listedGlobal.Count -eq 0) -and ($detectedGlobal.Count -eq 0)) {
            "no_installed_skills"
        } elseif ($unlistedGlobal.Count -gt 0) {
            "global_inventory_mismatch"
        } else {
            "global_check_completed"
        }
        note                   = if ($Mode -eq "repair") {
            "Global inventory completed. Repair mode will only target empty residual global directories that are not listed by npx skills ls -g."
        } elseif ($checkRun.exit_code -ne 0) {
            "Global inventory completed, but the read-only update check failed."
        } elseif (($listedGlobal.Count -eq 0) -and ($detectedGlobal.Count -eq 0)) {
            "No global skills were found under the detected global skill roots."
        } elseif ($unlistedGlobal.Count -gt 0) {
            "npx skills ls -g and the physical global skill directory do not fully agree. The script exposes both views in read-only mode and still stops before any global update."
        } else {
            "Global inventory and read-only update check completed. The script still stops before any global update."
        }
    }

    if ($checkRun.exit_code -eq 0) {
        $globalResult.check_output = $checkRun.output
    } else {
        $globalResult.error = $checkRun.output
    }

    if ($Mode -eq "repair") {
        if ($repairableEmptyResidual.Count -eq 0) {
            $globalResult.status = "no_repair_needed"
            $globalResult.repaired_count = 0
            $globalResult.repaired = @()
            $globalResult.repair_failed_count = 0
            $globalResult.repair_failed = @()
            $globalResult.repair_actions = @()
            $globalResult.note = "No empty residual global directories required cleanup."
            Emit-Result -Result $globalResult -AsJson:$Json
            exit 0
        }

        $repairActions = @()
        foreach ($residual in $repairableEmptyResidual) {
            $removeRun = Invoke-SkillsCommand -CommandLine ("npx skills remove -g {0} -y" -f $residual.name)
            $existsAfterRemove = Test-Path -LiteralPath $residual.path
            $entriesAfterRemove = if ($existsAfterRemove) {
                @(Get-DirectoryEntries -Path $residual.path).Count
            } else {
                0
            }

            $deletedDirectly = $false
            if ($existsAfterRemove -and ($entriesAfterRemove -eq 0)) {
                Remove-Item -LiteralPath $residual.path -Force -Recurse
                $deletedDirectly = $true
            }

            $existsAfterRepair = Test-Path -LiteralPath $residual.path

            $repairActions += [pscustomobject]@{
                name                = $residual.name
                path                = $residual.path
                remove_command      = $removeRun.command
                remove_exit_code    = $removeRun.exit_code
                remove_output       = $removeRun.output
                deleted_directly    = $deletedDirectly
                exists_after_repair = $existsAfterRepair
            }
        }

        $globalResult.repair_actions = $repairActions
        $globalResult.repaired = @($repairActions | Where-Object { -not $_.exists_after_repair } | ForEach-Object { $_.name })
        $globalResult.repaired_count = $globalResult.repaired.Count
        $globalResult.repair_failed = @($repairActions | Where-Object { $_.exists_after_repair } | ForEach-Object { $_.name })
        $globalResult.repair_failed_count = $globalResult.repair_failed.Count

        $postListRun = Invoke-SkillsCommand -CommandLine $listCommand
        $globalResult.post_list_command = $postListRun.command
        $globalResult.post_list_exit_code = $postListRun.exit_code
        if ($postListRun.exit_code -eq 0) {
            $postItems = @(Convert-InstalledSkills -JsonText $postListRun.stdout)
            $globalResult.post_listed_global = @(Get-SkillLabels -Skills $postItems)
            $globalResult.post_listed_global_count = $globalResult.post_listed_global.Count
            $globalResult.post_listed_global_paths = @(Get-SkillPaths -Skills $postItems)
        } else {
            $globalResult.post_list_error = $postListRun.output
        }

        $postGlobalRoots = @(Get-GlobalSkillRoots -ListedGlobalPaths @($globalResult.post_listed_global_paths))
        $postInventory = @(Get-GlobalSkillInventory -ListedGlobalPaths @($globalResult.post_listed_global_paths) -GlobalRoots $postGlobalRoots)
        $globalResult.post_global_skill_roots = $postGlobalRoots
        $globalResult.post_detected_global = @($postInventory | ForEach-Object { $_.name })
        $globalResult.post_detected_global_count = $globalResult.post_detected_global.Count
        $globalResult.post_detected_global_paths = @($postInventory | ForEach-Object { $_.path })

        $postCheckRun = Invoke-SkillsCommand -CommandLine "npx skills check"
        $globalResult.post_check_command = $postCheckRun.command
        $globalResult.post_check_exit_code = $postCheckRun.exit_code
        $globalResult.post_check_output = $postCheckRun.output

        if ($globalResult.repair_failed_count -gt 0) {
            $globalResult.status = "repair_partial"
            $globalResult.note = "Residual cleanup completed with failures. Review repair_failed and repair_actions."
            Emit-Result -Result $globalResult -AsJson:$Json
            exit 1
        }

        $globalResult.status = "repair_completed"
        $globalResult.note = "Empty residual global directories were cleaned. Review post_* fields for the normalized inventory."
        Emit-Result -Result $globalResult -AsJson:$Json
        exit 0
    }

    Emit-Result -Result $globalResult -AsJson:$Json

    if ($checkRun.exit_code -ne 0) {
        exit 1
    }

    exit 0
}

$listCommand = "npx skills ls --json"
$listRun = Invoke-SkillsCommand -CommandLine $listCommand
$result.list_command = $listRun.command
$result.list_exit_code = $listRun.exit_code

if ($listRun.exit_code -ne 0) {
    $result.status = "list_failed"
    $result.installed_count = 0
    $result.installed = @()
    $result.error = $listRun.output
    Emit-Result -Result $result -AsJson:$Json
    exit 1
}

try {
    $installedSkills = Convert-InstalledSkills -JsonText $listRun.stdout
} catch {
    $result.status = "list_parse_failed"
    $result.installed_count = 0
    $result.installed = @()
    $result.error = $_.Exception.Message
    $result.raw_list_stdout = $listRun.stdout
    Emit-Result -Result $result -AsJson:$Json
    exit 1
}

$result.raw_installed = $installedSkills
$result.installed = @(Get-SkillLabels -Skills $installedSkills)
$result.installed_count = $result.installed.Count

if ($result.installed_count -eq 0) {
    $result.status = "no_installed_skills"
    $result.note = "No CLI-managed market skills were found in workspace scope, so update checks were skipped."
    Emit-Result -Result $result -AsJson:$Json
    exit 0
}

$checkRun = Invoke-SkillsCommand -CommandLine "npx skills check"
$result.check_command = $checkRun.command
$result.check_exit_code = $checkRun.exit_code
$result.check_output = $checkRun.output

if ($checkRun.exit_code -ne 0) {
    $result.status = "check_failed"
    $result.error = $checkRun.output
    Emit-Result -Result $result -AsJson:$Json
    exit 1
}

if ($Mode -eq "check") {
    $result.status = "check_completed"
    Emit-Result -Result $result -AsJson:$Json
    exit 0
}

$updateRun = Invoke-SkillsCommand -CommandLine "npx skills update"
$result.update_command = $updateRun.command
$result.update_exit_code = $updateRun.exit_code
$result.update_output = $updateRun.output

if ($updateRun.exit_code -ne 0) {
    $result.status = "update_failed"
    $result.error = $updateRun.output
    Emit-Result -Result $result -AsJson:$Json
    exit 1
}

$postListRun = Invoke-SkillsCommand -CommandLine "npx skills ls --json"
$result.post_list_command = $postListRun.command
$result.post_list_exit_code = $postListRun.exit_code

if ($postListRun.exit_code -eq 0) {
    try {
        $postInstalled = Convert-InstalledSkills -JsonText $postListRun.stdout
        $result.post_installed = @(Get-SkillLabels -Skills $postInstalled)
        $result.post_installed_count = $result.post_installed.Count
    } catch {
        $result.post_list_error = $_.Exception.Message
    }
} else {
    $result.post_list_error = $postListRun.output
}

$result.status = "update_completed"
Emit-Result -Result $result -AsJson:$Json
