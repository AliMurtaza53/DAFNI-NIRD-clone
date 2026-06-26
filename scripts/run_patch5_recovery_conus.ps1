param(
    [int]$DepthKey = 30,
    [int[]]$EventKeys = @(1, 2, 3),
    [int]$NumChunks = 20,
    [int]$NumCpu = 1,
    [int]$MaxFlowIterations = 2,
    [string]$ResultsVariant = "revision",
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [switch]$SmokeOnly,
    [switch]$SkipPassA,
    [switch]$SkipPassB,
    [switch]$SkipExport,
    [switch]$SkipScript2,
    [switch]$SkipScript3,
    [switch]$SkipScript4,
    [switch]$RunVizOdpfcSidecar,
    [int]$VizSampleStride = 1,
    [switch]$RunNotebook
)

$ErrorActionPreference = "Stop"

function Join-MultiPath {
    param([Parameter(Mandatory = $true)][string[]]$Parts)
    $result = $Parts[0]
    foreach ($part in $Parts[1..($Parts.Count - 1)]) {
        $result = Join-Path $result $part
    }
    return $result
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python not found at $Python. Set -Python to your nird env python.exe."
}

. (Join-Path $PSScriptRoot "lib\nird_geo_env.ps1") -Python $Python

$configPath = Join-Path $repoRoot "config.json"
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Missing config.json at $configPath"
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$basePath = $config.paths.soge_clusters
$resultsRoot = Join-Path (Split-Path -Parent $basePath) "results"
$faf5DataRoot = Join-Path (Split-Path -Parent $basePath) "faf5_data"
$damagedEdgesPath = Join-Path (Join-Path $basePath "tables") "event_damaged_edges_depth${DepthKey}_toy.pq"

if (Test-Path -LiteralPath $faf5DataRoot) {
    $env:NIRD_FAF5_DATA_ROOT = $faf5DataRoot
}

Remove-Item Env:NIRD_OD_MULTIPLIER -ErrorAction SilentlyContinue
Remove-Item Env:NIRD_OD_TARGET_TOTAL -ErrorAction SilentlyContinue

function Set-Patch5SharedEnv {
    $env:NIRD_RESULTS_VARIANT = $ResultsVariant
    $env:NIRD_PATH_REALIZATION_STRATEGY = "streaming_arrays"
    $env:NIRD_DIRECT_DUCKDB_OUTPUTS = "1"
    $env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = "0"
    $env:NIRD_ODPFC_OUTPUT_MODE = "skip"
    $env:NIRD_WRITE_FULL_ODPFC = "0"
    $env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = "0"
    $env:NIRD_ENABLE_SPLIT_CACHE = "1"
    $env:NIRD_VECTORIZE_PATH_PARSING = "1"
    $env:NIRD_MAX_FLOW_ITERATIONS = "$MaxFlowIterations"
    $env:NIRD_OD_ID_AT_INSERT = "1"
    $env:NIRD_POOL_MAX_TASKS_PER_CHILD = "50"
    $env:OMP_NUM_THREADS = "1"
    $env:MKL_NUM_THREADS = "1"
    $env:OPENBLAS_NUM_THREADS = "1"
    Remove-Item Env:NIRD_LCP_COLLECT_POOL_RESULTS -ErrorAction SilentlyContinue
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $safeName = $Name -replace "[^A-Za-z0-9_.-]", "_"
    $logPath = Join-Path $logDir "$timestamp`_$safeName.log"

    Write-Host ""
    Write-Host "==== $Name ===="
    Write-Host "$Python $($Arguments -join ' ')"
    Write-Host "Log: $logPath"

    $oldErrorActionPreference = $ErrorActionPreference
    $oldNativePreference = $null
    $hasNativePreference = Test-Path Variable:\PSNativeCommandUseErrorActionPreference
    if ($hasNativePreference) {
        $oldNativePreference = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }
    try {
        $ErrorActionPreference = "Continue"
        & $Python @Arguments *>&1 | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $oldNativePreference
        }
    }
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode. See $logPath"
    }
    return $logPath
}

function Test-Patch5LogGates {
    param([string]$LogPath)
    if (-not (Test-Path -LiteralPath $LogPath)) {
        Write-Warning "Patch 5 log not found: $LogPath"
        return $false
    }
    $text = Get-Content -LiteralPath $LogPath -Raw
    $checks = [ordered]@{
        streaming_strategy = ($text -match "path_strategy=streaming_arrays")
        event_candidates_mode = ($text -match "event_candidates")
        no_unnest_fallback = (-not ($text -match "UNNEST\(e_id\)"))
    }
    $ok = $true
    foreach ($key in $checks.Keys) {
        $status = if ($checks[$key]) { "PASS" } else { "FAIL" }
        if ($status -eq "FAIL") { $ok = $false }
        Write-Host "  Patch5 gate [$key]: $status"
    }
    return $ok
}

