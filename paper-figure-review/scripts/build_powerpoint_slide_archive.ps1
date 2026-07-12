[CmdletBinding()]
param(
    [string]$OutputPath,
    [string]$VbaTemplatePath,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Release-ComObject {
    param([object]$InputObject)

    if ($null -ne $InputObject -and [Runtime.InteropServices.Marshal]::IsComObject($InputObject)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($InputObject)
    }
}

function Read-ZipTextEntry {
    param(
        [IO.Compression.ZipArchive]$Archive,
        [string]$EntryName
    )

    $entry = $Archive.GetEntry($EntryName)
    if ($null -eq $entry) {
        throw "PPAM 包缺少 $EntryName"
    }

    $stream = $entry.Open()
    $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true)
    try {
        return $reader.ReadToEnd()
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Write-ZipTextEntry {
    param(
        [IO.Compression.ZipArchive]$Archive,
        [string]$EntryName,
        [string]$Text
    )

    $existing = $Archive.GetEntry($EntryName)
    if ($null -ne $existing) {
        $existing.Delete()
    }

    $entry = $Archive.CreateEntry($EntryName, [IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
    try {
        $writer.Write($Text)
    }
    finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

function Save-XmlDocumentToString {
    param([Xml.XmlDocument]$Document)

    $stream = [IO.MemoryStream]::new()
    $settings = [Xml.XmlWriterSettings]::new()
    $settings.Encoding = [Text.UTF8Encoding]::new($false)
    $settings.Indent = $false
    $settings.OmitXmlDeclaration = $false
    $writer = [Xml.XmlWriter]::Create($stream, $settings)
    try {
        $Document.Save($writer)
        $writer.Flush()
        return [Text.Encoding]::UTF8.GetString($stream.ToArray())
    }
    finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

function Add-RibbonXmlToPackage {
    param(
        [string]$PackagePath,
        [string]$RibbonPath
    )

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $ribbonText = [IO.File]::ReadAllText($RibbonPath, [Text.Encoding]::UTF8)
    $ribbonDocument = [Xml.XmlDocument]::new()
    $ribbonDocument.PreserveWhitespace = $true
    $ribbonDocument.LoadXml($ribbonText)

    $archive = [IO.Compression.ZipFile]::Open($PackagePath, [IO.Compression.ZipArchiveMode]::Update)
    try {
        Write-ZipTextEntry -Archive $archive -EntryName 'customUI/customUI14.xml' -Text $ribbonText

        $relationshipNamespace = 'http://schemas.openxmlformats.org/package/2006/relationships'
        $relationshipType = 'http://schemas.microsoft.com/office/2007/relationships/ui/extensibility'
        $relationshipsDocument = [Xml.XmlDocument]::new()
        $relationshipsDocument.PreserveWhitespace = $true
        $relationshipsDocument.LoadXml((Read-ZipTextEntry -Archive $archive -EntryName '_rels/.rels'))

        $namespaceManager = [Xml.XmlNamespaceManager]::new($relationshipsDocument.NameTable)
        $namespaceManager.AddNamespace('r', $relationshipNamespace)
        $relationship = $relationshipsDocument.SelectSingleNode("/r:Relationships/r:Relationship[@Type='$relationshipType']", $namespaceManager)
        if ($null -eq $relationship) {
            $usedIds = @($relationshipsDocument.SelectNodes('/r:Relationships/r:Relationship', $namespaceManager) | ForEach-Object { $_.GetAttribute('Id') })
            $relationshipId = 'rIdPFRCustomUI'
            $suffix = 1
            while ($usedIds -contains $relationshipId) {
                $relationshipId = "rIdPFRCustomUI$suffix"
                $suffix++
            }

            $relationship = $relationshipsDocument.CreateElement('Relationship', $relationshipNamespace)
            $relationship.SetAttribute('Id', $relationshipId)
            $relationship.SetAttribute('Type', $relationshipType)
            $relationship.SetAttribute('Target', 'customUI/customUI14.xml')
            [void]$relationshipsDocument.DocumentElement.AppendChild($relationship)
        }
        else {
            $relationship.SetAttribute('Target', 'customUI/customUI14.xml')
        }
        Write-ZipTextEntry -Archive $archive -EntryName '_rels/.rels' -Text (Save-XmlDocumentToString $relationshipsDocument)

        $contentTypeNamespace = 'http://schemas.openxmlformats.org/package/2006/content-types'
        $contentTypesDocument = [Xml.XmlDocument]::new()
        $contentTypesDocument.PreserveWhitespace = $true
        $contentTypesDocument.LoadXml((Read-ZipTextEntry -Archive $archive -EntryName '[Content_Types].xml'))
        $contentTypeNamespaceManager = [Xml.XmlNamespaceManager]::new($contentTypesDocument.NameTable)
        $contentTypeNamespaceManager.AddNamespace('ct', $contentTypeNamespace)
        $xmlDefault = $contentTypesDocument.SelectSingleNode("/ct:Types/ct:Default[@Extension='xml']", $contentTypeNamespaceManager)
        if ($null -eq $xmlDefault) {
            $xmlDefault = $contentTypesDocument.CreateElement('Default', $contentTypeNamespace)
            $xmlDefault.SetAttribute('Extension', 'xml')
            $xmlDefault.SetAttribute('ContentType', 'application/xml')
            [void]$contentTypesDocument.DocumentElement.AppendChild($xmlDefault)
            Write-ZipTextEntry -Archive $archive -EntryName '[Content_Types].xml' -Text (Save-XmlDocumentToString $contentTypesDocument)
        }
    }
    finally {
        $archive.Dispose()
    }
}

function Assert-VbaProjectPresent {
    param([string]$PackagePath)

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($PackagePath)
    try {
        if ($null -eq $archive.GetEntry('ppt/vbaProject.bin')) {
            throw "PPAM 不含 VBA 工程：$PackagePath"
        }
    }
    finally {
        $archive.Dispose()
    }
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$assetRoot = Join-Path $skillRoot 'assets\powerpoint-slide-archive'
$vbaPath = Join-Path $assetRoot 'SlideArchive.bas'
$ribbonPath = Join-Path $assetRoot 'customUI14.xml'
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $assetRoot 'PaperFigureSlideArchive.ppam'
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)

if (-not (Test-Path -LiteralPath $vbaPath -PathType Leaf)) {
    throw "缺少 VBA 源码：$vbaPath"
}
if (-not (Test-Path -LiteralPath $ribbonPath -PathType Leaf)) {
    throw "缺少 RibbonX：$ribbonPath"
}
if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "输出已存在。重建时使用 -Force：$OutputPath"
}

$outputDirectory = Split-Path -Parent $OutputPath
[IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
$temporaryPackage = Join-Path $outputDirectory ('.PaperFigureSlideArchive.' + [Guid]::NewGuid().ToString('N') + '.ppam')

$powerPoint = $null
$presentation = $null
$vbaProject = $null
$component = $null
$codeModule = $null
$blankSlide = $null

try {
    if (-not [string]::IsNullOrWhiteSpace($VbaTemplatePath)) {
        $VbaTemplatePath = [IO.Path]::GetFullPath($VbaTemplatePath)
        if (-not (Test-Path -LiteralPath $VbaTemplatePath -PathType Leaf)) {
            throw "找不到手工 VBA 模板：$VbaTemplatePath"
        }
        [IO.File]::Copy($VbaTemplatePath, $temporaryPackage, $true)
        Assert-VbaProjectPresent -PackagePath $temporaryPackage
    }
    else {
        $runningPowerPoint = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue)
        if ($runningPowerPoint.Count -gt 0) {
            throw '自动构建前请关闭 PowerPoint；脚本不会连接或结束用户正在运行的 PowerPoint。也可关闭 PowerPoint 后通过 -VbaTemplatePath 完成后台构建。'
        }
        $powerPoint = New-Object -ComObject PowerPoint.Application
        $presentation = $powerPoint.Presentations.Add(0)
        $blankSlide = $presentation.Slides.Add(1, 12)

        try {
            $vbaProject = $presentation.VBProject
        }
        catch {
            throw '无法访问 PowerPoint VBA 工程。请确认已启用对 VBA 项目对象模型的访问，或通过 -VbaTemplatePath 提供手工保存的 PPAM。'
        }
        if ($null -eq $vbaProject) {
            throw 'PowerPoint 未返回 VBA 工程。请通过 -VbaTemplatePath 提供手工导入 SlideArchive.bas 后保存的 PPAM。'
        }

        $component = $vbaProject.VBComponents.Add(1)
        $component.Name = 'SlideArchive'
        $codeModule = $component.CodeModule
        $vbaSource = [IO.File]::ReadAllText($vbaPath, [Text.Encoding]::UTF8)
        $attributeLine = 'Attribute VB_Name = "SlideArchive"'
        if ($vbaSource.StartsWith($attributeLine, [StringComparison]::Ordinal)) {
            $vbaSource = $vbaSource.Substring($attributeLine.Length).TrimStart("`r", "`n")
        }
        $codeModule.AddFromString($vbaSource)

        $presentation.SaveAs($temporaryPackage, 30)
        $presentation.Close()
        Release-ComObject $blankSlide
        Release-ComObject $presentation
        $blankSlide = $null
        $presentation = $null

        $powerPoint.Quit()
        Release-ComObject $codeModule
        Release-ComObject $component
        Release-ComObject $vbaProject
        Release-ComObject $powerPoint
        $codeModule = $null
        $component = $null
        $vbaProject = $null
        $powerPoint = $null

        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
        Assert-VbaProjectPresent -PackagePath $temporaryPackage
    }

    Add-RibbonXmlToPackage -PackagePath $temporaryPackage -RibbonPath $ribbonPath

    if (Test-Path -LiteralPath $OutputPath) {
        [IO.File]::Delete($OutputPath)
    }
    [IO.File]::Move($temporaryPackage, $OutputPath)

    [pscustomobject]@{
        status = 'built'
        path = $OutputPath
        sha256 = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash
    } | ConvertTo-Json -Depth 3
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch {}
    }
    if ($null -ne $powerPoint) {
        try { $powerPoint.Quit() } catch {}
    }
    Release-ComObject $codeModule
    Release-ComObject $component
    Release-ComObject $vbaProject
    Release-ComObject $blankSlide
    Release-ComObject $presentation
    Release-ComObject $powerPoint
    if (Test-Path -LiteralPath $temporaryPackage) {
        [IO.File]::Delete($temporaryPackage)
    }
}
