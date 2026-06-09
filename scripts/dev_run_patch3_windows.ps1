param(
    [string]$PythonPath = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$DepthKey = 50,
    [int]$EventKey = 1,
    [string]$Variant = "patch3_path_index_smoke"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
$PatchDir = Join-Path $RepoRoot "experiments\patch3_path_index"
$ResultsDir = Join-Path $PatchDir "outputs"
$DbDir = Join-Path $PatchDir "dbs"
$DataResults = "C:\Users\akothaw\Desktop\data\results"
$FullFlowOut = Join-Path $DataResults "base_scenario\$Variant"
New-Item -ItemType Directory -Force -Path $LogsDir, $ResultsDir, $DbDir, $FullFlowOut | Out-Null

if (-not (Test-Path $PythonPath)) {
    throw "Python not found at $PythonPath"
}

function New-Patch3Window {
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

$legacyOut = Join-Path $ResultsDir "patch3_20k_full_odpfc_legacy"
$indexOut = Join-Path $ResultsDir "patch3_20k_path_index"
$legacyDb = Join-Path $DbDir "patch3_20k_full_odpfc_legacy.duckdb"
$indexDb = Join-Path $DbDir "patch3_20k_path_index.duckdb"
$fullDb = Join-Path $DbDir "patch3_fullflow_one_iter_path_index.duckdb"
$reportPath = Join-Path $PatchDir "patch3_20k_path_index_validation.json"

$runLegacy = @"
Remove-Item -LiteralPath '$legacyOut' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$legacyOut' | Out-Null
`$before = if (Test-Path '$legacyDb') { (Get-Item '$legacyDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'full_odpfc'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'duckdb_table'
`$env:NIRD_COMBINE_ODPFC_PARTS = '1'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
`$env:NIRD_SAMPLE_OD_N = '20000'
`$env:NIRD_BASELINE_DB_PATH = '$legacyDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$legacyOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$legacyDb') { (Get-Item '$legacyDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
"@

$runIndex = @"
while (-not (Test-Path '$legacyOut\odpfc.pq')) {
  Write-Host 'Waiting for Patch3_20k_full_odpfc_legacy...'
  Start-Sleep -Seconds 10
}
Remove-Item -LiteralPath '$indexOut' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$indexOut' | Out-Null
`$before = if (Test-Path '$indexDb') { (Get-Item '$indexDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'path_index'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
`$env:NIRD_SAMPLE_OD_N = '20000'
`$env:NIRD_BASELINE_DB_PATH = '$indexDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$indexOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$indexDb') { (Get-Item '$indexDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "path_index part count: `$((Get-ChildItem '$indexOut\baseline_path_index_parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

$runValidate = @"
while (-not (Test-Path '$indexOut\baseline_od_meta.pq')) {
  Write-Host 'Waiting for Patch3_20k_path_index...'
  Start-Sleep -Seconds 10
}
& "$PythonPath" .\scripts\dev_validate_path_index_patch3.py --legacy-dir '$legacyOut' --path-index-dir '$indexOut' --report-path '$reportPath'
"@

$runFull = @"
while (-not (Test-Path '$reportPath')) {
  Write-Host 'Waiting for Patch3_20k_validate_path_index...'
  Start-Sleep -Seconds 15
}
New-Item -ItemType Directory -Force -Path '$FullFlowOut' | Out-Null
`$before = if (Test-Path '$fullDb') { (Get-Item '$fullDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_RESULTS_VARIANT = '$Variant'
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'path_index'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
Remove-Item Env:\NIRD_SAMPLE_OD_N -ErrorAction SilentlyContinue
`$env:NIRD_BASELINE_DB_PATH = '$fullDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$FullFlowOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$fullDb') { (Get-Item '$fullDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "path_index part count: `$((Get-ChildItem '$FullFlowOut\baseline_path_index_parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

$runScript4 = @"
while (-not (Test-Path '$FullFlowOut\baseline_od_meta.pq')) {
  Write-Host 'Waiting for Patch3_fullflow_one_iter_path_index_no_full_odpfc...'
  Start-Sleep -Seconds 30
}
`$env:NIRD_RESULTS_VARIANT = '$Variant'
& "$PythonPath" .\scripts\4_rerouting_and_recovery_scenario_loop.py $DepthKey $EventKey $NumChunks $NumCpu
"@

New-Patch3Window `
    -Title "Patch3_20k_full_odpfc_legacy" `
    -LogPath (Join-Path $LogsDir "patch3_20k_full_odpfc_legacy.log") `
    -Command $runLegacy

New-Patch3Window `
    -Title "Patch3_20k_path_index" `
    -LogPath (Join-Path $LogsDir "patch3_20k_path_index.log") `
    -Command $runIndex

New-Patch3Window `
    -Title "Patch3_20k_validate_path_index" `
    -LogPath (Join-Path $LogsDir "patch3_20k_validate_path_index.log") `
    -Command $runValidate

New-Patch3Window `
    -Title "Patch3_fullflow_one_iter_path_index_no_full_odpfc" `
    -LogPath (Join-Path $LogsDir "patch3_fullflow_one_iter_path_index_no_full_odpfc.log") `
    -Command $runFull

New-Patch3Window `
    -Title "Patch3_script4_hazard_event_path_index_loader" `
    -LogPath (Join-Path $LogsDir "patch3_script4_hazard_event_path_index_loader.log") `
    -Command $runScript4

Write-Host "Launched Patch 3 windows in dependency order."
Write-Host "Logs: $LogsDir"
Write-Host "Patch outputs: $PatchDir"
Write-Host "Full-flow base scenario output: $FullFlowOut"