function Test-EventCandidateParts {
    param([string[]]$EventIds)
    $candidateRoot = Join-MultiPath @($resultsRoot, "base_scenario", $ResultsVariant, "event_disrupted_candidates")
    $allOk = $true
    foreach ($eventId in $EventIds) {
        $partsDir = Join-MultiPath @($candidateRoot, $eventId, "parts")
        $count = 0
        if (Test-Path -LiteralPath $partsDir) {
            $count = @(Get-ChildItem -LiteralPath $partsDir -Filter "*.pq" -ErrorAction SilentlyContinue).Count
        }
        $status = if ($count -gt 0) { "PASS ($count parts)" } else { "FAIL" }
        if ($count -le 0) { $allOk = $false }
        Write-Host "  Event candidates [$eventId]: $status"
    }
    return $allOk
}

function Get-BaseScenarioDir {
    return Join-MultiPath @($resultsRoot, "base_scenario", $ResultsVariant)
}

function Backup-PassAEdgeFlows {
    $baseDir = Get-BaseScenarioDir
    $edgeFlows = Join-Path $baseDir "edge_flows.gpq"
    $backup = Join-Path $baseDir "edge_flows_pass_a.gpq"
    if ((Test-Path -LiteralPath $edgeFlows) -and -not (Test-Path -LiteralPath $backup)) {
        Copy-Item -LiteralPath $edgeFlows -Destination $backup
        Write-Host "Backed up Pass A edge flows to $backup"
    }
    elseif (Test-Path -LiteralPath $backup) {
        Write-Host "Pass A edge-flow backup already present: $backup"
    }
}

function Clear-EventCandidateArtifacts {
    $candidateRoot = Join-MultiPath @((Get-BaseScenarioDir), "event_disrupted_candidates")
    if (Test-Path -LiteralPath $candidateRoot) {
        Write-Host "Removing stale event candidate artifacts: $candidateRoot"
        Remove-Item -LiteralPath $candidateRoot -Recurse -Force
    }
}

function Test-VizArtifacts {
    $baseDir = Get-BaseScenarioDir
    $figDir = Join-MultiPath @($resultsRoot, "figures", $ResultsVariant, "step1_base")
    $flowOk = Test-Path -LiteralPath (Join-Path $figDir "faf5_flow_validation.png")
    $sctgOk = Test-Path -LiteralPath (Join-Path $figDir "faf5_sctg_industry_breakdown.png")
    $odpfc = Join-Path $baseDir "odpfc.pq"
    Write-Host "  Viz flow validation: $(if ($flowOk) { 'PASS' } else { 'FAIL' })"
    Write-Host "  Viz SCTG breakdown:  $(if ($sctgOk) { 'PASS' } else { 'WARN (needs county/regional FAF)' })"
    Write-Host "  Viz odpfc artifact:  $(if (Test-Path -LiteralPath $odpfc) { 'PASS' } else { 'optional' }) -> $odpfc"
    return $flowOk
}

$eventIds = @($EventKeys | ForEach-Object { "${DepthKey}_$_" })

Write-Host "Patch 5 CONUS recovery workflow"
Write-Host "  Base path: $basePath"
Write-Host "  Results:   $resultsRoot"
Write-Host "  Variant:   $ResultsVariant"
Write-Host "  Depth:     $DepthKey"
Write-Host "  Events:    $($EventKeys -join ', ')"
Write-Host "  Max iters: $MaxFlowIterations"
if ($SmokeOnly) {
    Write-Host "  Mode:      smoke only (MaxFlowIterations=$MaxFlowIterations)"
}

