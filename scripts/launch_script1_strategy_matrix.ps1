param(
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$SampleStride = 500,
    [int]$MaxFlowIterations = 1,
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [switch]$IncludeLegacy
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "launch_script1_profile_window.ps1"

$runs = @(
    @{ RunName = "script1_option1_compact_sql"; Strategy = "compact_sql" },
    @{ RunName = "script1_option2_duckdb_chunked_compact"; Strategy = "duckdb_chunked_compact" },
    @{ RunName = "script1_option3_pandas_chunked"; Strategy = "pandas_chunked" }
)

if ($IncludeLegacy) {
    $runs += @{ RunName = "script1_legacy_materialized"; Strategy = "legacy_materialized"; Legacy = $true }
}

foreach ($run in $runs) {
    $args = @(
        "-ExecutionPolicy", "Bypass",
        "-File", $launcher,
        "-NumChunks", "$NumChunks",
        "-NumCpu", "$NumCpu",
        "-SampleStride", "$SampleStride",
        "-MaxFlowIterations", "$MaxFlowIterations",
        "-Python", $Python,
        "-RunName", $run.RunName,
        "-PathStrategy", $run.Strategy
    )
    if ($run.Legacy) {
        $args += "-LegacyPandasOutput"
        $args += "-DisableCompactPathAgg"
    }
    Start-Process powershell.exe -ArgumentList $args
}

Write-Host "Launched $($runs.Count) visible Script 1 strategy windows."
