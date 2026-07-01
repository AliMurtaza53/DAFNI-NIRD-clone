# Sioux Falls pipeline testbed

TNTP Sioux Falls network upcast into the FAF5-compatible schema used by the toy
routing disruption tests. Runs scripts 1–4 end-to-end on a real topology without
CONUS-scale data.

## Files

| Path | Role |
|------|------|
| `tests/data/sioux_falls_tntp/SiouxFalls_{net,node,trips}.tntp` | Offline TNTP sources |
| `tests/sioux_falls_fixtures.py` | Builds temp dataset (links, OD, hazard, parameters) |
| `tests/test_sioux_falls_pipeline_disruptions.py` | Single E2E pipeline test |

## Fixture design

- **Nodes**: `sf_1`, `sf_2`, …; geometry anchored near Sioux Falls (~15 km extent).
- **Bridges**: five physical pairs with `road_label=bridge`.
- **Flooded bottleneck**: physical pair 10–15 (both directions).
- **Reroute gain edge**: 11–14.
- **OD**: full TNTP trips as passenger; freight = 9% of passenger in `faf5_od_matrix.pq`.
- **Hazard**: 10 m raster, interior segment only, CRS EPSG:9311 aligned with links.
- **Classification**: `local` / `tertiary` only (avoids embankment zeroing flood depth).
- **Capacity**: `flow_cap_plph=1` (toy parity).

## Freight vs passenger (Script 4)

**Passenger** rerouting overlays raw TNTP demand → large disrupted flow and
reroute edge shifts are expected.

**Freight** uses capacity-adjusted baseline `odpfc` flows (capped near daily link
capacity), so `total_disrupted_flow` and freight reroute edge flows are often
zero even when flooding is valid. This is expected on this network scale.

## Run

```powershell
pytest tests/test_sioux_falls_pipeline_disruptions.py -v --basetemp ".pytest-tmp"
```

## Scenario QA

After a run, point the scenario summary tools at the pytest results tree:

```powershell
$env:NIRD_RESULTS_ROOT = ".pytest-tmp/test_sioux_falls_pipeline_scri0/results"
$env:NIRD_RESULTS_VARIANT = "toy_sioux_falls"
$env:NIRD_INPUT_ROOT = ".pytest-tmp/test_sioux_falls_pipeline_scri0/toy_data"
$env:NIRD_TESTBED = "1"
python scripts/summarize_scenario_run.py
```

Or open `scripts/visualizations/visualize_scenario_qa.ipynb` with the same env vars.
