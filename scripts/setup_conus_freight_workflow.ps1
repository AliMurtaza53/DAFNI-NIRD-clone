param(
    [string]$BasePath = "C:\Users\alimu\NIRD_Data\soge_clusters",
    [string]$FreightOdPath = "data\processed\faf5_bts_conus_assignment_od.pq",
    [string]$ToyHazardSource = "C:\Users\alimu\NIRD_Data\va_soge_clusters_toy\inputs\test_141node_50m",
    [switch]$InstallFreightOd,
    [switch]$CopyToyHazards
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $base = [IO.Path]::GetFullPath($BasePath)
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
