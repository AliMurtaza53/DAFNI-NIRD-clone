param(
    [string]$BasePath = "C:\Users\alimu\NIRD_Data\soge_clusters",
    [string]$FreightOdPath = "data\processed\faf5_bts_conus_assignment_od.pq",
    [string]$Faf5DataRoot = "",
    [string]$CountyOdPath = "",
    [string]$RegionalFafPath = "",
    [string]$ToyHazardSource = "C:\Users\alimu\NIRD_Data\va_soge_clusters_toy\inputs\test_141node_50m",
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [switch]$InstallFreightOd,
    [switch]$InstallCountyOd,
    [switch]$CopyToyHazards,
    [switch]$BuildSctgSummary,
    [switch]$BuildCountyOdFromFaf5
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $base = [IO.Path]::GetFullPath($BasePath)
    if ($Faf5DataRoot) {
        $faf5Root = [IO.Path]::GetFullPath($Faf5DataRoot)
    } else {
        $faf5Root = Join-Path (Split-Path -Parent $base) "faf5_data"
    }
    if (Test-Path -LiteralPath $faf5Root) {
        $env:NIRD_FAF5_DATA_ROOT = $faf5Root
        New-Item -ItemType Directory -Force -Path (Join-Path $faf5Root "processed") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $faf5Root "regional_od_data") | Out-Null
    }
    $requiredDirs = @(
        "asset_costs",
        "census_datasets",
        "damage_curves",
        "dbs",
        "hazards\completed",
        "inputs\test_141node_50m",
        "networks\faf5",
        "parameters",
        "tables"
    )
    foreach ($dir in $requiredDirs) {
        New-Item -ItemType Directory -Force -Path (Join-Path $base $dir) | Out-Null
    }

    $installedOd = $false
    $odDest = Join-Path $base "census_datasets\faf5_od_matrix.pq"
    if ($InstallFreightOd) {
        if (-not (Test-Path -LiteralPath $FreightOdPath)) {
            throw "Freight OD not found: $FreightOdPath"
        }
        if (Test-Path -LiteralPath $odDest) {
            $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
            Copy-Item -LiteralPath $odDest -Destination (Join-Path $base "census_datasets\faf5_od_matrix_backup_$stamp.pq") -Force
        }
        Copy-Item -LiteralPath $FreightOdPath -Destination $odDest -Force
        $installedOd = $true
    }

    $installedCountyOd = $false
    $countyOdDest = Join-Path $base "census_datasets\faf5_county_od.pq"
    if ($InstallCountyOd) {
        $countySource = $CountyOdPath
        if (-not $countySource) {
            $countySource = Join-Path $faf5Root "processed\faf5_county_truck_od_usa_2022_detail.parquet"
        }
        if (-not (Test-Path -LiteralPath $countySource)) {
            throw "County OD not found: $countySource"
        }
        Copy-Item -LiteralPath $countySource -Destination $countyOdDest -Force
        $installedCountyOd = $true
    }

    $builtCountyOd = $false
    $builtAssignmentOd = $false
    if ($BuildCountyOdFromFaf5) {
        if (-not (Test-Path -LiteralPath $Python)) {
            $Python = "python"
        }
        & $Python @("scripts/build_conus_freight_od.py", "--year", "2022")
        if ($LASTEXITCODE -ne 0) {
            throw "CONUS county OD / assignment build failed."
        }
        $builtCountyOd = $true
        $builtAssignmentOd = $true
        $installedCountyOd = $true
        $installedOd = $true
    }

    $sctgSummaryPath = Join-Path $base "census_datasets\faf5_sctg_daily_trucks.pq"
    $builtSctg = $false
    if ($BuildSctgSummary -or $installedCountyOd) {
        if (-not (Test-Path -LiteralPath $Python)) {
            $Python = "python"
        }
        if ($RegionalFafPath -and (Test-Path -LiteralPath $RegionalFafPath)) {
            $env:NIRD_FAF_REGIONAL_OD_PATH = $RegionalFafPath
        } elseif (Test-Path -LiteralPath (Join-Path $faf5Root "regional_od_data\FAF5.7.1_2018-2024.csv")) {
            $env:NIRD_FAF_REGIONAL_OD_PATH = Join-Path $faf5Root "regional_od_data\FAF5.7.1_2018-2024.csv"
        }
        $buildArgs = @("scripts/build_faf5_sctg_summary.py", "--year", "2022")
        if ($InstallCountyOd) {
            $buildArgs += @("--county-od-path", $countyOdDest)
        }
        & $Python @buildArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Host "SCTG summary build skipped or failed (county/regional FAF source may be missing)."
        } else {
            $builtSctg = Test-Path -LiteralPath $sctgSummaryPath
        }
    }

    $copiedHazards = @()
    if ($CopyToyHazards) {
        if (-not (Test-Path -LiteralPath $ToyHazardSource)) {
            throw "Toy hazard source not found: $ToyHazardSource"
        }
        $hazardDest = Join-Path $base "inputs\test_141node_50m"
        foreach ($file in @(
            "va_hazard_class50_141node_base.tif",
            "va_hazard_class50_141node_low.tif",
            "va_hazard_class50_141node_high.tif",
            "va_hazard_class50_141node.tif"
        )) {
            $src = Join-Path $ToyHazardSource $file
            if (Test-Path -LiteralPath $src) {
                Copy-Item -LiteralPath $src -Destination (Join-Path $hazardDest $file) -Force
                $copiedHazards += (Join-Path $hazardDest $file)
            }
        }
    }

    $requiredFiles = @(
        "census_datasets\faf5_od_matrix.pq",
        "networks\faf5\faf5_road_links.gpq",
        "networks\faf5\faf5_road_nodes.gpq",
        "parameters\flow_breakpoint_dict.json",
        "parameters\flow_cap_plph_dict.json",
        "parameters\free_flow_speed_dict.json",
        "parameters\min_speed_cap.json",
        "parameters\urban_speed_cap.json"
    )
    $missing = @()
    foreach ($file in $requiredFiles) {
        $path = Join-Path $base $file
        if (-not (Test-Path -LiteralPath $path)) {
            $missing += $path
        }
    }
    if ($missing.Count -gt 0) {
        throw "Missing required workflow files:`n$($missing -join "`n")"
    }

    $manifest = [ordered]@{
        created_at = (Get-Date).ToString("s")
        base_path = $base
        installed_freight_od = $installedOd
        freight_od_source = $FreightOdPath
        freight_od_destination = $odDest
        installed_county_od = $installedCountyOd
        county_od_source = if ($InstallCountyOd) { if ($CountyOdPath) { $CountyOdPath } else { $countySource } } else { $null }
        county_od_destination = $countyOdDest
        faf5_data_root = $faf5Root
        built_sctg_summary = $builtSctg
        built_county_od_from_faf5 = $builtCountyOd
        built_assignment_od_from_faf5 = $builtAssignmentOd
        sctg_summary_path = $sctgSummaryPath
        copied_toy_hazards = $copiedHazards
        required_files_checked = $requiredFiles
    }
    $manifestPath = Join-Path $base "tables\conus_freight_workflow_manifest.json"
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    Write-Host "CONUS freight workflow inputs are organized."
    Write-Host "Base path: $base"
    Write-Host "Manifest: $manifestPath"
}
finally {
    Pop-Location
}
