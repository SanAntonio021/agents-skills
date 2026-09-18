param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
if(-not [IO.Path]::IsPathRooted($Destination)){throw 'Destination must be an absolute path.'}
$target=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $target){throw 'Choose a new directory; existing projects are never overwritten.'}
$source=Join-Path (Split-Path $PSScriptRoot) 'assets\workbench'
if(-not (Test-Path -LiteralPath (Join-Path $source 'Template_Demo.m'))){throw 'Template incomplete.'}
$manifest=Join-Path (Split-Path $PSScriptRoot) 'references\provenance\template-files.json'
$files=Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($entry in $files){
    $inputPath=[IO.Path]::GetFullPath((Join-Path $source $entry.path))
    if(-not $inputPath.StartsWith([IO.Path]::GetFullPath($source)+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Manifest path leaves template.'}
    if(-not (Test-Path -LiteralPath $inputPath -PathType Leaf)){throw "Template file missing: $($entry.path)"}
    if((Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash -ne $entry.sha256){throw "Template hash mismatch: $($entry.path)"}
}
New-Item -ItemType Directory -Path $target | Out-Null
foreach($entry in $files){
    $outputPath=Join-Path $target $entry.path
    New-Item -ItemType Directory -Path (Split-Path $outputPath) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $source $entry.path) -Destination $outputPath
}
$skillRoot=Split-Path (Split-Path (Split-Path $PSScriptRoot))
$agentTemplate=Join-Path $skillRoot 'assets\project-template\AGENTS.md.template'
$utf8=[Text.UTF8Encoding]::new($false)
$agentText=[IO.File]::ReadAllText($agentTemplate,$utf8).Replace('{{PROJECT_NAME}}',[IO.Path]::GetFileName($target)).Replace('与 lab.md','与 README.md 中的记录').Replace('项目布局、逐次输出和 compact/full 见 README.md。','入口、依赖和验证进展见 README.md。')
[IO.File]::WriteAllText((Join-Path $target 'AGENTS.md'),$agentText,$utf8)
$readme=Join-Path $target 'README.md'
$readmeText=[IO.File]::ReadAllText($readme,$utf8).Replace('详细适配、数据接口、设备参考和来源清单见所属技能的 references','适配与设备历史来源由原技能维护；本副本的运行入口和依赖均在当前项目内')
$readmeText+="`n环境：MATLAB R2023b；生成和接收需 Communications Toolbox、Signal Processing Toolbox，其他专项按实际依赖配置。`n当前进展：已复制工程，尚未执行本副本的软件验证；在此记录验证结果与未完成事项。`n正式代码、配置、实验数据、重绘输入及必要日志按用途保留；临时草稿与预览集中在过程文件/任务主题/。显式收尾时先归位成果、更新引用并验证，再清空本任务目录。交付前检查 Template 入口及声明依赖不指向待清理目录，并执行所需离线验证。`n"
[IO.File]::WriteAllText($readme,$readmeText,$utf8)
Write-Output "Template copied to $target. Start with Template_Demo; no hardware was accessed."
