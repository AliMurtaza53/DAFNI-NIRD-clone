param(
    [string]$RunLabel,
    [string]$StepDescription,
    [string]$ParsedJsonPath,
    [string]$LogDoc = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $LogDoc) {
    $LogDoc = Join-Path $repoRoot "docs\passb_parallel_optimization_log.md"
}
$data = Get-Content -LiteralPath $ParsedJsonPath -Raw | ConvertFrom-Json
$metaPath = Join-Path (Split-Path -Parent $ParsedJsonPath) "run_meta.json"
$meta = @{}
if (Test-Path -LiteralPath $metaPath) {
    $meta = Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json
}

function Get-Val($obj, $name) {
    if ($null -eq $obj.$name) { return "" }
    return $obj.$name
}

$row = @(
    $StepDescription,
    $RunLabel,
    (Get-Val $meta "num_cpu"),
    (Get-Val $meta "patch6_od_id_at_insert"),
    (Get-Val $meta "lcp_collect_pool_results"),
    (Get-Val $meta "pool_max_tasks_per_child"),
    (Get-Val $meta "wall_clock_sec"),
    (Get-Val $data "lcp_pool_sec"),
    (Get-Val $data "lcp_db_insert_sec"),
    (Get-Val $data "od_id_assign_sec"),
    (Get-Val $data "streaming_pass1_sec"),
    (Get-Val $data "streaming_pass2_sec"),
    "see $ParsedJsonPath"
) -join " | "

Add-Content -LiteralPath $LogDoc -Value "| $row |" -Encoding utf8
Write-Host "Appended timing row for $RunLabel to $LogDoc"
