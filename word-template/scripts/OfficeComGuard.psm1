Set-StrictMode -Version Latest

function Test-WordProcessPresent {
    [CmdletBinding()]
    param()

    try {
        $processes = @(Get-Process -Name WINWORD -ErrorAction Stop)
        return $processes.Count -gt 0
    }
    catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
        return $false
    }
    catch {
        throw "Unable to verify whether WINWORD.EXE is running; Word COM is refused. $($_.Exception.Message)"
    }
}

function Assert-WordComPermission {
    [CmdletBinding()]
    param(
        [switch]$AllowOfficeCom,
        [scriptblock]$WordProcessProbe = { Test-WordProcessPresent }
    )

    if (-not $AllowOfficeCom) {
        throw "Word COM is disabled by default. Obtain explicit permission for this operation, then pass -AllowOfficeCom."
    }

    try {
        $wordProcessPresent = [bool](& $WordProcessProbe)
    }
    catch {
        throw "Unable to verify whether WINWORD.EXE is running; Word COM is refused. $($_.Exception.Message)"
    }

    if ($wordProcessPresent) {
        throw "WINWORD.EXE is already running. Refusing to start, connect to, or close Word."
    }
}

Export-ModuleMember -Function `
    Test-WordProcessPresent, `
    Assert-WordComPermission
