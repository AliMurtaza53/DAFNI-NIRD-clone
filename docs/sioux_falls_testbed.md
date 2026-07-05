# Sioux Falls pipeline testbed

TNTP Sioux Falls network upcast into the FAF5-compatible schema used by the toy
routing disruption tests. Runs scripts 1–4 end-to-end on a real topology without
CONUS-scale data.

## Files

| Path | Role |
|------|------|
| `tests/data/sioux_falls_tntp/SiouxFalls_{net,node,trips}.tntp` | Offline TNTP sources |
| `tests/data/sioux_falls_tntp/SiouxFallsCoordinates.geojson` | Vendored bstabler reference coords (WGS84) |
| `tests/sioux_falls_fixtures.py` | Builds temp dataset (links, OD, hazard, parameters) |
| `tests/test_sioux_falls_pipeline_disruptions.py` | Single E2E pipeline test |

## Calibration (realism mode)

- **Capacity**: TNTP link `capacity` (veh/hr) is mapped to per-link `flow_cap_plph`
  and used by Script 1 instead of the flat toy `flow_cap_plph=1` override.
- **Demand**: TNTP trips are scaled by `DEMAND_SCALE = 0.3`; freight is `9%` of
  scaled passenger demand.
- **Hazard**: full-network raster extent (all links intersect Script 2), with
  nonzero depth only on the 10–15 bridge interior.
- **Damage**: Sioux Falls-specific scaled damage workbooks (KUSD-scale direct
  damage, not billions).
- **Script 4**: freight and passenger overlay raw assignment demand onto unique
  disrupted OD pairs; closed links (`max_speed=0`) contribute zero capacity in
  the disruption bottleneck step; summaries prefer `total_disrupted_flow_unique_od`.

## Spatial representation

- **Source coordinates**: `SiouxFalls_node.tntp` X/Y are the WGS84 lon/lat values
  published in the bstabler `SiouxFallsCoordinates.geojson`. They are used directly
  as EPSG:4326 points (no anchoring/scaling), so the testbed layout matches the
  canonical Sioux Falls shape.
- **Pipeline CRS**: links are built in EPSG:4326, then reprojected to
  `OUTPUT_CRS = EPSG:9311` (CONUS Albers) for all parquet outputs, hazard raster,
  and study-area geometry — the same CRS the CONUS pipeline computes in. No
  CONUS/production code paths change.
- **Maps**: QA maps in `visualize_scenario_qa.ipynb` reproject links back to
  EPSG:4326 (`links.to_crs("EPSG:4326")`) for display.
- A unit test asserts TNTP node coordinates match the vendored GeoJSON within a
  small geographic tolerance.

## Fixture design

- **Nodes**: `sf_1`, `sf_2`, …; WGS84 lon/lat from the bstabler reference GeoJSON.
- **Bridges**: five physical pairs with `road_label=bridge`.
- **Flooded bottleneck**: physical pair 10–15 (both directions).
- **Reroute gain edge**: 11–14.
- **Classification**: `local` / `tertiary` only (avoids embankment zeroing flood depth).

## Run

```powershell
pytest tests/test_sioux_falls_pipeline_disruptions.py -v --basetemp ".pytest-tmp"
```

## Scenario QA

After a run, point the scenario summary tools at the pytest results tree:

```powershell
$env:NIRD_RESULTS_ROOT = ".pytest-tmp/test_sioux_falls_pipeline_scri0/results"
$env:NIRD_RESULTS_VARIANT = "toy_sioux_falls"
$env:NIRD_TESTBED = "1"
python scripts/summarize_scenario_run.py
```

Or open `scripts/visualizations/visualize_scenario_qa.ipynb` with the same env vars.

## Interpreting outputs

- `freight_disrupted_flow` / `passenger_disrupted_flow` in summaries use
  `total_disrupted_flow_unique_od` when present (one row per OD).
- Rerouting cost sign can be positive or negative depending on whether detour
  time/cost exceeds decongestion benefits on alternate paths.
- Isolation rows/flows are reported separately for freight and passenger.
