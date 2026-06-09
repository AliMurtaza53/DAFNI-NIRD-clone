param(
    [string]$PythonPath = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$SyntheticEdgeCount = 50,
    [string]$ValidationEventId = "synthetic_20k",
    [string]$FullFlowEventId = "50_1",
    [string]$Variant = "patch4_event_candidates_smoke"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
$PatchDir = Join-Path $RepoRoot "experiments\patch4_event_candidates"
$ResultsDir = Join-Path $PatchDir "outputs"
$DbDir = Join-Path $PatchDir "dbs"
$SyntheticDir = Join-Path $PatchDir "synthetic"
$DataResults = "C:\Users\akothaw\Desktop\data\results"
$FullFlowOut = Join-Path $DataResults "base_scenario\$Variant"
New-Item -ItemType Directory -Force -Path $LogsDir, $ResultsDir, $DbDir, $SyntheticDir, $FullFlowOut | Out-Null

if (-not (Test-Path $PythonPath)) {
    throw "Python not found at $PythonPath"
}

function New-Patch4Window {
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

$legacyOut = Join-Path $ResultsDir "patch4_20k_legacy_candidate_reference"
$eventOut = Join-Path $ResultsDir "patch4_20k_event_candidates"
$legacyDb = Join-Path $DbDir "patch4_20k_legacy_candidate_reference.duckdb"
$eventDb = Join-Path $DbDir "patch4_20k_event_candidates.duckdb"
$fullDb = Join-Path $DbDir "patch4_fullflow_one_iter_event_candidates_synthetic.duckdb"
$damaged20k = Join-Path $SyntheticDir "patch4_20k_synthetic_damaged_edges.pq"
$damagedFull = Join-Path $SyntheticDir "patch4_fullflow_synthetic_damaged_edges.pq"
$reportPath = Join-Path $PatchDir "patch4_20k_event_candidates_validation.json"

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

$runEvent = @"
while (-not (Test-Path '$legacyOut\odpfc.pq')) {
  Write-Host 'Waiting for Patch4_20k_legacy_candidate_reference...'
  Start-Sleep -Seconds 10
}
& "$PythonPath" .\scripts\dev_create_synthetic_damaged_edges_patch4.py --source legacy --legacy-odpfc '$legacyOut\odpfc.pq' --output '$damaged20k' --event-id '$ValidationEventId' --count $SyntheticEdgeCount
Remove-Item -LiteralPath '$eventOut' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$eventOut' | Out-Null
`$before = if (Test-Path '$eventDb') { (Get-Item '$eventDb').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'event_candidates'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'skip'
`$env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = '1'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
`$env:NIRD_SAMPLE_OD_N = '20000'
`$env:NIRD_EVENT_DAMAGED_EDGES_PATH = '$damaged20k'
`$env:NIRD_BASELINE_DB_PATH = '$eventDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$eventOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$eventDb') { (Get-Item '$eventDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "Event candidate part count: `$((Get-ChildItem '$eventOut\event_disrupted_candidates\$ValidationEventId\parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

$runValidate = @"
while (-not (Test-Path '$eventOut\event_disrupted_candidates\$ValidationEventId\parts')) {
  Write-Host 'Waiting for Patch4_20k_event_candidates...'
  Start-Sleep -Seconds 10
}
& "$PythonPath" .\scripts\dev_validate_event_candidates_patch4.py --legacy-dir '$legacyOut' --event-dir '$eventOut' --damaged-edges-path '$damaged20k' --event-id '$ValidationEventId' --report-path '$reportPath'
"@

$runFull = @"
while (-not (Test-Path '$reportPath')) {
  Write-Host 'Waiting for Patch4_20k_validate_event_candidates...'
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
`$env:NIRD_ODPFC_OUTPUT_MODE = 'skip'
`$env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = '0'
`$env:NIRD_MAX_FLOW_ITERATIONS = '1'
Remove-Item Env:\NIRD_SAMPLE_OD_N -ErrorAction SilentlyContinue
`$env:NIRD_EVENT_DAMAGED_EDGES_PATH = '$damagedFull'
`$env:NIRD_BASELINE_DB_PATH = '$fullDb'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$FullFlowOut'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$fullDb') { (Get-Item '$fullDb').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "Full-flow event candidate part count: `$((Get-ChildItem '$FullFlowOut\event_disrupted_candidates\$FullFlowEventId\parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

New-Patch4Window `
    -Title "Patch4_20k_legacy_candidate_reference" `
    -LogPath (Join-Path $LogsDir "patch4_20k_legacy_candidate_reference.log") `
    -Command $runLegacy

New-Patch4Window `
    -Title "Patch4_20k_event_candidates" `
    -LogPath (Join-Path $LogsDir "patch4_20k_event_candidates.log") `
    -Command $runEvent

New-Patch4Window `
    -Title "Patch4_20k_validate_event_candidates" `
    -LogPath (Join-Path $LogsDir "patch4_20k_validate_event_candidates.log") `
    -Command $runValidate

New-Patch4Window `
    -Title "Patch4_fullflow_one_iter_event_candidates_synthetic" `
    -LogPath (Join-Path $LogsDir "patch4_fullflow_one_iter_event_candidates_synthetic.log") `
    -Command $runFull

Write-Host "Launched Patch 4 windows in dependency order."
Write-Host "Logs: $LogsDir"
Write-Host "Patch outputs: $PatchDir"
Write-Host "Full-flow base scenario output: $FullFlowOut"
