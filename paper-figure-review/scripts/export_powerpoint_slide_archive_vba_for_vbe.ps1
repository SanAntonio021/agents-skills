[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $skillRoot 'assets\powerpoint-slide-archive\SlideArchive.bas'
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "缺少 VBA 源码：$sourcePath"
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $outputDirectory = Join-Path ([IO.Path]::GetTempPath()) 'PaperFigureSlideArchive-VBA'
    [IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
    $OutputPath = Join-Path $outputDirectory ('SlideArchive-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.bas')
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "输出已存在；覆盖时使用 -Force：$OutputPath"
}
[IO.Directory]::CreateDirectory((Split-Path -Parent $OutputPath)) | Out-Null

$source = [IO.File]::ReadAllText($sourcePath, [Text.Encoding]::UTF8)
$codePage = [Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage
$encoding = [Text.Encoding]::GetEncoding(
    $codePage,
    [Text.EncoderFallback]::ExceptionFallback,
    [Text.DecoderFallback]::ExceptionFallback
)
try {
    $bytes = $encoding.GetBytes($source)
}
catch {
    throw "当前 ANSI 代码页 $codePage 不能完整表示 VBA 源码；请改用已启用 VBOM 的自动构建路径。"
}

[IO.File]::WriteAllBytes($OutputPath, $bytes)
[pscustomobject]@{
    status = 'exported'
    path = $OutputPath
    code_page = $codePage
    sha256 = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 3
