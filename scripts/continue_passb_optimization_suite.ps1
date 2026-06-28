param(
    [string]$BaselineLabel = "step0_baseline",
    [int]$PollSeconds = 120
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$metaPath = Join-Path $repoRoot "experiments\passb_timing\$BaselineLabel\run_meta.json"

Write-Host "Waiting for $BaselineLabel to finish (poll every ${PollSeconds}s)..."
while ($true) {
    if (Test-Path -LiteralPath $metaPath) {
        $meta = Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json
        if ($meta.completed_at -and ($meta.wall_clock_sec -gt 0)) {
            Write-Host "$BaselineLabel complete: wall=$($meta.wall_clock_sec)s"
            break
        }
    }
    Start-Sleep -Seconds $PollSeconds
}

$parsed = Join-Path $repoRoot "experiments\passb_timing\$BaselineLabel\parsed_timing.json"
if (-not (Test-Path -LiteralPath $parsed)) {
    $logPath = Join-Path $repoRoot "experiments\passb_timing\$BaselineLabel\passb_script1.log"
    $python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe"
    & $python (Join-Path $repoRoot "scripts\parse_passb_timing.py") $logPath --json-out $parsed
}

& (Join-Path $PSScriptRoot "append_passb_timing_row.ps1") `
    -RunLabel $BaselineLabel `
    -StepDescription $BaselineLabel `
    -ParsedJsonPath $parsed

& (Join-Path $PSScriptRoot "run_passb_optimization_suite.ps1") -SkipBaseline