Push-Location $repoRoot
try {
    Set-Patch5SharedEnv

    try {
        Invoke-Step "build_faf5_sctg_summary" @("scripts/build_faf5_sctg_summary.py")
    }
    catch {
        Write-Host "SCTG summary not built yet (county/regional FAF source missing). Flow diagnostics will still run."
    }

    $passALog = $null
    if (-not $SkipPassA) {
        Remove-Item Env:\NIRD_EVENT_DAMAGED_EDGES_PATH -ErrorAction SilentlyContinue
        Remove-Item Env:\NIRD_BASELINE_PATH_OUTPUT_MODE -ErrorAction SilentlyContinue
        $passALog = Invoke-Step "passA_script1_baseline" @(
            "scripts/1_network_flow_model_revision.py",
            "$NumChunks",
            "$NumCpu"
        )
        $edgeFlows = Join-MultiPath @($resultsRoot, "base_scenario", $ResultsVariant, "edge_flows.gpq")
        if (-not (Test-Path -LiteralPath $edgeFlows)) {
            throw "Pass A did not produce edge_flows.gpq at $edgeFlows"
        }
    }

    if (-not $SkipScript2) {
        foreach ($eventKey in $EventKeys) {
            Invoke-Step "script2_depth${DepthKey}_event${eventKey}" @(
                "scripts/2_intersection_analysis.py",
                "$DepthKey",
                "$eventKey"
            )
        }
    }

    if (-not $SkipExport) {
        $exportArgs = @(
            "scripts/export_event_damaged_edges.py",
            "--depth-key", "$DepthKey",
            "--event-keys"
        )
        foreach ($eventKey in $EventKeys) {
            $exportArgs += "$eventKey"
        }
        $exportArgs += @("--output", $damagedEdgesPath, "--results-variant", $ResultsVariant)
        Invoke-Step "export_event_damaged_edges" $exportArgs

        if (-not (Test-Path -LiteralPath $damagedEdgesPath)) {
            throw "Damaged-edge export failed: $damagedEdgesPath"
        }
    }

    if (-not $SkipScript3) {
        Invoke-Step "script3_damage_analysis" @("scripts/3_damage_analysis.py")
        Invoke-Step "script3_postprocess_damage" @("scripts/3_postprocess_damage.py")
    }

    $passBLog = $null
    if (-not $SkipPassB) {
        if ($SkipPassA) {
            Backup-PassAEdgeFlows
        }
        Clear-EventCandidateArtifacts
        $env:NIRD_BASELINE_PATH_OUTPUT_MODE = "event_candidates"
        $env:NIRD_EVENT_DAMAGED_EDGES_PATH = $damagedEdgesPath
        $passBLog = Invoke-Step "passB_script1_event_candidates" @(
            "scripts/1_network_flow_model_revision.py",
            "$NumChunks",
            "$NumCpu"
        )
    }

    if (-not $SkipScript4) {
        foreach ($eventKey in $EventKeys) {
            Invoke-Step "script4_depth${DepthKey}_event${eventKey}" @(
                "scripts/4_rerouting_and_recovery_scenario_loop.py",
                "$DepthKey",
                "$eventKey",
                "$NumChunks",
                "$NumCpu"
            )
        }
    }

    if ($RunVizOdpfcSidecar) {
        Remove-Item Env:\NIRD_EVENT_DAMAGED_EDGES_PATH -ErrorAction SilentlyContinue
        $env:NIRD_BASELINE_PATH_OUTPUT_MODE = "full_odpfc"
        $env:NIRD_ODPFC_OUTPUT_MODE = "iteration_parquet"
        $env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = "1"
        $env:NIRD_COMBINE_ODPFC_PARTS = "1"
        $env:NIRD_MAX_FLOW_ITERATIONS = "1"
        Invoke-Step "viz_sidecar_odpfc" @(
            "scripts/1_network_flow_model_revision.py",
            "$NumChunks",
            "$NumCpu",
            "$VizSampleStride"
        )
        $odpfcPath = Join-Path (Get-BaseScenarioDir) "odpfc.pq"
        if (-not (Test-Path -LiteralPath $odpfcPath)) {
            throw "Viz sidecar did not produce combined odpfc.pq at $odpfcPath"
        }
    }

    if ($RunNotebook) {
        $env:NIRD_RESULTS_ROOT = $resultsRoot
        $env:NIRD_INPUT_ROOT = $basePath
        $env:NIRD_RESULTS_VARIANT = $ResultsVariant
        $env:NIRD_DEPTH_KEY = "$DepthKey"
        $env:NIRD_STUDY_AREA_LABEL = "CONUS freight (toy VA hazards)"
        $env:NIRD_HAZARD_TYPE_LABEL = "Flood depth $DepthKey cm"
        Invoke-Step "faf5_flow_diagnostics" @(
            "scripts/visualizations/plot_faf5_flow_diagnostics.py"
        )
        Invoke-Step "pipeline_draft_figures" @(
            "scripts/visualizations/plot_pipeline_draft_figures.py"
        )
        $nbPath = Join-Path $repoRoot "scripts\visualizations\visualize_pipeline_results.ipynb"
        $nbconvert = Join-Path (Split-Path -Parent $Python) "Scripts\jupyter-nbconvert.exe"
        $nbconvertArgs = @("--to", "notebook", "--execute", $nbPath, "--output-dir", (Join-Path $repoRoot "scripts\visualizations"))
        if (Test-Path -LiteralPath $nbconvert) {
            & $nbconvert @nbconvertArgs
        } else {
            & jupyter nbconvert @nbconvertArgs
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Notebook execution failed with exit code $LASTEXITCODE"
        }
    }

    Write-Host ""
    Write-Host "==== Post-run validation ===="
    if ($passBLog) {
        Test-Patch5LogGates -LogPath $passBLog | Out-Null
        Test-EventCandidateParts -EventIds $eventIds | Out-Null
    }
    if ($RunNotebook -or $RunVizOdpfcSidecar) {
        Test-VizArtifacts | Out-Null
    }
    foreach ($eventKey in $EventKeys) {
        $costCsv = Join-MultiPath @($resultsRoot, "rerouting_analysis", $ResultsVariant, "$DepthKey", "$eventKey", "cost_matrix_by_scenario.csv")
        $status = if (Test-Path -LiteralPath $costCsv) { "PASS" } else { "FAIL" }
        Write-Host "  Script 4 output [event $eventKey]: $status -> $costCsv"
    }

    Write-Host ""
    Write-Host "Workflow completed successfully."
    if ($SmokeOnly -and $MaxFlowIterations -gt 0) {
        Write-Host "Smoke run finished. For production recovery curves rerun with:"
        Write-Host "  .\scripts\run_patch5_recovery_conus.ps1 -MaxFlowIterations 0 -SkipScript2 -SkipScript3"
    }
}
finally {
    Pop-Location
}
