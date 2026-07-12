[CmdletBinding()]
param(
    [string]$AddInPath,
    [string]$PythonPath,
    [string]$WorkDirectory,
    [switch]$KeepArtifacts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Release-ComObject {
    param([object]$InputObject)
    if ($null -ne $InputObject -and [Runtime.InteropServices.Marshal]::IsComObject($InputObject)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($InputObject)
    }
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-ArchiveTestMacro {
    param([object]$Application)

    $macroNames = @(
        'PaperFigureSlideArchive.ppam!PFR_TestArchiveCurrentSlide',
        "'PaperFigureSlideArchive.ppam'!PFR_TestArchiveCurrentSlide",
        'PFR_TestArchiveCurrentSlide'
    )
    $lastError = $null
    foreach ($macroName in $macroNames) {
        try {
            return $Application.Run($macroName)
        }
        catch {
            $lastError = $_
        }
    }
    throw "无法调用加载项测试入口：$($lastError.Exception.Message)"
}

$running = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    throw '集成测试前请关闭 PowerPoint；脚本不会结束用户正在运行的 PowerPoint。'
}

if ([string]::IsNullOrWhiteSpace($AddInPath)) {
    $AddInPath = Join-Path $env:APPDATA 'Microsoft\AddIns\PaperFigureSlideArchive.ppam'
}
$AddInPath = [IO.Path]::GetFullPath($AddInPath)
if (-not (Test-Path -LiteralPath $AddInPath -PathType Leaf)) {
    throw "加载项尚未安装：$AddInPath"
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw '未找到 Python；请通过 -PythonPath 指定带 Pillow 的 Python。'
    }
    $PythonPath = $pythonCommand.Source
}
$PythonPath = [IO.Path]::GetFullPath($PythonPath)

$ownsWorkDirectory = $false
if ([string]::IsNullOrWhiteSpace($WorkDirectory)) {
    $WorkDirectory = Join-Path ([IO.Path]::GetTempPath()) ('paper-figure-slide-archive-' + [Guid]::NewGuid().ToString('N'))
    $ownsWorkDirectory = $true
}
$WorkDirectory = [IO.Path]::GetFullPath($WorkDirectory)
[IO.Directory]::CreateDirectory($WorkDirectory) | Out-Null
if (-not $ownsWorkDirectory) {
    $existingItems = @(Get-ChildItem -LiteralPath $WorkDirectory -Force)
    if ($existingItems.Count -gt 0) {
        throw "指定的 WorkDirectory 必须为空，测试不会覆盖或清理已有内容：$WorkDirectory"
    }
}

$presentationPath = Join-Path $WorkDirectory 'archive-integration-test.pptx'
$sourcePng = Join-Path $WorkDirectory 'source.png'
$archive1Png = Join-Path $WorkDirectory 'archive-1.png'
$archive2Png = Join-Path $WorkDirectory 'archive-2.png'
$comparisonScript = Join-Path $PSScriptRoot 'compare_png_pixels.py'

$powerPoint = $null
$presentation = $null
$slides = $null
$slide1 = $null
$slide2 = $null
$archiveSlide1 = $null
$archiveSlide2 = $null
$shape = $null
$textBox = $null
$activeSlide = $null

