[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

$settings = Read-POConfig -Path $Config
$output = Resolve-POFullPath -Path $OutputDir -AllowMissing
[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $output))
$maxDepth = if ($null -ne $settings.max_discovery_depth) { [int]$settings.max_discovery_depth } else { 4 }
if ($maxDepth -lt 0 -or $maxDepth -gt 12) { throw 'max_discovery_depth must be between 0 and 12.' }

$candidateRows = New-Object Collections.Generic.List[object]
$errorRows = New-Object Collections.Generic.List[object]
$evidenceRows = New-Object Collections.Generic.List[object]
$markerNames = @('README.md','AGENTS.md','CLAUDE.md','GEMINI.md','package.json','pyproject.toml','Cargo.toml','pom.xml')

foreach ($searchRootValue in @($settings.search_roots)) {
    $searchRoot = Resolve-POFullPath -Path ([string]$searchRootValue) -AllowNetwork
    if ($searchRoot.Equals([IO.Path]::GetPathRoot($searchRoot), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Whole-volume discovery is prohibited: $searchRoot"
    }
    $pending = New-Object Collections.Generic.Queue[object]
    $pending.Enqueue([pscustomobject]@{ path=$searchRoot; depth=0 })
    while ($pending.Count -gt 0) {
        $item = $pending.Dequeue()
        $directory = [string]$item.path
        $depth = [int]$item.depth
        try {
            $attributes = [IO.File]::GetAttributes((ConvertTo-POExtendedPath $directory))
            $reparse = Get-POReparseInfo -Path $directory -Attributes $attributes
            if ($reparse.is_name_surrogate -and $depth -gt 0) {
                $errorRows.Add([pscustomobject][ordered]@{ search_root=$searchRoot; path=$directory; stage='reparse'; reason='name_surrogate_not_followed' })
                continue
            }
            $children = @([IO.Directory]::EnumerateFileSystemEntries((ConvertTo-POExtendedPath $directory)) |
                ForEach-Object { ConvertFrom-POExtendedPath $_ } |
                Sort-Object { $_.ToLowerInvariant() }, { $_ })
        }
        catch {
            $errorRows.Add([pscustomobject][ordered]@{ search_root=$searchRoot; path=$directory; stage='enumerate'; reason=$_.Exception.Message })
            continue
        }

        $childNames = @($children | ForEach-Object { [IO.Path]::GetFileName($_) })
        $markers = New-Object Collections.Generic.List[string]
        foreach ($marker in $markerNames) {
            if (@($childNames | Where-Object { $_.Equals($marker, [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0) { $markers.Add($marker) }
        }
        if (@($childNames | Where-Object { $_ -like '*.sln' -or $_ -like '*.code-workspace' }).Count -gt 0) { $markers.Add('workspace_file') }
        $hasGit = @($childNames | Where-Object { $_.Equals('.git', [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
        if ($hasGit) { $markers.Add('.git') }
        $hintHits = @($settings.candidate_hints | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_) -and
            $directory.IndexOf([string]$_, [StringComparison]::OrdinalIgnoreCase) -ge 0
        } | ForEach-Object { [string]$_ } | Sort-Object -Unique)
        $score = ([int]$hasGit * 5) + ($markers.Count * 2) + ($hintHits.Count * 3)
        if ($score -gt 0) {
            $name = [IO.Path]::GetFileName($directory.TrimEnd('\'))
            $candidateRows.Add([pscustomobject][ordered]@{
                path=$directory; name=$name; search_root=$searchRoot; depth=$depth
                has_readme=@($markers | Where-Object { $_ -eq 'README.md' }).Count -gt 0
                has_git=$hasGit; project_markers=($markers.ToArray() -join ';')
                hint_hits=($hintHits -join ';'); evidence_score=$score
                inventory_only=($directory -notmatch '^[A-Za-z]:\\')
            })
            $evidenceRows.Add([pscustomobject][ordered]@{
                path=$directory; markers=@($markers.ToArray()); hint_hits=$hintHits; evidence_score=$score
            })
        }

        if ($depth -ge $maxDepth) { continue }
        foreach ($child in $children) {
            try {
                $childAttributes = [IO.File]::GetAttributes((ConvertTo-POExtendedPath $child))
                if (($childAttributes -band [IO.FileAttributes]::Directory) -eq 0) { continue }
                $childReparse = Get-POReparseInfo -Path $child -Attributes $childAttributes
                if ($childReparse.is_name_surrogate) {
                    $errorRows.Add([pscustomobject][ordered]@{ search_root=$searchRoot; path=$child; stage='reparse'; reason='name_surrogate_not_followed' })
                    continue
                }
                $pending.Enqueue([pscustomobject]@{ path=$child; depth=($depth + 1) })
            }
            catch { $errorRows.Add([pscustomobject][ordered]@{ search_root=$searchRoot; path=$child; stage='metadata'; reason=$_.Exception.Message }) }
        }
    }
}

$candidates = @($candidateRows.ToArray() | Sort-Object { $_.path.ToLowerInvariant() }, { $_.path })
$errors = @($errorRows.ToArray() | Sort-Object { $_.path.ToLowerInvariant() }, { $_.stage }, { $_.reason })
Write-POCsv -Path (Join-Path $output 'candidates.csv') -Rows $candidates -Columns @(
    'path','name','search_root','depth','has_readme','has_git','project_markers','hint_hits','evidence_score','inventory_only'
)
Write-POCsv -Path (Join-Path $output 'errors.csv') -Rows $errors -Columns @('search_root','path','stage','reason')
Write-POJson -Path (Join-Path $output 'candidate_evidence.json') -Value ([ordered]@{
    schema_version='1.0'; search_roots=@($settings.search_roots); max_discovery_depth=$maxDepth
    candidates=@($evidenceRows.ToArray() | Sort-Object { $_.path.ToLowerInvariant() }, { $_.path })
    stopped=@($errors)
})
$lines = @(
    '# 项目候选审查','',
    "- 搜索根：$(@($settings.search_roots).Count)",
    "- 候选目录：$($candidates.Count)",
    "- 停止或读取问题：$($errors.Count)",'',
    '本阶段只提供证据，不自动选择来源。确认模式、来源、目标和 Git 策略后再生成文件盘点。',''
)
foreach ($row in $candidates) { $lines += "- `$($row.path)`：分数 $($row.evidence_score)，标记 $($row.project_markers)，关键词 $($row.hint_hits)" }
Write-POText -Path (Join-Path $output 'review.md') -Text (($lines -join "`n") + "`n")

Write-Output "Candidates: $($candidates.Count)"
Write-Output "Review: $(Join-Path $output 'review.md')"
