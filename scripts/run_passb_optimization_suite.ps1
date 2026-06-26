param(
    [switch]$BaselineOnly,
    [switch]$SkipBaseline,
    [switch]$SkipLcpCollect
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

function Test-StepComplete {
    param([string]$Label)
    $metaPath = Join-Path $repoRoot "experiments\passb_timing\$Label\run_meta.json"
    if (-not (Test-Path -LiteralPath $metaPath)) { return $false }
    $meta = Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json
    return ($null -ne $meta.completed_at) -and ($meta.wall_clock_sec -gt 0)
}

function Get-ProductionEnvOverrides {
    return @{
        NIRD_OD_ID_AT_INSERT = "1"
        NIRD_POOL_MAX_TASKS_PER_CHILD = "50"
    }
}

function Run-Step {
    param(
        [string]$Label,
        [hashtable]$EnvOverrides = @{},
        [int]$NumCpu = 1,
        [switch]$Force
    )
    if ((-not $Force) -and (Test-StepComplete -Label $Label)) {
        Write-Host "Skipping $Label (already complete; use -Force to rerun)"
        return
    }
    Remove-Item Env:NIRD_LCP_COLLECT_POOL_RESULTS -ErrorAction SilentlyContinue
    foreach ($key in $EnvOverrides.Keys) {
        Set-Item -Path "Env:$key" -Value $EnvOverrides[$key]
    }
    Write-Host ""
    Write-Host "========== $Label =========="
    & (Join-Path $PSScriptRoot "benchmark_passb_timing.ps1") -RunLabel $Label -NumCpu $NumCpu
    $parsed = Join-Path $repoRoot "experiments\passb_timing\$Label\parsed_timing.json"
    & (Join-Path $PSScriptRoot "append_passb_timing_row.ps1") `
        -RunLabel $Label `
        -StepDescription $Label `
        -ParsedJsonPath $parsed
}

try {
    Remove-Item Env:NIRD_OD_ID_AT_INSERT -ErrorAction SilentlyContinue
    Remove-Item Env:NIRD_LCP_COLLECT_POOL_RESULTS -ErrorAction SilentlyContinue
    Remove-Item Env:NIRD_POOL_MAX_TASKS_PER_CHILD -ErrorAction SilentlyContinue
    $env:OMP_NUM_THREADS = "1"
    $env:MKL_NUM_THREADS = "1"
    $env:OPENBLAS_NUM_THREADS = "1"

    if (-not $SkipBaseline) {
        Run-Step -Label "step0_baseline" -NumCpu 1
    }
    if ($BaselineOnly) { return }

    Run-Step -Label "step1_patch6_od_id" -NumCpu 1 -EnvOverrides @{
        NIRD_OD_ID_AT_INSERT = "1"
    }

    if (-not $SkipLcpCollect) {
        Run-Step -Label "step2_lcp_collect" -NumCpu 1 -EnvOverrides @{
            NIRD_OD_ID_AT_INSERT = "1"
            NIRD_LCP_COLLECT_POOL_RESULTS = "1"
        }
    } else {
        Write-Host "Skipping step2_lcp_collect (documented MemoryError at CONUS scale; profiling-only flag)"
    }

    Run-Step -Label "step3_pool_recycle" -NumCpu 1 -EnvOverrides (Get-ProductionEnvOverrides)

    foreach ($cpu in @(1, 2, 4, 8)) {
        Run-Step -Label "step4_numcpu_$cpu" -NumCpu $cpu -EnvOverrides (Get-ProductionEnvOverrides)
    }
}
finally {
    Pop-Location
}
