# NIRD/FAF5 Disruption Analysis Pipeline - Inputs & Outputs Reference

## Overview
This document catalogs all inputs and outputs for the 5-script analysis pipeline that simulates flood disruptions on the FAF5 USA freight network and calculates economic and rerouting impacts.

## FAF-Specific Refactor Checklist (Toy-Ready)

This section defines what must be updated so the full workflow is **explicitly FAF-based** (not UK/generic fallback behavior).

### Canonical toy paths to use
- **Toy base path (`base_path`)**: `sandbox/fairfax_soge_clusters_toy`
- **Results root**: `sandbox/results`
- **Script 1 outputs**: `sandbox/results/base_scenario/revision`
- **Script 2 outputs**: `sandbox/results/disruption_analysis/revision/{depth_key}`
- **Script 3 outputs**: `sandbox/results/damage_analysis/revision`
- **Script 4 outputs**: `sandbox/results/rerouting_analysis/revision/{depth_key}/{flood_key}`

### Global input contracts to enforce
1. **Edge IDs (`e_id`)**
   - Store and process as **string** in all scripts and outputs (`road_links`, `path`, `flood_links`, damage tables).
   - Reject mixed int/string joins.

2. **Node IDs (`origin_node`, `destination_node`, `from_id`, `to_id`)**
   - Normalize to **string** before building igraph networks and before running flow model.

3. **Path columns (`path`, `flood_links`)**
   - Must be true list-like edge-id arrays, not stringified arrays or character arrays.
   - Parse/normalize on read.

4. **FAF class semantics**
   - Treat FAF road classes as canonical (`motorway`, `trunk`, `primary`, `secondary`, `tertiary`, `service`, `unclassified`, etc.).
   - Do not rely on UK-only labels (`A Road`, `B Road`, UK form-of-way assumptions) unless explicitly mapped.

### Script-level updates required for FAF specificity

#### Script 1 (`1_network_flow_model_revision.py`)
- Keep FAF links/OD as primary inputs:
  - `sandbox/fairfax_soge_clusters_toy/inputs/networks/faf5/faf5_road_links.gpq`
  - `sandbox/fairfax_soge_clusters_toy/inputs/census_datasets/faf5_od_matrix.pq`
- Validate all parameter dictionaries cover FAF `combined_label` values.

#### Script 2 (`2_intersection_analysis.py`)
- Keep toy hazard mode as explicit FAF toy mode:
  - `sandbox/fairfax_soge_clusters_toy/inputs/test_17node/fairfax_hazard_class50_17node_{base|low|high}.tif`
- Keep study-area clipping with:
  - `sandbox/fairfax_soge_clusters_toy/study_area/fairfax_study_area.gpkg`
- Ensure outputs retain FAF `e_id` typing and per-link damage fields used downstream:
  - `flood_depth_max`, `damage_level_max`, `max_speed`.

#### Script 3 (`3_damage_analysis.py`)
- Use FAF-compatible lookup files (toy current):
  - `sandbox/fairfax_soge_clusters_toy/damage_curves/damage_ratio_road_flood_uk.xlsx`
  - `sandbox/fairfax_soge_clusters_toy/asset_costs/damage_cost_road_flood_uk.xlsx`
- Keep robust mapping from available toy columns to internal curves (`C1..C6`).
- Add/maintain generation of event-level damage output files:
  - `sandbox/results/damage_analysis/revision/intersections_{flood_key}_with_damage_values.csv`
- Recommended FAF enhancement: also export **edge-level** compact file per event with:
  - `e_id`, `damage_level_max`, `flood_depth_max`, optional direct-damage totals per edge.

#### Script 4 (`4_rerouting_and_recovery_scenario_loop.py`)
- Inputs should be strictly FAF-derived:
  - `sandbox/results/disruption_analysis/revision/{depth_key}/links/road_links_{flood_key}.gpq`
  - `sandbox/results/base_scenario/revision/odpfc.pq` (or event-specific ODPFC if generated)
  - `sandbox/results/damage_analysis/revision/intersections_{flood_key}_with_damage_values.csv`
  - `sandbox/fairfax_soge_clusters_toy/tables/recovery design_updated.csv`
