param(
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$SampleStride = 1,
    [int]$MaxFlowIterations = 1,
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [string]$RunName = "script1_default_full",
    [ValidateSet("compact_sql", "duckdb_chunked_compact", "pandas_chunked", "legacy_materialized")]
    [string]$PathStrategy = "compact_sql",
    [switch]$LegacyPandasOutput,
    [switch]$ChunkedPathExpansion,
    [switch]$DisableCompactPathAgg
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$profileDir = Join-Path $repoRoot "experiments\option_profiles"
$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$directOutputs = if ($LegacyPandasOutput) { "0" } else { "1" }
$chunkedExpansion = if ($ChunkedPathExpansion) { "1" } else { "0" }
$compactPathAgg = if ($DisableCompactPathAgg) { "0" } else { "1" }
$dbPath = Join-Path $profileDir "$RunName.duckdb"
$outDir = Join-Path $profileDir "$RunName`_outputs"
$profPath = Join-Path $profileDir "$RunName.prof"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "$timestamp`_$RunName.log"

$command = @"
Set-Location "$repoRoot"
Set-Item Env:\NIRD_BASELINE_DB_PATH "$dbPath"
Set-Item Env:\NIRD_BASE_SCENARIO_OUT_DIR "$outDir"
Set-Item Env:\NIRD_MAX_FLOW_ITERATIONS "$MaxFlowIterations"
Set-Item Env:\NIRD_DIRECT_DUCKDB_OUTPUTS "$directOutputs"
Set-Item Env:\NIRD_DUCKDB_CHUNKED_PATH_EXPANSION "$chunkedExpansion"
Set-Item Env:\NIRD_DUCKDB_COMPACT_PATH_AGG "$compactPathAgg"
Set-Item Env:\NIRD_PATH_REALIZATION_STRATEGY "$PathStrategy"
& "$Python" -m cProfile -o "$profPath" scripts\1_network_flow_model_revision.py $NumChunks $NumCpu $SampleStride *>&1 | Tee-Object -FilePath "$logPath"
Write-Host ""
Write-Host "Profile: $profPath"
Write-Host "Log:     $logPath"
Write-Host "Outputs: $outDir"
"@

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $command
)

Write-Host "Opened visible PowerShell profile window."
Write-Host "Log: $logPath"
Write-Host "Profile: $profPath"
Write-Host "Outputs: $outDir"
