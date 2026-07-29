[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

function Invoke-GitRaw {
    param([Parameter(Mandatory=$true)][string[]]$Arguments,[switch]$AllowFailure)
    $oldPreference=$ErrorActionPreference
    $ErrorActionPreference='Continue'
    try {
        $output = @(& git --no-optional-locks @Arguments 2>&1 | ForEach-Object { [string]$_ })
        $code = $LASTEXITCODE
    }
    finally{$ErrorActionPreference=$oldPreference}
    if ($code -ne 0 -and -not $AllowFailure) { throw "git failed ($code): git $($Arguments -join ' ')`n$($output -join "`n")" }
    return [pscustomobject]@{ ExitCode=$code; Output=$output }
}

$settings = Read-POConfig -Path $Config -RequireSources
$output = Resolve-POFullPath -Path $OutputDir -AllowMissing
$external = Resolve-POFullPath -Path $settings.external_git_root -AllowMissing
foreach ($syncRoot in @($settings.sync_roots)) {
    if (Test-POPathWithin -Path $external -Parent ([string]$syncRoot) -AllowEqual) {
        throw "external_git_root must be outside sync_roots: $external"
    }
}
[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $output))
$bundleRoot = Join-Path $output 'git-bundles'
$recoveryRoot = Join-Path $output 'git-recovery'
[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $bundleRoot))
[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $recoveryRoot))
[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $external))

$archives = New-Object Collections.Generic.List[object]
$errors = New-Object Collections.Generic.List[object]
$repositories = New-Object Collections.Generic.List[object]
foreach ($source in @($settings.sources)) {
    $repositories.Add([pscustomobject]@{ id=[string]$source.id; repository=[string]$source.path; kind='worktree' })
    $property = $source.PSObject.Properties['git_paths']
    if ($null -ne $property) {
        $index = 0
        foreach ($gitPath in @($property.Value)) {
            $index++
            $repositories.Add([pscustomobject]@{ id=([string]$source.id + '-extra-' + $index); repository=[string]$gitPath; kind='configured_extra' })
        }
    }
}

foreach ($repositoryRecord in @($repositories.ToArray() | Sort-Object { $_.id.ToLowerInvariant() })) {
    $id = [string]$repositoryRecord.id
    $repository = Resolve-POFullPath -Path ([string]$repositoryRecord.repository)
    $state = $null
    try { $state = Get-POGitState -Repository $repository }
    catch { $errors.Add([pscustomobject][ordered]@{ source_id=$id; stage='git_state'; path=$repository; reason=$_.Exception.Message }); continue }
    if ($null -eq $state) { continue }

    $temporaryRoot = Join-Path $external ('temporary\project-organizer-' + $id + '-' + [Guid]::NewGuid().ToString('N'))
    $bare = Join-Path $temporaryRoot 'archive.git'
    $restore = Join-Path $temporaryRoot 'restore.git'
    $bundle = Join-Path $bundleRoot ($id + '.bundle')
    $sourceRecovery = Join-Path $recoveryRoot $id
    [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $sourceRecovery))
    try {
        if (Test-Path -LiteralPath $bundle) { throw "Bundle already exists: $bundle" }
        [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $temporaryRoot))
        [void](Invoke-GitRaw -Arguments @('clone','--quiet','--mirror','--no-hardlinks',$repository,$bare))
        $reflogIndex = 0
        foreach ($commit in @($state.reflog_commits | Sort-Object -Unique)) {
            $reflogIndex++
            $probe = Invoke-POGit -Repository $bare -Arguments @('cat-file','-e',($commit + '^{commit}')) -AllowFailure
            if ($probe.ExitCode -ne 0) {
                [void](Invoke-GitRaw -Arguments @('-C',$bare,'fetch','--quiet','--no-tags',$repository,$commit))
            }
            [void](Invoke-POGit -Repository $bare -Arguments @('update-ref',('refs/archive/reflog/{0:D6}' -f $reflogIndex),$commit))
        }
        if ($state.head) { [void](Invoke-POGit -Repository $bare -Arguments @('update-ref','refs/archive/original-head',$state.head)) }

        $sourceFsck = Invoke-POGit -Repository $repository -Arguments @('fsck','--full','--no-reflogs') -AllowFailure
        Write-POText -Path (Join-Path $sourceRecovery 'source-fsck.txt') -Text (($sourceFsck.Output -join "`n") + "`n")
        Write-POText -Path (Join-Path $sourceRecovery 'working-tree.diff') -Text (((Invoke-POGit -Repository $repository -Arguments @('diff','--binary','--no-ext-diff') -AllowFailure).Output -join "`n") + "`n")
        Write-POText -Path (Join-Path $sourceRecovery 'index.diff') -Text (((Invoke-POGit -Repository $repository -Arguments @('diff','--cached','--binary','--no-ext-diff') -AllowFailure).Output -join "`n") + "`n")
        Write-POText -Path (Join-Path $sourceRecovery 'untracked.txt') -Text (((Invoke-POGit -Repository $repository -Arguments @('ls-files','--others','--exclude-standard') -AllowFailure).Output -join "`n") + "`n")
        Write-POText -Path (Join-Path $sourceRecovery 'ignored.txt') -Text (((Invoke-POGit -Repository $repository -Arguments @('ls-files','--others','--ignored','--exclude-standard') -AllowFailure).Output -join "`n") + "`n")
        Write-POJson -Path (Join-Path $sourceRecovery 'git-state.json') -Value $state

        $temporaryBundle = Join-Path $temporaryRoot ($id + '.bundle')
        [void](Invoke-POGit -Repository $bare -Arguments @('bundle','create',$temporaryBundle,'--all'))
        $verify = Invoke-POGit -Repository $bare -Arguments @('bundle','verify',$temporaryBundle)
        [IO.File]::Move((ConvertTo-POExtendedPath $temporaryBundle), (ConvertTo-POExtendedPath $bundle))
        $bundleHash = Get-POStableSha256 -Path $bundle

        [void](Invoke-GitRaw -Arguments @('clone','--quiet','--mirror',$bundle,$restore))
        $restoreFsck = Invoke-POGit -Repository $restore -Arguments @('fsck','--full')
        $referenceFailures = New-Object Collections.Generic.List[string]
        foreach ($line in @($state.refs)) {
            $parts = ([string]$line).Split("`t",2)
            if ($parts.Count -ne 2) { $referenceFailures.Add("Malformed source ref: $line"); continue }
            $actual = Invoke-POGit -Repository $restore -Arguments @('rev-parse',$parts[0]) -AllowFailure
            if ($actual.ExitCode -ne 0 -or ($actual.Output -join '').Trim() -ne $parts[1]) { $referenceFailures.Add("Reference mismatch: $($parts[0])") }
            $object = Invoke-POGit -Repository $restore -Arguments @('cat-file','-e',$parts[1]) -AllowFailure
            if ($object.ExitCode -ne 0) { $referenceFailures.Add("Unreadable ref object: $($parts[1])") }
        }
        foreach ($commit in @($state.reflog_commits)) {
            $object = Invoke-POGit -Repository $restore -Arguments @('cat-file','-e',($commit + '^{commit}')) -AllowFailure
            if ($object.ExitCode -ne 0) { $referenceFailures.Add("Unreadable reflog commit: $commit") }
        }
        if ($referenceFailures.Count -gt 0) { throw ($referenceFailures.ToArray() -join '; ') }

        Write-POText -Path (Join-Path $sourceRecovery 'bundle-verify.txt') -Text (($verify.Output -join "`n") + "`n")
        Write-POText -Path (Join-Path $sourceRecovery 'restore-fsck.txt') -Text (($restoreFsck.Output -join "`n") + "`n")
        $supportManifest = Join-Path $sourceRecovery 'recovery-files.sha256'
        [void](New-POHashManifest -Paths @(
            (Join-Path $sourceRecovery 'source-fsck.txt'),(Join-Path $sourceRecovery 'working-tree.diff'),
            (Join-Path $sourceRecovery 'index.diff'),(Join-Path $sourceRecovery 'untracked.txt'),
            (Join-Path $sourceRecovery 'ignored.txt'),(Join-Path $sourceRecovery 'git-state.json'),
            (Join-Path $sourceRecovery 'bundle-verify.txt'),(Join-Path $sourceRecovery 'restore-fsck.txt')
        ) -OutputPath $supportManifest)
        $archives.Add([pscustomobject][ordered]@{
            source_id=$id; kind=$repositoryRecord.kind; repository=$repository; git_dir=$state.git_dir
            bundle_path=$bundle; bundle_sha256=$bundleHash; bundle_verified=$true; source_fsck_exit_code=$sourceFsck.ExitCode
            restore_fsck_verified=$true; references_verified=$true; head=$state.head; branch=$state.branch
            refs=@($state.refs); reflog_commits=@($state.reflog_commits); recovery_manifest=$supportManifest
            recovery_manifest_sha256=(Get-POStableSha256 -Path $supportManifest)
        })
    }
    catch { $errors.Add([pscustomobject][ordered]@{ source_id=$id; stage='bundle'; path=$repository; reason=$_.Exception.Message }) }
    finally {
        if ((Test-POPathWithin -Path $temporaryRoot -Parent $external) -and (Test-Path -LiteralPath $temporaryRoot)) {
            Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
        }
    }
}

$archiveRows = @($archives.ToArray() | Sort-Object { $_.source_id.ToLowerInvariant() })
$errorRows = @($errors.ToArray() | Sort-Object { $_.source_id.ToLowerInvariant() }, { $_.stage })
Write-POJson -Path (Join-Path $output 'git_archives.json') -Value $archiveRows
Write-POCsv -Path (Join-Path $output 'git-errors.csv') -Rows $errorRows -Columns @('source_id','stage','path','reason')
$review = @(
    '# Git 恢复包审查','',
    "- 已验证恢复包：$($archiveRows.Count)",
    "- 错误：$($errorRows.Count)",'',
    '每个恢复包均需同时通过 bundle verify、隔离恢复、fsck 和引用读取检查。',''
)
foreach ($archive in $archiveRows) { $review += "- $($archive.source_id)：$($archive.bundle_path)，SHA256 $($archive.bundle_sha256)" }
Write-POText -Path (Join-Path $output 'git-review.md') -Text (($review -join "`n") + "`n")

if ($errorRows.Count -gt 0) { throw "Git recovery failed for $($errorRows.Count) repository or store(s)." }
Write-Output "Git recovery bundles: $($archiveRows.Count)"