- Keep script-3 damage merge as authoritative for event damage levels.
- Replace/avoid UK-style speed-day gating logic tied to `event_day == 1/2/3`.
  - Current toy recovery table uses day values: `0,7,14,30,60,90,120,150,180`.
  - Apply speed constraints using damage/flood masks and/or day ranges that match these values.
- Current rerouting trigger is capacity-only (`disrupted_flow = flow - acc_capacity`).
  - FAF-specific enhancement required: include rerouting triggers for severe speed/cost degradation even when capacity is not exceeded.

#### Script 5 (sensitivity)
- Direct analysis should consume script-3 FAF outputs only.
- Indirect analysis should consume script-4 FAF rerouting outputs with event/depth indexing consistent with toy naming (`1/2/3`, `15/30/60`).

### Immediate validation checks (must pass)
1. `e_id` type is string in links, paths, flood links, and damage tables.
2. `path` arrays are parsed as lists of FAF edge IDs.
3. Recovery table day values are consistent with speed-constraint conditions.
4. Script 4 outputs include both rerouting and direct damage fields in cost tables:
   - `rerouting_cost`, `direct_damage_total`, `combined_total_cost`.
5. For each toy event (`1`, `2`, `3`), verify non-empty disrupted OD candidates before rerouting loop.

---

## Script 1: Network Flow Model Revision
**File:** `scripts/1_network_flow_model_revision.py`  
**Purpose:** Establish baseline network flow simulation on FAF5 road network

### Inputs

#### Network & OD Data
- **faf5_road_links.gpq** 
  - Path: `{base_path}/networks/faf5/faf5_road_links.gpq`
  - Format: GeoParquet (GeoDataFrame)
  - Content: FAF5 road network with attributes (road class, link geometry, etc.)

- **faf5_od_matrix.pq**
  - Path: `{base_path}/census_datasets/faf5_od_matrix.pq`
  - Format: Parquet (DataFrame)
  - Content: Origin-destination matrix with baseline 2021 traffic flows

#### Model Parameters (JSON)
- **flow_breakpoint_dict.json**
  - Path: `{base_path}/parameters/flow_breakpoint_dict.json`
  - Content: Flow thresholds for traffic speed/capacity

- **flow_cap_plph_dict.json**
  - Path: `{base_path}/parameters/flow_cap_plph_dict.json`
  - Content: Road capacity (persons per lane per hour) by road class

- **free_flow_speed_dict.json**
  - Path: `{base_path}/parameters/free_flow_speed_dict.json`
  - Content: Speed limits by road class

- **min_speed_cap.json**
  - Path: `{base_path}/parameters/min_speed_cap.json`
  - Content: Minimum speed thresholds

- **urban_speed_cap.json**
  - Path: `{base_path}/parameters/urban_speed_cap.json`
  - Content: Urban area speed caps

### Outputs
All outputs saved to: `{base_path}/results/base_scenario/revision/`

- **edge_flows.gpq**
  - Format: GeoParquet
  - Content: Road network links enriched with baseline flow simulation results

- **trip_isolations.pq**
  - Format: Parquet
  - Content: Isolated trips analysis from baseline network

- **odpfc.pq**
  - Format: Parquet
  - Content: Origin-destination pairs with flows and paths

---

## Script 2: Intersection Analysis
**File:** `scripts/2_intersection_analysis.py`  
**Purpose:** Intersect road network with flood hazard rasters to compute flood depths and damage levels

### Inputs

#### Network Data
- **faf5_road_links.gpq**
  - Path: `{base_path}/networks/faf5/faf5_road_links.gpq`
  - Content: FAF5 road network geometry and attributes

- **edge_flows.gpq** (from Script 1)
  - Path: `{base_path}/results/base_scenario/revision/edge_flows.gpq`
  - Content: Road links with baseline flow simulation

