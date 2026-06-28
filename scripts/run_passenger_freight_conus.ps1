param(
    [int]$DepthKey = 30,
    [int[]]$EventKeys = @(1, 2, 3),
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$MaxFlowIterations = 0,
    [int]$LodesYear = 2022,
    [string]$ResultsVariant = "revision",
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [switch]$SkipLodesBuild,
    [switch]$LodesCountyOnly,
    [switch]$ForceLodesRebuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$wrapper = Join-Path $logDir "${ts}_passenger_freight_conus_wrapper.log"

"wrapper_start=$(Get-Date -Format o)" | Tee-Object -FilePath $wrapper
"command=passenger+freight CONUS pipeline" | Tee-Object -FilePath $wrapper -Append

if (-not $SkipLodesBuild) {
    $lodesArgs = @(
        "scripts/build_lodes_passenger_od.py",
        "--year", "$LodesYear"
    )
    if ($ForceLodesRebuild) {
        $lodesArgs += "--force-county"
    }
    if ($LodesCountyOnly) {
        $lodesArgs += "--skip-centroid"
    }
    & $Python @lodesArgs *>&1 | Tee-Object -FilePath $wrapper -Append
    if ($LASTEXITCODE -ne 0) {
        throw "LODES passenger OD build failed with exit code $LASTEXITCODE"
    }
}

if (-not $LodesCountyOnly) {
    $patchArgs = @(
        "-File", (Join-Path $repoRoot "scripts\run_patch5_recovery_conus.ps1"),
        "-IncludePassenger",
        "-LodesYear", "$LodesYear",
        "-DepthKey", "$DepthKey",
        "-NumChunks", "$NumChunks",
        "-NumCpu", "$NumCpu",
        "-MaxFlowIterations", "$MaxFlowIterations",
        "-ResultsVariant", $ResultsVariant
    )
    foreach ($ek in $EventKeys) {
        $patchArgs += "-EventKeys"
        $patchArgs += "$ek"
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass @patchArgs *>&1 | Tee-Object -FilePath $wrapper -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Passenger+freight Pass A/B workflow failed with exit code $LASTEXITCODE"
    }
}

"wrapper_done=$(Get-Date -Format o)" | Tee-Object -FilePath $wrapper -Append
