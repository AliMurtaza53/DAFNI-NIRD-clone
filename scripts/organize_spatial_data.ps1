$repo = "C:\Users\alimu\Desktop\Github\DAFNI-NIRD-clone"
$srcRoot = Join-Path $repo "sandbox\shapefiles"
$destRoot = Join-Path $repo "spatial_data"

$adminRaw = Join-Path $destRoot "dmv_admin\tiger_2025\raw_zips"
$adminExt = Join-Path $destRoot "dmv_admin\tiger_2025\extracted"
$tazRaw = Join-Path $destRoot "dmv_taz\raw_zips"
$tazExt = Join-Path $destRoot "dmv_taz\extracted"
$fafRaw = Join-Path $destRoot "faf_county_experimental\raw_zips"
$fafExt = Join-Path $destRoot "faf_county_experimental\extracted_by_state"
$fafReadme = Join-Path $destRoot "faf_county_experimental\README_experimental.md"

New-Item -ItemType Directory -Force -Path $adminRaw, $adminExt, $tazRaw, $tazExt, $fafRaw, $fafExt | Out-Null

# Move top-level ZIPs
$topLevelZips = Get-ChildItem -Path $srcRoot -File -Filter *.zip -ErrorAction SilentlyContinue
foreach ($z in $topLevelZips) {
    if ($z.Name -like "TAZ*" -or $z.Name -like "*COG*") {
        Move-Item -Path $z.FullName -Destination (Join-Path $tazRaw $z.Name) -Force
    }
    else {
        Move-Item -Path $z.FullName -Destination (Join-Path $adminRaw $z.Name) -Force
    }
}

# Move county FAF ZIPs
$countySrc = Join-Path $srcRoot "county faf flows"
if (Test-Path $countySrc) {
    $countyZips = Get-ChildItem -Path $countySrc -File -Filter *.zip -ErrorAction SilentlyContinue
    foreach ($z in $countyZips) {
        Move-Item -Path $z.FullName -Destination (Join-Path $fafRaw $z.Name) -Force
    }
}

# Extract admin ZIPs
$adminZips = Get-ChildItem -Path $adminRaw -File -Filter *.zip -ErrorAction SilentlyContinue
foreach ($z in $adminZips) {
    $folder = [System.IO.Path]::GetFileNameWithoutExtension($z.Name)
    $target = Join-Path $adminExt $folder
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Expand-Archive -Path $z.FullName -DestinationPath $target -Force
}

# Extract TAZ ZIPs
$tazZips = Get-ChildItem -Path $tazRaw -File -Filter *.zip -ErrorAction SilentlyContinue
foreach ($z in $tazZips) {
    $folder = [System.IO.Path]::GetFileNameWithoutExtension($z.Name)
    $target = Join-Path $tazExt $folder
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Expand-Archive -Path $z.FullName -DestinationPath $target -Force
}

# Extract FAF ZIPs
$fafZips = Get-ChildItem -Path $fafRaw -File -Filter *.zip -ErrorAction SilentlyContinue
foreach ($z in $fafZips) {
    $folder = [System.IO.Path]::GetFileNameWithoutExtension($z.Name)
    $target = Join-Path $fafExt $folder
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Expand-Archive -Path $z.FullName -DestinationPath $target -Force
}

# Experimental note
$noteLines = @(
    "# FAF County Flow Data (Experimental)",
    "",
    "This folder contains experimental county-level FAF flow extracts for DMV core states and nearby neighbors.",
    "",
    "States currently staged:",
    "- 10 Delaware",
    "- 11 District of Columbia",
    "- 21 Kentucky",
    "- 24 Maryland",
    "- 34 New Jersey",
    "- 37 North Carolina",
    "- 42 Pennsylvania",
    "- 51 Virginia",
    "- 54 West Virginia",
    "",
    "## Status",
    "- These files are staged for later processing.",
    "- Treat as exploratory/intermediate data until validation is complete.",
    "",
    "## Source references",
    "- https://www.bts.gov/faf/county",
    "- https://www.bts.gov/faf/county/documentation",
    "",
    "## Notes for later work",
    "- Confirm FAF county schema/version and year consistency.",
    "- Validate county FIPS mapping and directional flow fields.",
    "- Build a harmonized DMV-neighbor county flow subset for model inputs."
)
Set-Content -Path $fafReadme -Value $noteLines -Encoding UTF8

# Remove now-empty county source folder
if (Test-Path $countySrc) {
    Remove-Item -Path $countySrc -Force -Recurse
}

Write-Host "Organization complete."
Write-Host "Destination: $destRoot"
Write-Host "\nRemaining in source folder:"
Get-ChildItem -Path $srcRoot -Force | Select-Object Name, FullName, PSIsContainer | Format-Table -AutoSize

Write-Host "\nTop-level destination folders:"
Get-ChildItem -Path $destRoot -Force | Select-Object Name, FullName, PSIsContainer | Format-Table -AutoSize