#### Flood Hazard Data
- **Aqueduct flood rasters**
  - Path: `{base_path}/hazards/completed/`
  - Format: GeoTIFF raster files
  - Content: Global flood depth data at various return periods and depths
  - Pattern: `{depth_key}_{flood_key}.tif` (e.g., `30_2050.tif`)
  - Note: Windowed reads used to avoid memory allocation (3.48 GiB file size)

- **Toy hazard rasters (FAF toy mode)**
  - Path: `{base_path}/inputs/test_17node/`
  - Files:
    - `fairfax_hazard_class50_17node_base.tif`
    - `fairfax_hazard_class50_17node_low.tif`
    - `fairfax_hazard_class50_17node_high.tif`
  - Event mapping currently used:
    - `flood_key=1` → base
    - `flood_key=2` → low
    - `flood_key=3` → high

### Outputs
All outputs organized by flood key and saved to: `{base_path}/results/disruption_analysis/revision/{depth_key}/`

#### By-Depth Subdirectories
- **intersections/{flood_key}/**
  - **intersections_{flood_key}.pq**
    - Format: Parquet (DataFrame)
    - Content: Road segments split by hazard grid cells
    - Columns: Geometry, segment geometry, flood_depth_max, damage_level_max, max_speed

- **links/{flood_key}/**
  - **road_links_{flood_key}.gpq**
    - Format: GeoParquet (GeoDataFrame)
    - Content: Complete road network with flood impact data
    - Columns: Original network columns + flood_depth_max, damage_level_max, free_flow_speeds_max
    - Records: ~483,599 links with flood metadata

**Example Output Statistics** (for depth_key=30, flood_key=2050):
- Intersections: 2,329 segments
- Road links: 483,599 links
- Flood depth max: 0.0 m (for 2050 scenario at 30cm threshold)

---

## Script 3: Damage Analysis
**File:** `scripts/3_damage_analysis.py`  
**Purpose:** Compute direct economic damages using piecewise linear damage curves

### Inputs

#### Intersection Data (from Script 2)
- **intersections_{flood_key}.pq**
  - Path: `{base_path}/results/disruption_analysis/revision/{depth_key}/intersections/{flood_key}/`
  - Content: Road segments with flood depths and damage levels

#### Network Data
- **GB_road_links_with_bridges_subnetwork.gpq** (Legacy/UK reference)
  - Path: `{base_path}/networks/test_subnetwork/GB_road_links_with_bridges_subnetwork.gpq`
  - Content: Reference network with road classifications and bridge flags
  - Note: Script adapted for FAF5 schema (uses faf5_road_links.gpq when available)

#### Damage Ratio Curves
- **Lookup files (toy FAF run)**
  - `sandbox/fairfax_soge_clusters_toy/damage_curves/damage_ratio_road_flood_uk.xlsx`
  - `sandbox/fairfax_soge_clusters_toy/asset_costs/damage_cost_road_flood_uk.xlsx`
  - Note: Current toy files are coarse FAF-compatible mappings (Interstate/US Route/State Route/Local + bridges).
  - Recommendation for strict FAF production: provide dedicated FAF-named curve/cost workbook schema.

### Outputs
All outputs saved to: `{base_path}/results/damage_analysis/revision/{depth_key}/`

- **{flood_key}_with_damage_values.csv**
  - Format: CSV (DataFrame)
  - Content: Road segments with computed damage costs
  - Columns: Segment ID, damage_value_min, damage_value_max, (per damage category C1-C6)
  - Records: One per intersection segment

---

## Script 3 Postprocess: Damage Aggregation
**File:** `scripts/3_postprocess_damage.py`  
**Purpose:** Aggregate segment-level damages to event-level totals

### Inputs
- All CSV files from Script 3
  - Path: `{base_path}/results/damage_analysis/revision/{depth_key}/*.csv`
  - Content: Segment-level damage values

### Outputs
- **damage_summary.csv** (or similar)
  - Format: CSV
  - Content: Event-level aggregated damage statistics
  - Columns: flood_key, min_cost_total, max_cost_total, event_day
  - Purpose: Summary of total economic damage per flood event

---

## Script 4: Rerouting & Recovery Scenario Loop
**File:** `scripts/4_rerouting_and_recovery_scenario_loop.py`  
**Purpose:** Simulate rerouting costs during flood recovery over multiple time steps and scenarios

### Inputs

#### Damaged Network Data (from Script 2 + Script 3 integration)
- **road_links_{flood_key}.gpq**
  - Path: `{base_path.parent}/results/disruption_analysis/revision/{depth_key}/links/`
  - Content: Road links with flood depths and damage levels

- **intersections_{flood_key}_with_damage_values.csv** (from Script 3)
  - Path: `{base_path.parent}/results/damage_analysis/revision/`
  - Content: Event-level direct damage outputs used to re-derive per-edge `damage_level_max`

#### OD Data (from Script 1)
- **odpfc_{depth_key}_{flood_key}.pq** OR base scenario **odpfc.pq**
  - Path: `{base_path.parent}/results/disruption_analysis/revision/od/` (event-specific) OR `{base_path.parent}/results/base_scenario/revision/` (fallback)
  - Content: OD pairs with paths through network
  - Note: Derived from base scenario if disrupted version not available

#### Recovery Parameters
- **recovery design_updated.csv**
  - Path: `{base_path}/tables/recovery design_updated.csv`
  - Format: CSV
  - Content: Recovery rates over time for bridges vs. ordinary roads
  - Columns: scenario, event_day, bridge_minor, bridge_moderate, bridge_extensive, bridge_severe, road_minor, road_moderate, road_extensive, road_severe

#### Model Parameters
- **flow_breakpoint_dict.json**
  - Path: `{base_path}/parameters/flow_breakpoint_dict.json`
  - Content: Flow breakpoints for traffic simulation

### Outputs
All outputs saved to: `{base_path}/results/rerouting_analysis/revision/{depth_key}/{flood_key}/`

#### Per-Scenario Results
- **rerouting_cost_{scenario_idx}.csv**
  - Format: CSV
  - Content: Rerouting costs per OD pair across recovery days
  - Columns: origin, destination, scenario_idx, cost_type (toll/distance/time)

- **trip_isolations_{scenario_idx}.csv**
  - Format: CSV
  - Content: Trips unable to complete due to network disruption
  - Columns: origin, destination, scenario_idx

- **edge_flows_{scenario_idx}.gpq**
  - Format: GeoParquet
  - Content: Road network with flows for given recovery scenario
  - Records: One per road link with rerouted flows

#### Summary Results
- **cost_matrix_by_scenario.csv**
  - Format: CSV
  - Content: Aggregated rerouting costs across all scenarios
  - Columns (current script): `scenario`, `rer_time`, `rer_operate`, `rer_toll`, `rerouting_cost`, `direct_damage_total`, `combined_total_cost`
  - Records: One per recovery scenario row in recovery table (toy currently 9 rows: scenario 0-8)

**Note:** If no flooded OD pairs detected, script exits gracefully with message "No rerouting results to save."

---

## Script 5A: Sensitivity Analysis - Direct Damages
**File:** `scripts/5_sensitivity_analysis_direct.py`  
**Purpose:** Morris sensitivity analysis for direct flood damages using road characteristics

### Inputs

#### Intersection Data
- **Damage intersection files** (from Script 3)
  - Path: `{base_path}/results/damage_analysis/revision/{depth_key}/*.csv`
  - Content: Segment-level flood depths and damage values

#### UK-Specific Boundary Data
- **gb_lad_2021_estimates.geoparquet**
  - Path: Not specified, expected in `{base_path}/networks/`
  - Content: GB Local Authority District boundaries
  - **Status:** Missing - Script gracefully skips if unavailable

#### Network Reference
- **GB_road_links_with_bridges_subnetwork.gpq**
  - Path: `{base_path}/networks/test_subnetwork/GB_road_links_with_bridges_subnetwork.gpq`
  - Content: Road classifications and bridge flags

### Outputs
All outputs saved to: `{base_path}/results/sensitivity_analysis/direct/{depth_key}/`

- **morris_indices_{flood_key}.csv**
  - Format: CSV
  - Content: Morris sensitivity indices (μ, σ, μ*)
  - Columns: Parameter name, μ (mean), σ (std), μ* (mean absolute)

- **sensitivity_plot_{flood_key}.png**
  - Format: PNG image
  - Content: Scatter plot of μ* vs σ showing parameter importance
  - DPI: 300

**Status:** Currently disabled - requires UK LAD boundary data

---

## Script 5B: Sensitivity Analysis - Indirect (Rerouting) Costs
**File:** `scripts/5_sensitivity_analysis_indirect.py`  
**Purpose:** Morris sensitivity analysis for indirect costs (rerouting impacts) using road and hazard characteristics

### Inputs

#### Rerouting Cost Data (from Script 4)
- **rerouting_cost_*.csv**
  - Path: `{base_path}/results/rerouting_analysis/revision/{depth_key}/{flood_key}/`
  - Content: OD pair rerouting costs per scenario
  - **Status:** Missing if Script 4 produces zero results

#### Network Data
- **edges_revised.pq**
  - Path: `{base_path}/results/` or `res_path/`
  - Content: Edge attributes for sensitivity sampling

#### OD Flow Data
- **odpfc.pq** (from Script 1)
  - Path: `{base_path}/results/base_scenario/revision/`
  - Content: Baseline OD flows

### Outputs
All outputs saved to: `{base_path}/results/sensitivity_analysis/indirect/{depth_key}/`

- **morris_indices_indirect_{flood_key}.csv**
  - Format: CSV
  - Content: Morris sensitivity indices for rerouting costs
  - Columns: Parameter name, μ (mean), σ (std), μ* (mean absolute)

- **sensitivity_plot_indirect_{flood_key}.png**
  - Format: PNG image
  - Content: Scatter plot of μ* vs σ for rerouting impacts
  - DPI: 300

**Status:** Currently disabled - requires Script 4 outputs (which are missing due to zero flood depths in 2050 scenario)

---

## Configuration & Parameters

### Main Configuration File
- **config.json**
  - Path: `{base_path}/config.json` (typically `C:\Users\alimu\NIRD_Data\soge_clusters\config.json`)
  - Content: Base paths and output paths
  - Key fields: `paths.soge_clusters`, `paths.base_path`, `paths.output_path`

### Base Path Structure
```
{base_path}/
├── networks/
│   ├── faf5/
│   │   └── faf5_road_links.gpq
│   └── test_subnetwork/
│       └── GB_road_links_with_bridges_subnetwork.gpq
├── census_datasets/
│   └── faf5_od_matrix.pq
├── parameters/
│   ├── flow_breakpoint_dict.json
│   ├── flow_cap_plph_dict.json
│   ├── free_flow_speed_dict.json
│   ├── min_speed_cap.json
│   └── urban_speed_cap.json
├── tables/
│   └── recovery design_updated.csv
├── hazards/
│   └── completed/
│       └── {depth_key}_{flood_key}.tif
└── dbs/
    ├── baseline.duckdb
    └── recovery_{depth_key}_{flood_key}.duckdb
```

### Results Directory Structure
```
{base_path.parent}/results/
├── base_scenario/
│   └── revision/
│       ├── edge_flows.gpq
│       ├── trip_isolations.pq
│       └── odpfc.pq
├── disruption_analysis/
│   └── revision/{depth_key}/
│       ├── intersections/{flood_key}/
│       │   └── intersections_{flood_key}.pq
│       └── links/{flood_key}/
│           └── road_links_{flood_key}.gpq
├── damage_analysis/
│   └── revision/{depth_key}/
│       └── {flood_key}_with_damage_values.csv
├── rerouting_analysis/
│   └── revision/{depth_key}/{flood_key}/
│       ├── rerouting_cost_0.csv
│       ├── rerouting_cost_1.csv
│       ├── ... (up to 5)
│       ├── trip_isolations_0.csv
│       ├── edge_flows_0.gpq
│       └── cost_matrix_by_scenario.csv
└── sensitivity_analysis/
    ├── direct/{depth_key}/
    │   ├── morris_indices_{flood_key}.csv
    │   └── sensitivity_plot_{flood_key}.png
    └── indirect/{depth_key}/
        ├── morris_indices_indirect_{flood_key}.csv
        └── sensitivity_plot_indirect_{flood_key}.png
```

---

## Data Flow Summary

```
Script 1: Network Flow
├── Input: faf5_road_links.gpq, faf5_od_matrix.pq, parameters
└── Output: edge_flows.gpq, odpfc.pq, trip_isolations.pq

    ↓

Script 2: Intersection Analysis
├── Input: edge_flows.gpq, faf5_road_links.gpq, hazard rasters
└── Output: intersections_{flood_key}.pq, road_links_{flood_key}.gpq

    ↓ (Path A)

Script 3: Damage Analysis
├── Input: intersections_{flood_key}.pq
└── Output: {flood_key}_with_damage_values.csv

    ↓

Script 3 Postprocess: Damage Aggregation
├── Input: {flood_key}_with_damage_values.csv
└── Output: damage_summary.csv

    ↓ (Path B)

Script 4: Rerouting & Recovery
├── Input: road_links_{flood_key}.gpq, odpfc.pq, recovery_rates.csv
└── Output: rerouting_cost_*.csv, cost_matrix_by_scenario.csv

    ↓

Script 5B: Sensitivity Analysis (Indirect)
├── Input: rerouting_cost_*.csv, odpfc.pq
└── Output: morris_indices_indirect.csv, sensitivity_plot.png

Script 5A: Sensitivity Analysis (Direct)
├── Input: {flood_key}_with_damage_values.csv
└── Output: morris_indices.csv, sensitivity_plot.png
```

---

## Key Parameters

### Execution Parameters
- **depth_key**: Flood depth threshold (e.g., "30" for 30cm)
- **flood_key**: Year or scenario identifier (e.g., "2050" for 2050 projection)
- **num_of_cpu**: Number of CPUs for parallel processing
- **num_of_chunk**: Number of chunks for distributed processing

### Common Values
- **depth_key values:** "15", "30", "60" (depth in cm)
- **flood_key values (toy FAF mode):** "1", "2", "3" (base/low/high toy hazards)
- **flood_key values (non-toy/global mode):** e.g., "2050", "2100" depending on hazard naming
- **Scenario indices:** toy table currently 0-8 (9 recovery snapshots)

---

## File Size Reference

| File | Size | Notes |
|------|------|-------|
| faf5_road_links.gpq | ~200 MB | USA road network geometry |
| faf5_od_matrix.pq | ~50 MB | OD flows dataset |
| Aqueduct rasters | 3.48 GB each | Windowed reads required |
| intersections_2050.pq | ~10 MB | 2,329 segments |
| road_links_2050.gpq | ~150 MB | 483,599 links |
| rerouting_cost_*.csv | 1-5 MB | Per scenario |

---

## Notes & Caveats

1. **Aqueduct Data**: Global 3.48 GiB raster files - Script 2 uses windowed reads to avoid memory allocation failure
2. **FAF5 vs UK Schema**: Scripts adapted to work with FAF5 road network schema (lacking UK-specific fields like road_label, road_bridge)
3. **Graceful Degradation**: 
   - Script 4 exits cleanly if no flooded OD pairs detected
   - Scripts 5A-5B skip if required inputs missing
4. **Zero Flood Depths**: 2050 scenarios at 30cm threshold may yield max_flood_depth=0.0, resulting in zero damages and no rerouting impacts
5. **PROJ Database Warnings**: Non-fatal version conflicts between system PROJ and Python packages
6. **Script 4 rerouting trigger**: Current `disrupted_flow = flow - acc_capacity` is capacity-only; speed-only degradation may not create rerouting unless explicitly added as a trigger
7. **Event-day gating mismatch risk**: Speed-constraint logic in Script 4 must align with actual recovery table `event_day` values (toy currently uses 0,7,14,30,60,90,120,150,180)
