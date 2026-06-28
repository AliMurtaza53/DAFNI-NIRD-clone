param(
    [int]$DepthKey = 30,
    [int[]]$EventKeys = @(1, 2, 3),
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

. (Join-Path $PSScriptRoot "lib\nird_geo_env.ps1") -Python $Python

Remove-Item Env:NIRD_OD_MULTIPLIER -ErrorAction SilentlyContinue
Remove-Item Env:NIRD_OD_TARGET_TOTAL -ErrorAction SilentlyContinue

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

    foreach ($eventKey in $EventKeys) {
        Invoke-Step "script2_depth${DepthKey}_event${eventKey}" @("scripts/2_intersection_analysis.py", "$DepthKey", "$eventKey")
    }

    Invoke-Step "script3_damage_analysis" @("scripts/3_damage_analysis.py")
    Invoke-Step "script3_postprocess_damage" @("scripts/3_postprocess_damage.py")

    foreach ($eventKey in $EventKeys) {
        Invoke-Step "script4_depth${DepthKey}_event${eventKey}" @(
            "scripts/4_rerouting_and_recovery_scenario_loop.py",
            "$DepthKey",
            "$eventKey",
            "$NumChunks",
            "$NumCpu"
        )
    }

    Write-Host ""
    Write-Host "Workflow completed successfully."
}
finally {
    Pop-Location
}
