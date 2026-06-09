param(
    [string]$PythonPath = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$SyntheticEdgeCount = 50,
    [string]$ValidationEventId = "synthetic_20k",
    [string]$FullFlowEventId = "50_1",
    [string]$Variant = "patch5_fused_event_candidates_smoke"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
$PatchDir = Join-Path $RepoRoot "experiments\patch5_fused_event_candidates"
$ResultsDir = Join-Path $PatchDir "outputs"
$DbDir = Join-Path $PatchDir "dbs"
$SyntheticDir = Join-Path $PatchDir "synthetic"
$DataResults = "C:\Users\akothaw\Desktop\data\results"
$FullFlowOut = Join-Path $DataResults "base_scenario\$Variant"
New-Item -ItemType Directory -Force -Path $LogsDir, $ResultsDir, $DbDir, $SyntheticDir, $FullFlowOut | Out-Null

if (-not (Test-Path $PythonPath)) {
    throw "Python not found at $PythonPath"
}

function New-Patch5Window {
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

$patch4Out = Join-Path $ResultsDir "patch5_20k_patch4_reference"
$patch5Out = Join-Path $ResultsDir "patch5_20k_fused_event_candidates"
$patch4Db = Join-Path $DbDir "patch5_20k_patch4_reference.duckdb"
$patch5Db = Join-Path $DbDir "patch5_20k_fused_event_candidates.duckdb"
$fullDb = Join-Path $DbDir "patch5_fullflow_one_iter_fused_event_candidates_synthetic.duckdb"
$damaged20k = Join-Path $SyntheticDir "patch5_20k_synthetic_damaged_edges.pq"
$damagedFull = Join-Path $SyntheticDir "patch5_fullflow_synthetic_damaged_edges.pq"
$reportPath = Join-Path $PatchDir "patch5_20k_fused_candidates_validation.json"

$runPatch4Reference = @"
& "$PythonPath" .\scripts\dev_create_synthetic_damaged_edges_patch4.py --source network --output '$damaged20k' --event-id '$ValidationEventId' --count $SyntheticEdgeCount
Remove-Item -LiteralPath '$patch4Out' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$patch4Out' | Out-Null
`$before = if (Test-Path '$patch4Db') { (Get-Item '$patch4Db').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'event_candidates'
`$env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = '1'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'skip'
`$env:NIRD_WRITE_FULL_ODPFC = '0'
`$env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = '1'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
`$env:NIRD_SAMPLE_OD_N = '20000'
`$env:NIRD_EVENT_DAMAGED_EDGES_PATH = '$damaged20k'
`$env:NIRD_BASELINE_DB_PATH = '$patch4Db'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$patch4Out'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$patch4Db') { (Get-Item '$patch4Db').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "Patch4 reference candidate part count: `$((Get-ChildItem '$patch4Out\event_disrupted_candidates\$ValidationEventId\parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

$runPatch5Fused = @"
while (-not (Test-Path '$patch4Out\event_disrupted_candidates\$ValidationEventId\parts')) {
  Write-Host 'Waiting for Patch5_20k_patch4_reference...'
  Start-Sleep -Seconds 10
}
Remove-Item -LiteralPath '$patch5Out' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$patch5Out' | Out-Null
`$before = if (Test-Path '$patch5Db') { (Get-Item '$patch5Db').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'event_candidates'
`$env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = '0'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'skip'
`$env:NIRD_WRITE_FULL_ODPFC = '0'
`$env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = '1'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
`$env:NIRD_SAMPLE_OD_N = '20000'
`$env:NIRD_EVENT_DAMAGED_EDGES_PATH = '$damaged20k'
`$env:NIRD_BASELINE_DB_PATH = '$patch5Db'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$patch5Out'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$patch5Db') { (Get-Item '$patch5Db').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "Patch5 fused candidate part count: `$((Get-ChildItem '$patch5Out\event_disrupted_candidates\$ValidationEventId\parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

$runValidate = @"
while (-not (Test-Path '$patch5Out\event_disrupted_candidates\$ValidationEventId\parts')) {
  Write-Host 'Waiting for Patch5_20k_fused_event_candidates...'
  Start-Sleep -Seconds 10
}
& "$PythonPath" .\scripts\dev_validate_patch5_fused_candidates.py --patch4-dir '$patch4Out' --patch5-dir '$patch5Out' --event-id '$ValidationEventId' --report-path '$reportPath'
"@

$runFull = @"
while (-not (Test-Path '$reportPath')) {
  Write-Host 'Waiting for Patch5_20k_validate_fused_candidates...'
  Start-Sleep -Seconds 15
}
& "$PythonPath" .\scripts\dev_create_synthetic_damaged_edges_patch4.py --source network --output '$damagedFull' --event-id '$FullFlowEventId' --count $SyntheticEdgeCount
Remove-Item -LiteralPath '$FullFlowOut' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$FullFlowOut' | Out-Null
`$before = if (Test-Path '$fullDb') { (Get-Item '$fullDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_RESULTS_VARIANT = '$Variant'
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'event_candidates'
`$env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = '0'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'skip'
`$env:NIRD_WRITE_FULL_ODPFC = '0'
`$env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = '0'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
Remove-Item Env:\NIRD_SAMPLE_OD_N -ErrorAction SilentlyContinue
`$env:NIRD_EVENT_DAMAGED_EDGES_PATH = '$damagedFull'
`$env:NIRD_BASELINE_DB_PATH = '$fullDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$FullFlowOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$fullDb') { (Get-Item '$fullDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "Full-flow fused event candidate part count: `$((Get-ChildItem '$FullFlowOut\event_disrupted_candidates\$FullFlowEventId\parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

New-Patch5Window `
    -Title "Patch5_20k_patch4_reference" `
    -LogPath (Join-Path $LogsDir "patch5_20k_patch4_reference.log") `
    -Command $runPatch4Reference

New-Patch5Window `
    -Title "Patch5_20k_fused_event_candidates" `
    -LogPath (Join-Path $LogsDir "patch5_20k_fused_event_candidates.log") `
    -Command $runPatch5Fused

New-Patch5Window `
    -Title "Patch5_20k_validate_fused_candidates" `
    -LogPath (Join-Path $LogsDir "patch5_20k_validate_fused_candidates.log") `
    -Command $runValidate

New-Patch5Window `
    -Title "Patch5_fullflow_one_iter_fused_event_candidates_synthetic" `
    -LogPath (Join-Path $LogsDir "patch5_fullflow_one_iter_fused_event_candidates_synthetic.log") `
    -Command $runFull

Write-Host "Launched Patch 5 windows in dependency order."
Write-Host "Logs: $LogsDir"
Write-Host "Patch outputs: $PatchDir"
Write-Host "Full-flow base scenario output: $FullFlowOut"
