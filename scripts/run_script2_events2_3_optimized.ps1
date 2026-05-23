param(
    [int]$DepthKey = 30,
    [string]$EventKeys = "all",
    [string]$Variant = "optimized_3m_20260511",
    [string]$SimplifyToleranceM = "25",
    [string]$ToyFloodTypes = "flood",
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
$profileDir = Join-Path $repoRoot "profiles"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

$env:PYTHONIOENCODING = "utf-8"
$env:NIRD_RESULTS_VARIANT = $Variant
$env:NIRD_ENABLE_SPLIT_CACHE = "1"
$env:NIRD_SPLIT_SIMPLIFY_TOLERANCE_M = $SimplifyToleranceM
$env:NIRD_TOY_FLOOD_TYPES = $ToyFloodTypes

Push-Location $repoRoot
try {
    foreach ($eventKey in @($EventKeys)) {
        $safeEventKey = $eventKey -replace "[^A-Za-z0-9_.-]", "_"
        $safeFloodTypes = $ToyFloodTypes -replace "[^A-Za-z0-9_.-]", "_"
        $name = "script2_event${safeEventKey}_${Variant}_${safeFloodTypes}"
        $profilePath = Join-Path $profileDir "$name.prof"
        $logPath = Join-Path $logDir "$name.log"

        Write-Host ""
        Write-Host "==== Script 2 event_key=$eventKey, depth_key=$DepthKey ===="
        Write-Host "Variant: $Variant"
        Write-Host "Toy flood types: $ToyFloodTypes"
        Write-Host "Simplify tolerance: $SimplifyToleranceM m"
        Write-Host "Profile: $profilePath"
        Write-Host "Log: $logPath"

        & $Python -u -m cProfile -o $profilePath scripts\2_intersection_analysis.py $DepthKey $eventKey *>&1 |
            Tee-Object -FilePath $logPath
        if ($LASTEXITCODE -ne 0) {
            throw "Script 2 event_key=$eventKey failed with exit code $LASTEXITCODE. See $logPath"
        }
    }
}
finally {
    Pop-Location
}
