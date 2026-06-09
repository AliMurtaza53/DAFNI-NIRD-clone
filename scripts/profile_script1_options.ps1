param(
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$SampleStride = 500,
    [int]$MaxFlowIterations = 1,
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$profileDir = Join-Path $repoRoot "experiments\option_profiles"
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Push-Location $repoRoot
try {
    $oldMaxIterations = $env:NIRD_MAX_FLOW_ITERATIONS
    $oldBaselineDbPath = $env:NIRD_BASELINE_DB_PATH
    $oldBaseOutDir = $env:NIRD_BASE_SCENARIO_OUT_DIR
    $oldDirectOutputs = $env:NIRD_DIRECT_DUCKDB_OUTPUTS
    $oldChunkedExpansion = $env:NIRD_DUCKDB_CHUNKED_PATH_EXPANSION
    $oldCompactPathAgg = $env:NIRD_DUCKDB_COMPACT_PATH_AGG
    $oldPathStrategy = $env:NIRD_PATH_REALIZATION_STRATEGY

    $env:NIRD_MAX_FLOW_ITERATIONS = "$MaxFlowIterations"

    $env:NIRD_BASELINE_DB_PATH = Join-Path $profileDir "script1_baseline.duckdb"
    $env:NIRD_BASE_SCENARIO_OUT_DIR = Join-Path $profileDir "script1_baseline_outputs"
    $env:NIRD_DIRECT_DUCKDB_OUTPUTS = "0"
    $env:NIRD_DUCKDB_CHUNKED_PATH_EXPANSION = "0"
    $env:NIRD_DUCKDB_COMPACT_PATH_AGG = "0"
    $env:NIRD_PATH_REALIZATION_STRATEGY = "legacy_materialized"
    & $Python -m cProfile -o (Join-Path $profileDir "script1_baseline.prof") `
        scripts\1_network_flow_model_revision.py `
        $NumChunks $NumCpu $SampleStride

    $env:NIRD_BASELINE_DB_PATH = Join-Path $profileDir "script1_option1.duckdb"
    $env:NIRD_BASE_SCENARIO_OUT_DIR = Join-Path $profileDir "script1_option1_outputs"
    $env:NIRD_DIRECT_DUCKDB_OUTPUTS = "1"
    $env:NIRD_DUCKDB_CHUNKED_PATH_EXPANSION = "0"
    $env:NIRD_DUCKDB_COMPACT_PATH_AGG = "1"
    $env:NIRD_PATH_REALIZATION_STRATEGY = "compact_sql"
    & $Python -m cProfile -o (Join-Path $profileDir "script1_option1_direct_duckdb.prof") `
        scripts\1_network_flow_model_revision.py `
        $NumChunks $NumCpu $SampleStride

    & $Python tools\compare_profiles.py `
        --profiles_dir $profileDir `
        --out_dir (Join-Path $profileDir "summary")
}
finally {
    $env:NIRD_MAX_FLOW_ITERATIONS = $oldMaxIterations
    $env:NIRD_BASELINE_DB_PATH = $oldBaselineDbPath
    $env:NIRD_BASE_SCENARIO_OUT_DIR = $oldBaseOutDir
    $env:NIRD_DIRECT_DUCKDB_OUTPUTS = $oldDirectOutputs
    $env:NIRD_DUCKDB_CHUNKED_PATH_EXPANSION = $oldChunkedExpansion
    $env:NIRD_DUCKDB_COMPACT_PATH_AGG = $oldCompactPathAgg
    $env:NIRD_PATH_REALIZATION_STRATEGY = $oldPathStrategy
    Pop-Location
}
