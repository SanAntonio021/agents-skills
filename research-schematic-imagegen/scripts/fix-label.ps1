[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$Text,
    [Parameter(Mandatory = $true)][int]$X,
    [Parameter(Mandatory = $true)][int]$Y,
    [Parameter(Mandatory = $true)][int]$Width,
    [Parameter(Mandatory = $true)][int]$Height,
    [string]$FontFamily = 'Microsoft YaHei',
    [float]$FontSize = 28,
    [ValidateSet('Regular', 'Bold')][string]$FontStyle = 'Regular',
    [string]$BackgroundColor = '#FFFFFF',
    [string]$TextColor = '#16324F'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$inputFull = [IO.Path]::GetFullPath($InputPath)
$outputFull = [IO.Path]::GetFullPath($OutputPath)
if ($inputFull -eq $outputFull) {
    throw 'InputPath and OutputPath must differ.'
}
if (-not [IO.File]::Exists($inputFull)) {
    throw "Input image not found: $inputFull"
}
if ($Width -le 0 -or $Height -le 0 -or $X -lt 0 -or $Y -lt 0) {
    throw 'X and Y must be non-negative; Width and Height must be positive.'
}

$source = $null
$bitmap = $null
$graphics = $null
$backgroundBrush = $null
$textBrush = $null
$font = $null
$format = $null

try {
    $source = [Drawing.Bitmap]::new($inputFull)
    if (($X + $Width) -gt $source.Width -or ($Y + $Height) -gt $source.Height) {
        throw "Label rectangle exceeds image bounds $($source.Width)x$($source.Height)."
    }
    $bitmap = [Drawing.Bitmap]::new($source)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $backgroundBrush = [Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($BackgroundColor))
    $textBrush = [Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($TextColor))
    $style = if ($FontStyle -eq 'Bold') { [Drawing.FontStyle]::Bold } else { [Drawing.FontStyle]::Regular }
    $font = [Drawing.Font]::new($FontFamily, $FontSize, $style, [Drawing.GraphicsUnit]::Pixel)
    $format = [Drawing.StringFormat]::new()
    $format.Alignment = [Drawing.StringAlignment]::Center
    $format.LineAlignment = [Drawing.StringAlignment]::Center
    $rect = [Drawing.RectangleF]::new($X, $Y, $Width, $Height)
    $graphics.FillRectangle($backgroundBrush, $rect)
    $graphics.DrawString($Text, $font, $textBrush, $rect, $format)
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputFull)) | Out-Null
    $bitmap.Save($outputFull, [Drawing.Imaging.ImageFormat]::Png)
    Write-Output $outputFull
}
finally {
    foreach ($item in @($format, $font, $textBrush, $backgroundBrush, $graphics, $bitmap, $source)) {
        if ($null -ne $item) { $item.Dispose() }
    }
}
