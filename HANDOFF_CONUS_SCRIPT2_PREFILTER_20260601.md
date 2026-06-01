# CONUS Freight Script 2 Handoff - 2026-06-01

This note captures the current repo state for moving work to another PC.

## Current Folder

Working folder on this machine:

```text
C:\Users\akothaw\Desktop\DAFNI-NIRD-clone
```

Active data bundle configured in `config.json`:

```text
C:\Users\akothaw\Desktop\conus_freight_handoff_20260528_190923\soge_clusters
```

Script outputs are expected under the data bundle parent:

```text
C:\Users\akothaw\Desktop\conus_freight_handoff_20260528_190923\results
```

## Script 1 Status

Script 1 has produced base scenario outputs here:

```text
C:\Users\akothaw\Desktop\conus_freight_handoff_20260528_190923\results\base_scenario\revision
```

Observed files:

- `edge_flows.gpq`
- `trip_isolations.pq`
- `odpfc.pq`

Important nuance: the completed base output uses the FAF5 network, with about
483,442 road links in `edge_flows.gpq`. It is not the small 4,541-row Fairfax
profile case.

## Script 2 Issue

The temporary CONUS run uses local VA toy hazard rasters:

```text
soge_clusters\inputs\test_141node_50m\va_hazard_class50_141node_*.tif
```

No toy study-area clip file exists in the data bundle. Before this handoff,
Script 2 fell back to the broad USA analysis boundary and attempted to pass the
full 483k-link FAF5 network into the raster intersection workflow. That is too
slow for the local hazard test.

## Code Changes Made

### `scripts/2_intersection_analysis.py`

Added raster-extent prefiltering before the expensive `snail.intersection`
line-splitting path.

New helper:

```python
subset_features_to_raster_extent(features, flood_path, padding_pixels=2)
```

Behavior:

- reads the hazard raster bounds with `rasterio`
- expands by two pixels
- converts the raster footprint to the road-link CRS
- spatially queries candidate road links intersecting that footprint
- passes only candidate links into `clip_features()` and then the `snail`
  intersection workflow

Also added a helper for the known US National Atlas / EPSG:2163 CRS alias used
by the toy rasters.

### `scripts/run_script2_event1_profile_prefilter.ps1`

Added a visible-window runner for one profiled Script 2 scenario:

```powershell
.\scripts\run_script2_event1_profile_prefilter.ps1
```

It runs:

```powershell
scripts\2_intersection_analysis.py 30 1
```

with:

- `NIRD_ENABLE_SPLIT_CACHE=1`
- `NIRD_TOY_FLOOD_TYPES=flood`
- `NIRD_RESULTS_VARIANT=revision`
- `cProfile` output under `profiles\`
- console/log output under `logs\`

The runner uses `cmd.exe` to merge Python stderr into stdout before PowerShell
sees it. This avoids PowerShell treating normal Python warnings as terminating
errors.

## Verification So Far

Syntax check passed using ArcGIS Python:

```powershell
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" -c "from pathlib import Path; compile(Path('scripts/2_intersection_analysis.py').read_text(), 'scripts/2_intersection_analysis.py', 'exec'); print('syntax ok')"
```

The one-scenario profile run was started but stopped before completion so this
handoff could be prepared. Failed partial logs were deleted.

No completed Script 2 profile from the raster-extent prefilter exists yet.

## How To Continue On The Other PC

1. Make sure `config.json` points to the local copied data bundle.
2. Confirm Script 1 outputs exist:

```text
<bundle_parent>\results\base_scenario\revision\edge_flows.gpq
<bundle_parent>\results\base_scenario\revision\trip_isolations.pq
<bundle_parent>\results\base_scenario\revision\odpfc.pq
```

3. Run the one-scenario Script 2 profile in a visible PowerShell window:

```powershell
.\scripts\run_script2_event1_profile_prefilter.ps1
```

4. Watch for this log line:

```text
Raster extent prefilter for va_hazard_class50_141node_base.tif: 483442 -> <candidate_count> road links
```

The candidate count should be far below 483,442. If it is not, inspect raster
CRS/bounds and road-link CRS before continuing.

5. If the one-scenario test completes, inspect:

```text
logs\script2_event1_raster_extent_prefilter_<timestamp>.log
profiles\script2_event1_raster_extent_prefilter_<timestamp>.prof
<bundle_parent>\results\disruption_analysis\revision\30
```

Then run events 2 and 3, followed by Scripts 3-5.

## Commit Status

This local `DAFNI-NIRD-clone` folder is not currently a Git checkout:

- no `.git` directory is present
- `git` is not available on PATH

So a real commit could not be created on this machine from the current folder.

When this work is placed in a proper Git checkout, commit these files:

```text
scripts/2_intersection_analysis.py
scripts/run_script2_event1_profile_prefilter.ps1
HANDOFF_CONUS_SCRIPT2_PREFILTER_20260601.md
```

Suggested commit message:

```text
Optimize Script 2 hazard intersection prefiltering
```

## Temp Cleanup Done

Stopped the active ArcGIS Python Script 2 profile process and removed failed
temporary logs:

```text
logs\script2_event1_raster_extent_prefilter_20260601_133706.log
logs\script2_event1_raster_extent_prefilter_20260601_134059.log
logs\script2_event1_raster_extent_prefilter_20260601_134205.log
logs\20260601_111857_script2_intersection_depth30_event1.log
```

No raster-extent prefilter `.prof` files remained after cleanup.
