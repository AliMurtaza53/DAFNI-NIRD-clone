param(
    [string]$PythonPath = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [int]$NumChunks = 20,
    [switch]$SkipRuns,
    [switch]$ValidationOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
$ResultsDir = Join-Path $RepoRoot "results\dev"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

if (-not (Test-Path $PythonPath)) {
    throw "Python not found at $PythonPath"
}

function New-RunWindow {
    param(
        [string]$Title,
        [string]$Command,
        [string]$LogPath
    )

    $windowCommand = @"
`$Host.UI.RawUI.WindowTitle = '$Title'
Set-Location '$RepoRoot'
`$env:PYTHONPATH = '$RepoRoot\src;$RepoRoot'
`$env:NIRD_DUCKDB_COMPACT_PATH_AGG = '1'
Remove-Item -LiteralPath '$LogPath' -Force -ErrorAction SilentlyContinue
Write-Host 'Starting: $Title'
Write-Host 'Log: $LogPath'
Write-Host 'Command: $Command'
$Command *>&1 | Tee-Object -FilePath '$LogPath'
Write-Host 'Finished: $Title'
"@
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $windowCommand
    )
}

$legacy1k = Join-Path $ResultsDir "path_realization_legacy_1k"
$streaming1k = Join-Path $ResultsDir "path_realization_streaming_1k"
$legacy20k = Join-Path $ResultsDir "path_realization_legacy_20k"
$streaming20k = Join-Path $ResultsDir "path_realization_streaming_20k"

if (-not $SkipRuns -and -not $ValidationOnly) {
    New-RunWindow `
        -Title "NIRD path realization legacy 1k" `
        -LogPath (Join-Path $LogsDir "path_realization_legacy_1k.log") `
        -Command "`"$PythonPath`" scripts/dev_compare_path_realization.py --strategy legacy_compact_sql --sample-n 1000 --num-chunks $NumChunks --out-dir `"$legacy1k`""

    New-RunWindow `
        -Title "NIRD path realization streaming 1k" `
        -LogPath (Join-Path $LogsDir "path_realization_streaming_1k.log") `
        -Command "`"$PythonPath`" scripts/dev_compare_path_realization.py --strategy streaming_arrays --sample-n 1000 --num-chunks $NumChunks --out-dir `"$streaming1k`""

    New-RunWindow `
        -Title "NIRD path realization legacy 20k" `
        -LogPath (Join-Path $LogsDir "path_realization_legacy_20k.log") `
        -Command "`"$PythonPath`" scripts/dev_compare_path_realization.py --strategy legacy_compact_sql --sample-n 20000 --num-chunks $NumChunks --out-dir `"$legacy20k`""

    New-RunWindow `
        -Title "NIRD path realization streaming 20k" `
        -LogPath (Join-Path $LogsDir "path_realization_streaming_20k.log") `
        -Command "`"$PythonPath`" scripts/dev_compare_path_realization.py --strategy streaming_arrays --sample-n 20000 --num-chunks $NumChunks --out-dir `"$streaming20k`""
}

$waitCommand = @"
`$paths = @(
  '$legacy1k\summary.json',
  '$streaming1k\summary.json',
  '$legacy20k\summary.json',
  '$streaming20k\summary.json'
)
while ((`$paths | Where-Object { -not (Test-Path `$_) }).Count -gt 0) {
  Write-Host "Waiting for sample runs to finish..."
  Start-Sleep -Seconds 15
}
& "$PythonPath" scripts/dev_compare_path_realization.py --compare --sample-n 1000 --legacy-dir "$legacy1k" --streaming-dir "$streaming1k" --report-dir "$ResultsDir"
& "$PythonPath" scripts/dev_compare_path_realization.py --compare --sample-n 20000 --legacy-dir "$legacy20k" --streaming-dir "$streaming20k" --report-dir "$ResultsDir"
"@

if (-not $SkipRuns -or $ValidationOnly) {
    New-RunWindow `
        -Title "NIRD path realization validation" `
        -LogPath (Join-Path $LogsDir "path_realization_validation.log") `
        -Command $waitCommand
}

Write-Host "Launched path-realization windows."
Write-Host "Logs: $LogsDir"
Write-Host "Results: $ResultsDir"
