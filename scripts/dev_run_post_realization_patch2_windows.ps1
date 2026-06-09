param(
    [string]$PythonPath = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [int]$NumChunks = 20,
    [int]$NumCpu = 1
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
$PatchDir = Join-Path $RepoRoot "experiments\patch2_post_realization"
$ResultsDir = Join-Path $PatchDir "outputs"
$DbDir = Join-Path $PatchDir "dbs"
New-Item -ItemType Directory -Force -Path $LogsDir, $ResultsDir, $DbDir | Out-Null

if (-not (Test-Path $PythonPath)) {
    throw "Python not found at $PythonPath"
}

function New-Patch2Window {
    param(
        [string]$Title,
        [string]$LogPath,
        [string]$Command
    )

$windowCommand = @"
`$Host.UI.RawUI.WindowTitle = '$Title'
Set-Location '$RepoRoot'
Remove-Item -LiteralPath '$LogPath' -Force -ErrorAction SilentlyContinue
& {
Write-Host 'Starting: $Title'
Write-Host 'Log: $LogPath'
Write-Host 'Command: $Command'
$Command
Write-Host 'Finished: $Title'
} *>&1 | Tee-Object -FilePath '$LogPath'
"@
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $windowCommand
    )
}

$iter20kOut = Join-Path $ResultsDir "patch2_20k_streaming_iteration_parquet"
$duckdb20kOut = Join-Path $ResultsDir "patch2_20k_streaming_duckdb_table"
$fullOut = Join-Path $ResultsDir "patch2_fullflow_one_iter_streaming_no_combine"
$iter20kDb = Join-Path $DbDir "patch2_20k_streaming_iteration_parquet.duckdb"
$duckdb20kDb = Join-Path $DbDir "patch2_20k_streaming_duckdb_table.duckdb"
$fullDb = Join-Path $DbDir "patch2_fullflow_one_iter_streaming_no_combine.duckdb"
$reportPath = Join-Path $PatchDir "patch2_20k_output_mode_validation.json"

$run20kIteration = @"
Remove-Item -LiteralPath '$iter20kOut' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$iter20kOut' | Out-Null
`$before = if (Test-Path '$iter20kDb') { (Get-Item '$iter20kDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'iteration_parquet'
`$env:NIRD_COMBINE_ODPFC_PARTS = '1'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
`$env:NIRD_SAMPLE_OD_N = '20000'
`$env:NIRD_BASELINE_DB_PATH = '$iter20kDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$iter20kOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$iter20kDb') { (Get-Item '$iter20kDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "odpfc part count: `$((Get-ChildItem '$iter20kOut\odpfc_parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

$validate20k = @"
while (-not (Test-Path '$iter20kOut\odpfc.pq')) {
  Write-Host 'Waiting for Patch2_20k_streaming_iteration_parquet...'
  Start-Sleep -Seconds 15
}
Remove-Item -LiteralPath '$duckdb20kOut' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$duckdb20kOut' | Out-Null
`$before = if (Test-Path '$duckdb20kDb') { (Get-Item '$duckdb20kDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'duckdb_table'
`$env:NIRD_COMBINE_ODPFC_PARTS = '1'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
`$env:NIRD_SAMPLE_OD_N = '20000'
`$env:NIRD_BASELINE_DB_PATH = '$duckdb20kDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$duckdb20kOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$duckdb20kDb') { (Get-Item '$duckdb20kDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
& "$PythonPath" .\scripts\dev_validate_post_realization_patch2.py --duckdb-dir '$duckdb20kOut' --iteration-dir '$iter20kOut' --report-path '$reportPath'
"@

$runFullOneIter = @"
Remove-Item -LiteralPath '$fullOut' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$fullOut' | Out-Null
`$before = if (Test-Path '$fullDb') { (Get-Item '$fullDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'iteration_parquet'
`$env:NIRD_COMBINE_ODPFC_PARTS = '0'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
Remove-Item Env:\NIRD_SAMPLE_OD_N -ErrorAction SilentlyContinue
`$env:NIRD_BASELINE_DB_PATH = '$fullDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$fullOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$fullDb') { (Get-Item '$fullDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "odpfc part count: `$((Get-ChildItem '$fullOut\odpfc_parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

New-Patch2Window `
    -Title "Patch2_20k_streaming_iteration_parquet" `
    -LogPath (Join-Path $LogsDir "patch2_20k_streaming_iteration_parquet.log") `
    -Command $run20kIteration

New-Patch2Window `
    -Title "Patch2_20k_validation_compare" `
    -LogPath (Join-Path $LogsDir "patch2_20k_validation_compare.log") `
    -Command $validate20k

New-Patch2Window `
    -Title "Patch2_fullflow_one_iter_streaming_no_combine" `
    -LogPath (Join-Path $LogsDir "patch2_fullflow_one_iter_streaming_no_combine.log") `
    -Command $runFullOneIter

Write-Host "Launched Patch 2 windows."
Write-Host "Logs: $LogsDir"
Write-Host "Patch outputs: $PatchDir"