try {
    $powerPoint = New-Object -ComObject PowerPoint.Application

    $matchingAddIn = $null
    for ($index = 1; $index -le $powerPoint.AddIns.Count; $index++) {
        $candidate = $powerPoint.AddIns.Item($index)
        if ([string]::Equals([IO.Path]::GetFullPath($candidate.FullName), $AddInPath, [StringComparison]::OrdinalIgnoreCase)) {
            $matchingAddIn = $candidate
            break
        }
        Release-ComObject $candidate
    }
    Assert-True ($null -ne $matchingAddIn) 'PowerPoint 没有注册目标加载项。'
    Assert-True ($matchingAddIn.Loaded -eq -1) '目标加载项没有自动加载。'
    Release-ComObject $matchingAddIn

    $noDeckResult = Invoke-ArchiveTestMacro -Application $powerPoint
    Assert-True (-not [bool]$noDeckResult) '没有演示文稿时不应创建留档。'

    $presentation = $powerPoint.Presentations.Add(-1)
    $powerPoint.Visible = -1
    try { $powerPoint.WindowState = 2 } catch {}
    $slides = $presentation.Slides
    while ($slides.Count -gt 0) {
        $slides.Item(1).Delete()
    }

    $slide1 = $slides.Add(1, 12)
    $shape = $slide1.Shapes.AddShape(1, 72, 72, 500, 210)
    $shape.Fill.ForeColor.RGB = 10181046
    $shape.Line.ForeColor.RGB = 3158064
    $textBox = $slide1.Shapes.AddTextbox(1, 105, 310, 600, 90)
    $textBox.TextFrame.TextRange.Text = 'archive integration test'
    $textBox.TextFrame.TextRange.Font.Name = 'Arial'
    $textBox.TextFrame.TextRange.Font.Size = 28

    $slide2 = $slides.Add(2, 12)
    $shape = $slide2.Shapes.AddShape(9, 150, 120, 300, 300)
    $shape.Fill.ForeColor.RGB = 3434905

    $powerPoint.ActiveWindow.View.GotoSlide(1)
    $unsavedResult = Invoke-ArchiveTestMacro -Application $powerPoint
    Assert-True (-not [bool]$unsavedResult) '未保存演示文稿不应创建留档。'
    Assert-True ($slides.Count -eq 2) '未保存演示文稿的页数被修改。'

    $presentation.SaveAs($presentationPath, 24)
    $sourceSlideId = $slide1.SlideID
    $sourceIndex = $slide1.SlideIndex

    $presentation.Save()
    Assert-True ($slides.Count -eq 2) '普通保存不应创建历史副本。'
    $writeTimeBeforeArchive = (Get-Item -LiteralPath $presentationPath).LastWriteTimeUtc

    $powerPoint.ActiveWindow.View.GotoSlide($sourceIndex)
    $archiveResult = Invoke-ArchiveTestMacro -Application $powerPoint
    Assert-True ([bool]$archiveResult) '留档宏没有报告成功。'
    Assert-True ($slides.Count -eq 3) '点击一次后页数必须只增加 1。'
    Assert-True ($slide1.SlideIndex -eq $sourceIndex) '原页位置发生变化。'
    Assert-True ($slides.Item($sourceIndex).SlideID -eq $sourceSlideId) '原页已被替换。'

    $archiveSlide1 = $slides.Item($slides.Count)
    Assert-True ($archiveSlide1.SlideShowTransition.Hidden -eq -1) '末页副本没有隐藏。'
    Assert-True ($archiveSlide1.Tags.Item('PFR_ARCHIVE_MARKER') -eq '1') '历史副本缺少标记。'
    Assert-True ($archiveSlide1.Tags.Item('PFR_ARCHIVE_SOURCE_SLIDE_ID') -eq [string]$sourceSlideId) '源 Slide ID 记录错误。'
    Assert-True ($archiveSlide1.Tags.Item('PFR_ARCHIVE_SOURCE_SLIDE_INDEX') -eq [string]$sourceIndex) '源页位置记录错误。'
    Assert-True ($archiveSlide1.Tags.Item('PFR_ARCHIVE_VERSION') -eq '1') '首次留档版本号应为 1。'
    Assert-True (-not [string]::IsNullOrWhiteSpace($archiveSlide1.Tags.Item('PFR_ARCHIVE_TIMESTAMP'))) '历史副本缺少时间。'

    $hiddenCount = 0
    for ($index = 1; $index -le $slides.Count; $index++) {
        if ($slides.Item($index).SlideShowTransition.Hidden -eq -1) {
            $hiddenCount++
        }
    }
    Assert-True ($hiddenCount -eq 1) '点击一次必须只生成一个隐藏副本。'

    $activeSlide = $powerPoint.ActiveWindow.View.Slide
    Assert-True ($activeSlide.SlideID -eq $sourceSlideId) '留档后没有恢复选中原页。'
    Assert-True ($presentation.Saved -eq -1) '留档后演示文稿没有保存。'

    $secondArchiveResult = Invoke-ArchiveTestMacro -Application $powerPoint
    Assert-True ([bool]$secondArchiveResult) '第二次留档宏没有报告成功。'
    Assert-True ($slides.Count -eq 4) '连续留档两次后页数必须增加 2。'
    Assert-True ($slide1.SlideIndex -eq $sourceIndex) '第二次留档后原页位置发生变化。'
    Assert-True ($slides.Item($sourceIndex).SlideID -eq $sourceSlideId) '第二次留档后原页已被替换。'

    Release-ComObject $archiveSlide1
    $archiveSlide1 = $slides.Item($slides.Count - 1)
    $archiveSlide2 = $slides.Item($slides.Count)
    Assert-True ($archiveSlide1.SlideShowTransition.Hidden -eq -1) '首次历史页不再隐藏。'
    Assert-True ($archiveSlide2.SlideShowTransition.Hidden -eq -1) '第二个历史页没有隐藏。'
    Assert-True ($archiveSlide1.SlideIndex -eq 3 -and $archiveSlide2.SlideIndex -eq 4) '两个历史页没有连续位于末尾。'
    Assert-True ($archiveSlide1.Tags.Item('PFR_ARCHIVE_VERSION') -eq '1') '首次留档版本号被改变。'
    Assert-True ($archiveSlide2.Tags.Item('PFR_ARCHIVE_VERSION') -eq '2') '第二次留档版本号应为 2。'
    Assert-True ($archiveSlide2.Tags.Item('PFR_ARCHIVE_SOURCE_SLIDE_ID') -eq [string]$sourceSlideId) '第二次留档的源 Slide ID 记录错误。'
    Assert-True (-not [string]::IsNullOrWhiteSpace($archiveSlide2.Tags.Item('PFR_ARCHIVE_TIMESTAMP'))) '第二个历史副本缺少时间。'

    $hiddenCount = 0
    for ($index = 1; $index -le $slides.Count; $index++) {
        if ($slides.Item($index).SlideShowTransition.Hidden -eq -1) {
            $hiddenCount++
        }
    }
    Assert-True ($hiddenCount -eq 2) '连续留档两次必须生成两个隐藏副本。'

    Release-ComObject $activeSlide
    $activeSlide = $powerPoint.ActiveWindow.View.Slide
    Assert-True ($activeSlide.SlideID -eq $sourceSlideId) '第二次留档后没有恢复选中原页。'
    Assert-True ($presentation.Saved -eq -1) '第二次留档后演示文稿没有保存。'

    $slide1.Export($sourcePng, 'PNG', 1280, 720)
    $archiveSlide1.Export($archive1Png, 'PNG', 1280, 720)
    $archiveSlide2.Export($archive2Png, 'PNG', 1280, 720)

    $presentation.Close()
    Release-ComObject $activeSlide
    Release-ComObject $archiveSlide2
    Release-ComObject $archiveSlide1
    Release-ComObject $slide2
    Release-ComObject $slide1
    Release-ComObject $slides
    Release-ComObject $presentation
    $activeSlide = $null
    $archiveSlide2 = $null
    $archiveSlide1 = $null
    $slide2 = $null
    $slide1 = $null
    $slides = $null
    $presentation = $null

    $writeTimeAfterArchive = (Get-Item -LiteralPath $presentationPath).LastWriteTimeUtc
    Assert-True ($writeTimeAfterArchive -ge $writeTimeBeforeArchive) '留档后文件时间没有更新。'

    $presentation = $powerPoint.Presentations.Open($presentationPath, -1, 0, -1)
    $slides = $presentation.Slides
    Assert-True ($slides.Count -eq 4) '重新打开后两个历史副本没有保存。'
    Assert-True ($slides.Item(3).SlideShowTransition.Hidden -eq -1) '重新打开后首次历史页不再隐藏。'
    Assert-True ($slides.Item(4).SlideShowTransition.Hidden -eq -1) '重新打开后第二个历史页不再隐藏。'
    $readOnlyCount = $slides.Count
    $readOnlyResult = Invoke-ArchiveTestMacro -Application $powerPoint
    Assert-True (-not [bool]$readOnlyResult) '只读演示文稿不应创建留档。'
    Assert-True ($slides.Count -eq $readOnlyCount) '只读演示文稿的页数被修改。'
    $presentation.Close()
    Release-ComObject $slides
    Release-ComObject $presentation
    $slides = $null
    $presentation = $null

    $comparison1Json = & $PythonPath $comparisonScript $sourcePng $archive1Png
    if ($LASTEXITCODE -ne 0) {
        throw "原页和首次历史页像素不一致：$comparison1Json"
    }
    $comparison1 = $comparison1Json | ConvertFrom-Json
    Assert-True ([bool]$comparison1.pixels_equal) '原页和首次历史页像素不一致。'

    $comparison2Json = & $PythonPath $comparisonScript $sourcePng $archive2Png
    if ($LASTEXITCODE -ne 0) {
        throw "原页和第二个历史页像素不一致：$comparison2Json"
    }
    $comparison2 = $comparison2Json | ConvertFrom-Json
    Assert-True ([bool]$comparison2.pixels_equal) '原页和第二个历史页像素不一致。'

    $pptxFiles = @(Get-ChildItem -LiteralPath $WorkDirectory -Filter '*.pptx' -File)
    Assert-True ($pptxFiles.Count -eq 1) '测试产生了额外 PPTX。'

    $powerPoint.Quit()
    Release-ComObject $powerPoint
    $powerPoint = $null

    $result = [pscustomobject]@{
        status = 'passed'
        work_directory = $WorkDirectory
        slide_count_before = 2
        slide_count_after = 4
        archive_is_last = $true
        archive_is_hidden = $true
        original_position_unchanged = $true
        original_selection_restored = $true
        pixels_equal = ([bool]$comparison1.pixels_equal -and [bool]$comparison2.pixels_equal)
        metadata_source_slide_id = [string]$sourceSlideId
        metadata_versions = @('1', '2')
        saved_and_reopened = $true
        extra_pptx_count = 0
        unsaved_guard = $true
        readonly_guard = $true
        no_active_deck_guard = $true
    }
    $result | ConvertTo-Json -Depth 4

    if (-not $KeepArtifacts -and $ownsWorkDirectory) {
        $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        if (-not $WorkDirectory.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "拒绝清理不在系统临时目录内的路径：$WorkDirectory"
        }
        [IO.Directory]::Delete($WorkDirectory, $true)
    }
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch {}
    }
    if ($null -ne $powerPoint) {
        try { $powerPoint.Quit() } catch {}
    }
    Release-ComObject $activeSlide
    Release-ComObject $archiveSlide2
    Release-ComObject $archiveSlide1
    Release-ComObject $shape
    Release-ComObject $textBox
    Release-ComObject $slide2
    Release-ComObject $slide1
    Release-ComObject $slides
    Release-ComObject $presentation
    Release-ComObject $powerPoint
}
