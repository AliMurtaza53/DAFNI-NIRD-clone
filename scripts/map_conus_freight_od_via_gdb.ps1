param(
    [string]$BasePath = "",
    [string]$GdbPath = "",
    [string]$CentroidsPath = "",
    [int]$Year = 2022,
    [string]$Python = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe",
    [switch]$ExportOnly,
    [switch]$RequireGdb
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    . (Join-Path $PSScriptRoot "lib\nird_geo_env.ps1") -Python $Python

    if (-not $BasePath) {
        $config = Get-Content -LiteralPath (Join-Path $repoRoot "config.json") -Raw | ConvertFrom-Json
        $BasePath = $config.paths.soge_clusters
    }
    $faf5Root = Join-Path (Split-Path -Parent $BasePath) "faf5_data"
    $env:NIRD_FAF5_DATA_ROOT = $faf5Root

    if (-not $GdbPath) {
        $GdbPath = Join-Path $faf5Root "network_data\FAF5Network.gdb"
    }
    if (-not $CentroidsPath) {
        $CentroidsPath = Join-Path $faf5Root "processed\faf5_network_loading_centroids.gpq"
    }

    $exportArgs = @(
        "scripts/export_faf5_network_centroids.py",
        "--gdb", $GdbPath,
        "--output", $CentroidsPath
    )
    & $Python @exportArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Centroid export failed. Ensure the full FAF5Network.gdb is installed."
    }

    if ($ExportOnly) {
        Write-Host "Exported loading centroids to $CentroidsPath"
        return
    }

    $buildArgs = @(
        "scripts/build_conus_freight_od.py",
        "--year", "$Year",
        "--skip-county",
        "--force-centroid",
        "--network-centroids", $CentroidsPath
    )
    if ($RequireGdb) {
        $buildArgs += "--require-gdb"
    }
    & $Python @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "GDB-based freight OD mapping failed."
    }
    Write-Host "GDB-based mapping completed."
}
finally {
    Pop-Location
}
