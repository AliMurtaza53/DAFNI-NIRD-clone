param(
    [int]$DepthKey = 30,
    [string]$EventKey = "1",
    [string]$Python = "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:PYTHONIOENCODING = "utf-8"
$env:NIRD_ENABLE_SPLIT_CACHE = "1"
$env:NIRD_TOY_FLOOD_TYPES = "flood"
$env:NIRD_RESULTS_VARIANT = "revision"

New-Item -ItemType Directory -Force -Path "profiles", "logs" | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$profilePath = Join-Path "profiles" "script2_event1_raster_extent_prefilter_$stamp.prof"
$logPath = Join-Path "logs" "script2_event1_raster_extent_prefilter_$stamp.log"

Write-Host "Running Script 2 event $EventKey with raster-extent prefilter"
Write-Host "Profile: $profilePath"
Write-Host "Log: $logPath"
Write-Host ""

$pythonCommand = "`"$Python`" -u -m cProfile -o `"$profilePath`" scripts\2_intersection_analysis.py $DepthKey $EventKey 2>&1"
& cmd.exe /d /c $pythonCommand |
    Tee-Object -FilePath $logPath

$exitCode = $LASTEXITCODE
Write-Host ""
Write-Host "Exit code: $exitCode"
if ($exitCode -eq 0) {
    Write-Host "Script 2 profile run completed successfully."
} else {
    Write-Host "Script 2 profile run failed."
}
Write-Host "Window left open for inspection."
