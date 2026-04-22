param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$InputPaths,

    [string]$OutputPath,

    [switch]$OverwriteExisting,

    [string]$Preset,

    [string]$TemplatePath,

    [string]$PandocPath = "$env:LOCALAPPDATA\Pandoc\pandoc.exe"
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$formatterScriptPath = Join-Path $scriptRoot "word_template_formatter.py"
$defaultWordTemplatePath = Join-Path $env:APPDATA "Microsoft\Templates\Normal.dotm"
$defaultPresetName = "qiye-shenbao"

function Resolve-PresetName {
    param([Parameter(Mandatory = $true)][string]$PresetName)

    $canonicalPresetMap = @{
        "default" = "qiye-shenbao"
        "master-default" = "tongyong-moren"
        "technical-summary" = "jishu-zongjie"
        "work-summary" = "gongzuo-zongjie"
        "tongyong-moren" = "tongyong-moren"
        "jishu-zongjie" = "jishu-zongjie"
        "gongzuo-zongjie" = "gongzuo-zongjie"
        "qiye-shenbao" = "qiye-shenbao"
    }

    if (-not $canonicalPresetMap.ContainsKey($PresetName)) {
        throw "Unknown preset: $PresetName. Canonical presets: tongyong-moren, jishu-zongjie, gongzuo-zongjie, qiye-shenbao."
    }

    return $canonicalPresetMap[$PresetName]
}

function Resolve-ExistingPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Resolve-Path -LiteralPath $Path).Path
}

function Resolve-OutputPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

function Resolve-PythonPath {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python was not found."
    }
    return $pythonCommand.Source
}

function Invoke-PandocExport {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$OutputPath
    )

    & $PandocPath `
        $SourcePath `
        "--from=markdown" `
        "--to=docx" `
        "--standalone" `
        "--output=$OutputPath"

    if ($LASTEXITCODE -ne 0) {
        throw "Pandoc failed for $SourcePath"
    }
}

function Invoke-WordTemplateApply {
    param(
        [Parameter(Mandatory = $true)]$WordApp,
        [Parameter(Mandatory = $true)][string]$DocumentPath,
        [Parameter(Mandatory = $true)][string]$ResolvedTemplatePath
    )

    $doc = $WordApp.Documents.Open($DocumentPath, $false, $false)
    try {
        $doc.AttachedTemplate = $ResolvedTemplatePath
        $doc.CopyStylesFromTemplate($ResolvedTemplatePath)
        $doc.UpdateStylesOnOpen = $true
        $doc.UpdateStyles()
        $doc.Save()
    }
    finally {
        $doc.Close()
    }
}

function Invoke-DocxTemplateApply {
    param(
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$DocumentPath,
        [string]$ResolvedTemplatePath,
        [string]$PresetName
    )

    $applyArgs = @(
        $formatterScriptPath,
        "apply",
        "--input",
        $DocumentPath,
        "--output",
        $DocumentPath
    )

    if ($PresetName) {
        $applyArgs += @("--preset", $PresetName)
    }
    elseif ($ResolvedTemplatePath) {
        $applyArgs += @("--template", $ResolvedTemplatePath)
    }
    else {
        throw "A DOCX preset or template path is required."
    }

    & $PythonPath @applyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "DOCX template apply failed for $DocumentPath"
    }
}

if (-not (Test-Path -LiteralPath $PandocPath)) {
    $pandocCommand = Get-Command pandoc -ErrorAction SilentlyContinue
    if ($null -eq $pandocCommand) {
        throw "Pandoc was not found."
    }
    $PandocPath = $pandocCommand.Source
}

if (-not (Test-Path -LiteralPath $formatterScriptPath)) {
    throw "word_template_formatter.py was not found: $formatterScriptPath"
}

if ($PSBoundParameters.ContainsKey("Preset") -and $PSBoundParameters.ContainsKey("TemplatePath")) {
    throw "Use either -Preset or -TemplatePath, not both."
}

$templateMode = $null
$resolvedTemplatePath = $null
$pythonPath = $null

if ($PSBoundParameters.ContainsKey("Preset")) {
    $Preset = Resolve-PresetName -PresetName $Preset
    $templateMode = "docx-preset"
    $pythonPath = Resolve-PythonPath
}
elseif ($PSBoundParameters.ContainsKey("TemplatePath")) {
    $resolvedTemplatePath = Resolve-ExistingPath -Path $TemplatePath
    $templateExtension = [System.IO.Path]::GetExtension($resolvedTemplatePath).ToLowerInvariant()
    switch ($templateExtension) {
        ".docx" {
            $templateMode = "docx-template"
            $pythonPath = Resolve-PythonPath
        }
        ".dotm" { $templateMode = "word-template" }
        ".dotx" { $templateMode = "word-template" }
        ".dot" { $templateMode = "word-template" }
        default {
            throw "TemplatePath must be a .docx, .dotm, .dotx, or .dot file: $resolvedTemplatePath"
        }
    }
}
else {
    $Preset = Resolve-PresetName -PresetName $defaultPresetName
    $templateMode = "docx-preset"
    $pythonPath = Resolve-PythonPath
}

$resolvedInputs = @()
foreach ($inputPath in $InputPaths) {
    $resolvedInput = Resolve-ExistingPath -Path $inputPath
    if ([System.IO.Path]::GetExtension($resolvedInput).ToLowerInvariant() -ne ".md") {
        throw "Only Markdown files are supported: $resolvedInput"
    }
    $resolvedInputs += $resolvedInput
}

if ($resolvedInputs.Count -gt 1 -and $OutputPath) {
    throw "OutputPath can only be used with a single Markdown input."
}

$word = $null

try {
    if ($templateMode -eq "word-template") {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0
    }

    foreach ($sourcePath in $resolvedInputs) {
        if ($OutputPath) {
            $outputPath = Resolve-OutputPath -Path $OutputPath
        }
        elseif ($OverwriteExisting) {
            $outputPath = [System.IO.Path]::ChangeExtension($sourcePath, ".docx")
        }
        else {
            $directory = [System.IO.Path]::GetDirectoryName($sourcePath)
            $stem = [System.IO.Path]::GetFileNameWithoutExtension($sourcePath)
            $outputPath = Join-Path $directory ($stem + ".formatted.docx")
        }

        Invoke-PandocExport -SourcePath $sourcePath -OutputPath $outputPath

        if ($templateMode -eq "word-template") {
            Invoke-WordTemplateApply `
                -WordApp $word `
                -DocumentPath $outputPath `
                -ResolvedTemplatePath $resolvedTemplatePath
        }
        else {
            Invoke-DocxTemplateApply `
                -PythonPath $pythonPath `
                -DocumentPath $outputPath `
                -ResolvedTemplatePath $resolvedTemplatePath `
                -PresetName $Preset
        }

        [PSCustomObject]@{
            SourcePath          = $sourcePath
            OutputPath          = $outputPath
            AppliedMode         = $templateMode
            AppliedPreset       = $Preset
            AppliedTemplatePath = $resolvedTemplatePath
        }
    }
}
finally {
    if ($null -ne $word) {
        $word.Quit()
    }
}
