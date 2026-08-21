[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath,

    [string[]]$ScriptArguments = @(),

    [ValidateSet("A", "B", "formal", "unspecified")]
    [string]$DraftVariant = "unspecified",

    [string]$RuntimeRoot = "C:\Users\SanAn\.local\scientific-plotting-runtime",

    [switch]$TestMode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$fixedRuntimeRoot = "C:\Users\SanAn\.local\scientific-plotting-runtime"
$metadataNames = @(
    "PAPER_FIGURE_REVIEW_RUNTIME_ROOT",
    "PAPER_FIGURE_REVIEW_PYTHON",
    "PAPER_FIGURE_REVIEW_PYTHON_VERSION",
    "PAPER_FIGURE_REVIEW_MATPLOTLIB_VERSION",
    "PAPER_FIGURE_REVIEW_SCIENCEPLOTS_VERSION",
    "PAPER_FIGURE_REVIEW_DRAFT_VARIANT",
    "PAPER_FIGURE_REVIEW_FORMAL_STYLE_SOURCE",
    "PYTHONPATH"
)

function Get-ProcessEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    return [Environment]::GetEnvironmentVariable($Name, "Process")
}

function Restore-ProcessEnvironment {
    param([Parameter(Mandatory = $true)][hashtable]$Values)
    foreach ($name in $Values.Keys) {
        $value = $Values[$name]
        if ($null -eq $value) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item -LiteralPath "Env:$name" -Value $value
        }
    }
}

$previousEnvironment = @{}
foreach ($name in $metadataNames) {
    $previousEnvironment[$name] = Get-ProcessEnvironmentValue -Name $name
}

try {
    $resolvedRuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
    $resolvedFixedRuntimeRoot = [IO.Path]::GetFullPath($fixedRuntimeRoot)
    $isFixedRuntime = [StringComparer]::OrdinalIgnoreCase.Equals($resolvedRuntimeRoot, $resolvedFixedRuntimeRoot)
    if (-not $isFixedRuntime) {
        if (-not $TestMode -or $env:PAPER_FIGURE_REVIEW_TEST_MODE -ne "1") {
            throw "RuntimeRoot is fixed to $fixedRuntimeRoot. Non-default roots are allowed only for internal tests with -TestMode and PAPER_FIGURE_REVIEW_TEST_MODE=1."
        }
    }

    $python = Join-Path $resolvedRuntimeRoot ".venv\Scripts\python.exe"
    $launcher = Join-Path $resolvedRuntimeRoot "run-figure.ps1"
    if (-not (Test-Path -LiteralPath $resolvedRuntimeRoot -PathType Container)) {
        throw "Scientific plotting runtime directory was not found: $resolvedRuntimeRoot"
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Runtime Python was not found: $python"
    }
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "Runtime launcher was not found: $launcher"
    }

    $resolvedScript = (Resolve-Path -LiteralPath $ScriptPath -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $resolvedScript -PathType Leaf)) {
        throw "Figure script was not found: $ScriptPath"
    }

    $versionProbe = @'
import importlib.metadata as metadata
import matplotlib
import scienceplots
import sys

print("python=" + ".".join(str(part) for part in sys.version_info[:3]))
print("matplotlib=" + matplotlib.__version__)
print("scienceplots=" + metadata.version("SciencePlots"))
'@
    $probeOutput = @(& $python -c $versionProbe 2>&1)
    $probeExitCode = $LASTEXITCODE
    if ($probeExitCode -ne 0) {
        throw "Runtime dependency probe failed (exit $probeExitCode): $(($probeOutput -join " "))"
    }
    $probeText = $probeOutput -join "`n"
    $pythonVersionMatch = [regex]::Match($probeText, "(?m)^python=(?<value>[^\r\n]+)$")
    $matplotlibVersionMatch = [regex]::Match($probeText, "(?m)^matplotlib=(?<value>[^\r\n]+)$")
    $sciencePlotsVersionMatch = [regex]::Match($probeText, "(?m)^scienceplots=(?<value>[^\r\n]+)$")
    if (-not $pythonVersionMatch.Success -or -not $matplotlibVersionMatch.Success -or -not $sciencePlotsVersionMatch.Success) {
        throw "Runtime dependency probe returned incomplete version metadata: $probeText"
    }
    $pythonVersion = $pythonVersionMatch.Groups["value"].Value
    $matplotlibVersion = $matplotlibVersionMatch.Groups["value"].Value
    $sciencePlotsVersion = $sciencePlotsVersionMatch.Groups["value"].Value
    if (-not $pythonVersion.StartsWith("3.12.", [StringComparison]::Ordinal)) {
        throw "Unsupported runtime Python version: $pythonVersion (expected Python 3.12.x)"
    }
    if ($matplotlibVersion -ne "3.11.1") {
        throw "Unsupported runtime Matplotlib version: $matplotlibVersion (expected 3.11.1)"
    }
    if ($sciencePlotsVersion -ne "2.2.2") {
        throw "Unsupported runtime SciencePlots version: $sciencePlotsVersion (expected 2.2.2)"
    }

    $skillScripts = Split-Path -Parent $PSCommandPath
    $existingPythonPath = $previousEnvironment["PYTHONPATH"]
    if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
        $env:PYTHONPATH = $skillScripts
    } else {
        $env:PYTHONPATH = "$skillScripts$([IO.Path]::PathSeparator)$existingPythonPath"
    }
    $env:PAPER_FIGURE_REVIEW_RUNTIME_ROOT = $resolvedRuntimeRoot
    $env:PAPER_FIGURE_REVIEW_PYTHON = $python
    $env:PAPER_FIGURE_REVIEW_PYTHON_VERSION = $pythonVersion
    $env:PAPER_FIGURE_REVIEW_MATPLOTLIB_VERSION = $matplotlibVersion
    $env:PAPER_FIGURE_REVIEW_SCIENCEPLOTS_VERSION = $sciencePlotsVersion
    $env:PAPER_FIGURE_REVIEW_DRAFT_VARIANT = $DraftVariant
    $env:PAPER_FIGURE_REVIEW_FORMAL_STYLE_SOURCE = "ieee_plot_style.py"

    & $launcher $resolvedScript @ScriptArguments
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
} catch {
    Write-Error $_
    $exitCode = 1
} finally {
    Restore-ProcessEnvironment -Values $previousEnvironment
}

exit $exitCode
