param(
    [int]$DepthKey = 30,
    [int[]]$EventKeys = @(1, 2, 3),
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [string]$Python = "python",
    [int]$MaxFlowIterations = 0,
    [int]$ShortestPathDestBatch = 0,
    [int]$FlowDbBatchSize = 100000,
    [string]$BaselineDbPath = "",
    [switch]$RunAlternateScript2,
    [switch]$RunSensitivity,
    [switch]$RunSetup
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$eventArg = ($EventKeys -join ",")
$setupCommand = ""
if ($RunSetup) {
    $setupCommand = ".\scripts\setup_conus_freight_workflow.ps1 -InstallFreightOd -CopyToyHazards; "
}
$alternateArg = if ($RunAlternateScript2) { " -RunAlternateScript2" } else { "" }
$sensitivityArg = if ($RunSensitivity) { " -RunSensitivity" } else { "" }
$dbEnvCommand = if ($BaselineDbPath) { "`$env:NIRD_BASELINE_DB_PATH='$BaselineDbPath'; " } else { "" }
$command = "Set-Location `"$repoRoot`"; " +
    "`$env:NIRD_MAX_FLOW_ITERATIONS='$MaxFlowIterations'; " +
    "`$env:NIRD_SHORTEST_PATH_DEST_BATCH='$ShortestPathDestBatch'; " +
    "`$env:NIRD_FLOW_DB_BATCH_SIZE='$FlowDbBatchSize'; " +
    $dbEnvCommand +
    $setupCommand +
    ".\scripts\run_numbered_workflow.ps1 -DepthKey $DepthKey -EventKeys $eventArg -NumChunks $NumChunks -NumCpu $NumCpu -Python `"$Python`"$alternateArg$sensitivityArg"

Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $command)
Write-Host "Opened visible PowerShell workflow terminal."
Write-Host $command
