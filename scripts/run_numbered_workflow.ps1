param(
    [int]$DepthKey = 30,
    [int[]]$EventKeys = @(1, 2, 3),
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [string]$Python = "python",
    [switch]$RunAlternateScript2,
    [switch]$RunSensitivity
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $safeName = $Name -replace "[^A-Za-z0-9_.-]", "_"
    $logPath = Join-Path $logDir "$timestamp`_$safeName.log"

    Write-Host ""
    Write-Host "==== $Name ===="
    Write-Host "$Python $($Arguments -join ' ')"
    Write-Host "Log: $logPath"

    $oldErrorActionPreference = $ErrorActionPreference
    $oldNativePreference = $null
    $hasNativePreference = Test-Path Variable:\PSNativeCommandUseErrorActionPreference
    if ($hasNativePreference) {
        $oldNativePreference = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }
    try {
        $ErrorActionPreference = "Continue"
        & $Python @Arguments *>&1 | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $oldNativePreference
        }
    }
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode. See $logPath"
    }
}

Push-Location $repoRoot
try {
    Invoke-Step "script1_network_flow" @("scripts/1_network_flow_model_revision.py", "$NumChunks", "$NumCpu")

    if ($RunAlternateScript2) {
        foreach ($eventKey in $EventKeys) {
            Invoke-Step "script2_alt_depth${DepthKey}_event${eventKey}" @("scripts/2_int_analysis.py", "$DepthKey", "$eventKey")
        }
    }

    foreach ($eventKey in $EventKeys) {
        Invoke-Step "script2_intersection_depth${DepthKey}_event${eventKey}" @("scripts/2_intersection_analysis.py", "$DepthKey", "$eventKey")
    }

    Invoke-Step "script3_damage_analysis" @("scripts/3_damage_analysis.py")
    Invoke-Step "script3_postprocess_damage" @("scripts/3_postprocess_damage.py")

    foreach ($eventKey in $EventKeys) {
        Invoke-Step "script4_rerouting_depth${DepthKey}_event${eventKey}" @(
            "scripts/4_rerouting_and_recovery_scenario_loop.py",
            "$DepthKey",
            "$eventKey",
            "$NumChunks",
            "$NumCpu"
        )
    }

    if ($RunSensitivity) {
        Invoke-Step "script5_sensitivity_direct" @("scripts/5_sensitivity_analysis_direct.py")
        Invoke-Step "script5_sensitivity_indirect" @("scripts/5_sensitivity_analysis_indirect.py")
    }

    Write-Host ""
    Write-Host "Numbered workflow completed successfully."
}
finally {
    Pop-Location
}
