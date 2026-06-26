param(
    [string]$RunLabel = "baseline",
    [int]$NumCpu = 1,
    [int]$NumChunks = 20,
    [int]$MaxFlowIterations = 1,
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [string]$ResultsRoot = "",
    [switch]$SkipRun
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    . (Join-Path $PSScriptRoot "lib\nird_geo_env.ps1") -Python $Python

    $config = Get-Content -LiteralPath (Join-Path $repoRoot "config.json") -Raw | ConvertFrom-Json
    $basePath = $config.paths.soge_clusters
    if (-not $ResultsRoot) {
        $ResultsRoot = Join-Path (Split-Path -Parent $basePath) "results"
    }
    $damagedEdges = Join-Path $basePath "tables\event_damaged_edges_depth30_toy.pq"
    $benchmarkRoot = Join-Path $repoRoot "experiments\passb_timing"
    $runDir = Join-Path $benchmarkRoot $RunLabel
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null

    $env:NIRD_RESULTS_VARIANT = "revision"
    $env:NIRD_PATH_REALIZATION_STRATEGY = "streaming_arrays"
    $env:NIRD_DIRECT_DUCKDB_OUTPUTS = "1"
    $env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = "0"
    $env:NIRD_ODPFC_OUTPUT_MODE = "skip"
    $env:NIRD_WRITE_FULL_ODPFC = "0"
    $env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = "0"
    $env:NIRD_BASELINE_PATH_OUTPUT_MODE = "event_candidates"
    $env:NIRD_EVENT_DAMAGED_EDGES_PATH = $damagedEdges
    $env:NIRD_MAX_FLOW_ITERATIONS = "$MaxFlowIterations"
    $env:NIRD_BASELINE_DB_PATH = Join-Path $runDir "baseline.duckdb"
    $env:NIRD_BASE_SCENARIO_OUT_DIR = Join-Path $runDir "base_scenario_outputs"
    $env:OMP_NUM_THREADS = "1"
    $env:MKL_NUM_THREADS = "1"
    $env:OPENBLAS_NUM_THREADS = "1"

    $meta = [ordered]@{
        run_label = $RunLabel
        num_cpu = $NumCpu
        num_chunks = $NumChunks
        max_flow_iterations = $MaxFlowIterations
        patch6_od_id_at_insert = $env:NIRD_OD_ID_AT_INSERT
        lcp_collect_pool_results = $env:NIRD_LCP_COLLECT_POOL_RESULTS
        pool_max_tasks_per_child = $env:NIRD_POOL_MAX_TASKS_PER_CHILD
        omp_num_threads = $env:OMP_NUM_THREADS
        started_at = (Get-Date).ToString("o")
    }
    $metaPath = Join-Path $runDir "run_meta.json"
    $meta | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metaPath -Encoding utf8

    $logPath = Join-Path $runDir "passb_script1.log"
    if (-not $SkipRun) {
        $candidateRoot = Join-Path $ResultsRoot "base_scenario\revision\event_disrupted_candidates"
        if (Test-Path $candidateRoot) {
            Remove-Item -LiteralPath $candidateRoot -Recurse -Force
        }
        if (Test-Path -LiteralPath $logPath) {
            Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
        }
        Write-Host "==== Pass B benchmark: $RunLabel (NumCpu=$NumCpu, MaxFlowIterations=$MaxFlowIterations) ===="
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $oldErrorActionPreference = $ErrorActionPreference
        $oldNativePreference = $null
        $hasNativePreference = Test-Path Variable:\PSNativeCommandUseErrorActionPreference
        if ($hasNativePreference) {
            $oldNativePreference = $PSNativeCommandUseErrorActionPreference
            $PSNativeCommandUseErrorActionPreference = $false
        }
        try {
            $ErrorActionPreference = "Continue"
            & $Python scripts/1_network_flow_model_revision.py $NumChunks $NumCpu *>&1 | Tee-Object -FilePath $logPath
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $oldErrorActionPreference
            if ($hasNativePreference) {
                $PSNativeCommandUseErrorActionPreference = $oldNativePreference
            }
        }
        if ($exitCode -ne 0) {
            throw "Pass B benchmark failed with exit code $exitCode"
        }
        $sw.Stop()
        $meta.completed_at = (Get-Date).ToString("o")
        $meta.wall_clock_sec = [math]::Round($sw.Elapsed.TotalSeconds, 2)
        $meta | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metaPath -Encoding utf8
    }

    $jsonOut = Join-Path $runDir "parsed_timing.json"
    & $Python scripts/parse_passb_timing.py $logPath --json-out $jsonOut
    Write-Host "Wrote $jsonOut"
}
finally {
    Pop-Location
}
