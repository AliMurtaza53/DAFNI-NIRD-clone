param(
    [string]$PythonPath = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$SyntheticEdgeCount = 50,
    [string]$SyntheticEventId = "50_1",
    [string]$Variant = "patch5_fused_event_candidates_smoke_iter2",
    [string]$RealDamagedEdgesPath = "",
    [string]$RealEventId = "real_event_placeholder",
    [string]$Script4CandidateRoot = "",
    [switch]$SkipIter2,
    [switch]$SkipRealEventPlaceholder,
    [switch]$SkipScript4Placeholder
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
$PatchDir = Join-Path $RepoRoot "experiments\patch5_fused_event_candidates"
$DbDir = Join-Path $PatchDir "dbs"
$SyntheticDir = Join-Path $PatchDir "synthetic"
$DataResults = "C:\Users\akothaw\Desktop\data\results"
$Iter2Out = Join-Path $DataResults "base_scenario\$Variant"
New-Item -ItemType Directory -Force -Path $LogsDir, $PatchDir, $DbDir, $SyntheticDir, $Iter2Out | Out-Null

if (-not (Test-Path $PythonPath)) {
    throw "Python not found at $PythonPath"
}

function New-Patch5SmokeWindow {
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

$iter2Db = Join-Path $DbDir "patch5_fullflow_two_iter_fused_event_candidates_synthetic.duckdb"
$damagedIter2 = Join-Path $SyntheticDir "patch5_fullflow_two_iter_synthetic_damaged_edges.pq"

$runIter2Smoke = @"
& "$PythonPath" .\scripts\dev_create_synthetic_damaged_edges_patch4.py --source network --output '$damagedIter2' --event-id '$SyntheticEventId' --count $SyntheticEdgeCount
Remove-Item -LiteralPath '$Iter2Out' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path '$Iter2Out' | Out-Null
`$before = if (Test-Path '$iter2Db') { (Get-Item '$iter2Db').Length } else { 0 }
Write-Host "DB before bytes: `$before"
`$env:NIRD_RESULTS_VARIANT = '$Variant'
`$env:NIRD_PATH_REALIZATION_STRATEGY = 'streaming_arrays'
`$env:NIRD_DIRECT_DUCKDB_OUTPUTS = '1'
`$env:NIRD_BASELINE_PATH_OUTPUT_MODE = 'event_candidates'
`$env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = '0'
`$env:NIRD_ODPFC_OUTPUT_MODE = 'skip'
`$env:NIRD_WRITE_FULL_ODPFC = '0'
`$env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = '0'
`$env:NIRD_MAX_FLOW_ITERATIONS = '2'
Remove-Item Env:\NIRD_SAMPLE_OD_N -ErrorAction SilentlyContinue
`$env:NIRD_EVENT_DAMAGED_EDGES_PATH = '$damagedIter2'
`$env:NIRD_BASELINE_DB_PATH = '$iter2Db'
`$env:NIRD_BASE_SCENARIO_OUT_DIR = '$Iter2Out'
& "$PythonPath" .\scripts\1_network_flow_model_revision.py $NumChunks $NumCpu
`$after = if (Test-Path '$iter2Db') { (Get-Item '$iter2Db').Length } else { 0 }
Write-Host "DB after bytes: `$after"
Write-Host "Two-iteration fused event candidate part count: `$((Get-ChildItem '$Iter2Out\event_disrupted_candidates\$SyntheticEventId\parts' -Filter '*.pq' -ErrorAction SilentlyContinue | Measure-Object).Count)"
"@

$runRealEventPlaceholder = @"
Write-Host 'Real-event Patch 5 smoke placeholder.'
Write-Host 'No real-event model run is launched by this placeholder unless -RealDamagedEdgesPath is provided and the command below is reviewed.'
Write-Host 'Expected bounded settings: streaming_arrays, event_candidates, no full odpfc, no full temp_flow_matrix.'
Write-Host 'RealDamagedEdgesPath: $RealDamagedEdgesPath'
Write-Host 'RealEventId: $RealEventId'
if ('$RealDamagedEdgesPath' -and (Test-Path '$RealDamagedEdgesPath')) {
  Write-Host 'Prepared command skeleton:'
  Write-Host 'python scripts\1_network_flow_model_revision.py $NumChunks $NumCpu'
  Write-Host 'Required env values:'
  Write-Host 'NIRD_EVENT_DAMAGED_EDGES_PATH=$RealDamagedEdgesPath'
  Write-Host 'NIRD_MAX_FLOW_ITERATIONS=1 or 2'
  Write-Host 'NIRD_BASELINE_PATH_OUTPUT_MODE=event_candidates'
} else {
  Write-Host 'Waiting on actual Script 2/3 damaged-edge parquet before this smoke is run.'
}
"@

$runScript4Placeholder = @"
Write-Host 'Script 4 event-candidate loader smoke placeholder.'
Write-Host 'No Script 4 recovery run is launched by this placeholder.'
Write-Host 'Candidate root: $Script4CandidateRoot'
if ('$Script4CandidateRoot' -and (Test-Path '$Script4CandidateRoot')) {
  Write-Host 'Prepared command skeleton:'
  Write-Host 'python scripts\4_rerouting_and_recovery_scenario_loop.py'
  Write-Host 'Expected input: event_disrupted_candidates/<event_id>/parts/*.pq under the candidate root.'
} else {
  Write-Host 'Waiting on a real Patch 5 event-candidate output root before this loader smoke is run.'
}
"@

if (-not $SkipIter2) {
    New-Patch5SmokeWindow `
        -Title "Patch5_fullflow_two_iter_fused_event_candidates_synthetic" `
        -LogPath (Join-Path $LogsDir "patch5_fullflow_two_iter_fused_event_candidates_synthetic.log") `
        -Command $runIter2Smoke
}

if (-not $SkipRealEventPlaceholder) {
    New-Patch5SmokeWindow `
        -Title "Patch5_real_event_smoke_placeholder" `
        -LogPath (Join-Path $LogsDir "patch5_real_event_smoke_placeholder.log") `
        -Command $runRealEventPlaceholder
}

if (-not $SkipScript4Placeholder) {
    New-Patch5SmokeWindow `
        -Title "Patch5_script4_event_candidate_loader_placeholder" `
        -LogPath (Join-Path $LogsDir "patch5_script4_event_candidate_loader_placeholder.log") `
        -Command $runScript4Placeholder
}

Write-Host "Launched Patch 5 smoke windows."
Write-Host "Logs: $LogsDir"
Write-Host "Two-iteration synthetic output: $Iter2Out"
Write-Host "No unrestricted production run was launched."
