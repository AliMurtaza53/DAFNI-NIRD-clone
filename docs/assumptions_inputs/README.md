# Model Assumptions And Parameter Inputs

This folder centralizes documentation for non-network, non-OD, non-hazard data inputs and
hard-coded assumptions used by the numbered NIRD workflow.

It is intentionally an inventory and assumptions register, not a data copy. Most parameter
workbooks, JSON files, and lookup tables live under the active data root from `config.json`
(`paths.soge_clusters`). This document names the expected files, fallback locations, and
code paths that consume them.

## Existing Documentation Check

The repository previously had partial workflow documentation in:

- `docs/CONUS_FREIGHT_WORKFLOW.md`
- `docs/faf5_county_disaggregation.md`
- `docs/path_realization_attempt_log.md`

There was no single document collecting vulnerability curves, damage-cost tables,
recovery-rate assumptions, speed/capacity assumptions, and cost constants. This README is
that consolidated register.

## Active Data Root

The numbered scripts use:

- `config.json`
- `nird.utils.load_config()`
- `paths.soge_clusters`

Most external parameter files are searched under this base path, often with both production
and toy/test fallback locations.

## Transport Assignment Parameters

Consumed by:

- `scripts/1_network_flow_model_revision.py`
- `scripts/4_prepare_disrupted_od_option5.py`
- `src/nird/road_revised.py`

Expected files under either `<base_path>/parameters/` or `<base_path>/inputs/parameters/`:

| File | Purpose | Main use |
| --- | --- | --- |
| `flow_breakpoint_dict.json` | Per road class hourly flow threshold where speed starts decreasing. | `edge_initial_speed_func()`, `update_edge_speed()` |
| `flow_cap_plph_dict.json` | Designed capacity per lane per hour by road class. | Initial `acc_capacity = capacity * lanes * 24` |
| `free_flow_speed_dict.json` | Free-flow speed by road class. | Initial speed before urban cap or flood cap |
| `min_speed_cap.json` | Minimum allowed congested speed by road class. | Lower bound in speed-flow update |
| `urban_speed_cap.json` | Urban speed restriction by road class. | Overrides free-flow speed when `urban == 1` |

Road classes are reclassified into `M`, `A_dual`, `A_single`, and `B` in
`src/nird/road_revised.py`.

The current speed-flow rule in `update_edge_speed()` is:

| Combined label | Reduction factor when flow exceeds breakpoint |
| --- | --- |
| `M` | `0.033 * excess hourly flow` |
| `A_dual` | `0.033 * excess hourly flow` |
| `A_single` | `0.05 * excess hourly flow` |
| `B`, `B_dual`, `B_single` | `0.05 * excess hourly flow` |

Speed is then clipped to the class minimum speed.

## Travel Cost Constants

Defined in:

- `src/nird/constants.py`

Used by:

- `src/nird/road_revised.py`

Key constants:

| Constant | Meaning |
| --- | --- |
| `CONV_METER_TO_MILE = 0.000621371` | Geometry length conversion |
| `CONV_MILE_TO_KM = 1.60934` | Mile to km conversion |
| `GBP_TO_USD = 1.27` | Exchange-rate conversion |
| `VOT_POUND_PER_HOUR` | Value of time by vehicle type, stored as USD/hour in current comments |
| `FUEL_LITRE_PER_KM` | Vehicle fuel-consumption polynomial coefficients |
| `NON_FUEL_PENCE_PER_KM` | Non-fuel operating-cost coefficients |

Cost construction in `compute_costs_for_links()`:

- edge time cost uses travel time and value of time;
- car time cost includes average occupancy `1.06`;
- operating cost combines fuel and non-fuel cost terms;
- route weight is `time_cost + operating_cost + average_toll_cost`;
- PSV and rail fare/waiting-time adjustments are applied during OD output/cost
  aggregation, not as ordinary car assignment defaults.

## Hazard Rasters And CONUS Projection

CONUS freight and toy hazard workflows expect aligned projections between the FAF5
network and hazard GeoTIFFs. See [`docs/geo_projection_conus.md`](../geo_projection_conus.md)
for portable GDAL/PROJ setup, CRS normalization, and Script 2 troubleshooting.

Toy hazard rasters (Script 2 events 1/2/3) are typically stored under:

```text
<base_path>/inputs/test_141node_50m/va_hazard_class50_141node_{base,low,high}.tif
```

Use `scripts/normalize_hazard_crs.py` when migrating rasters from another machine.

## Flood Speed Assumption

Implemented in:

- `scripts/2_intersection_analysis.py`
- legacy alternate: `scripts/2_int_analysis.py`
- related helper: `src/nird/road_functions.py`

Flood depth is converted from meters to centimeters. A road with flood depth below the
closure threshold retains a reduced speed:

```text
max_speed = free_flow_speed * (depth_cm / threshold_cm - 1)^2
```

At or above the threshold, speed becomes zero.

Important detail:

- `compute_maximum_speed_on_flooded_roads()` has a default `threshold=30`.
- The main Script 2 workflow uses the CLI `depth_key`/threshold logic when creating
  disrupted road-link outputs.

## Damage-Level Threshold Assumptions

Implemented in:

- `scripts/2_intersection_analysis.py`
- legacy alternate: `scripts/2_int_analysis.py`

Damage levels are categorical:

```text
no < minor < moderate < extensive < severe
```

For FAF/US-style classes, Script 2 treats these as major classes:

```text
motorway, motorway_link, trunk, primary, secondary
```

and these as minor/local classes:

```text
tertiary, service, unclassified
```

FAF/US surface flooding thresholds:

| Road group | Depth cm | Damage level |
| --- | --- | --- |
| Major | `< 200` | `no` |
| Major | `200-600` | `minor` |
| Major | `>= 600` | `moderate` |
| Minor/local | `< 50` | `no` |
| Minor/local | `50-600` | `minor` |
| Minor/local | `>= 600` | `moderate` |

FAF/US river flooding thresholds:

| Road group | Depth cm | Damage level |
| --- | --- | --- |
| Major | `< 50` | `no` |
| Major | `50-100` | `minor` |
| Major | `100-200` | `moderate` |
| Major | `200-600` | `extensive` |
| Major | `>= 600` | `severe` |
| Minor/local | `<= 0` | `no` |
| Minor/local | `0-50` | `minor` |
| Minor/local | `50-200` | `moderate` |
| Minor/local | `200-600` | `extensive` |
| Minor/local | `>= 600` | `severe` |

Script 2 also retains legacy UK-style threshold branches for `Motorway`, `A Road`,
`trunk_road`, and `road_label == tunnel`.

## Vulnerability Curves

Consumed by:

- `scripts/3_damage_analysis.py`

Expected file, searched in this order:

1. `<base_path>/damage_curves/damage_ratio_road_flood.xlsx`
2. `<base_path>/inputs/lookup/damage_ratio_road_flood.xlsx`
3. `<base_path>/tables/damage_ratio_road_flood.xlsx`

The workbook is converted into `snail.damages.PiecewiseLinearDamageCurve` objects.
Every column except `intensity` is treated as a damage-ratio curve.

Internal curve labels:

| Internal curve | Intended group in code comments / fallback mapping |
| --- | --- |
| `C1` | Motorways/trunk roads, sophisticated accessories, low flow; preferred US fallback `Interstate` |
| `C2` | Motorways/trunk roads, sophisticated accessories, high flow; preferred US fallback `Interstate` |
| `C3` | Motorways/trunk roads, non-sophisticated accessories, low flow; preferred US fallback `US Route` |
| `C4` | Motorways/trunk roads, non-sophisticated accessories, high flow; preferred US fallback `US Route` |
| `C5` | Other roads, low flow; preferred US fallback `State Route` |
| `C6` | Other roads, high flow; preferred US fallback `Local` |

For each disrupted road segment, Script 3 computes two curve-based damage fractions for
surface and river flooding.

## Direct-Damage Cost Tables

Consumed by:

- `scripts/3_damage_analysis.py`

Expected file, searched in this order:

1. `<base_path>/asset_costs/damage_cost_road_flood.xlsx`
2. `<base_path>/inputs/lookup/damage_cost_road_flood.xlsx`
3. `<base_path>/tables/damage_cost_road_flood.xlsx`

Expected sheets:

| Sheet | Purpose |
| --- | --- |
| `roads` | Ordinary road cost values |
| `tunnels` | Tunnel cost values; if missing, road costs are reused for toy fallback |
| `bridges-surface` | Bridge cost values for surface flooding |
| `bridges-river` | Bridge cost values for river flooding |
| `bridges` | Accepted fallback for both bridge flood types |

Cost formulas:

- Bridges: `width * length * bridge_cost_by_flood_type_and_damage_level`.
- Roads/tunnels: `length_km * lanes * unit_cost * damage_fraction`.
- Mean damage cost is the average of min and max.

Script 3 writes direct-damage outputs to:

```text
<base_path_parent>/results/damage_analysis/<variant>/*_with_damage_values.csv
```

## Recovery Rates

Consumed by:

- `scripts/4_rerouting_and_recovery_scenario_loop.py`

Expected file:

```text
<base_path>/tables/recovery design_updated.csv
```

Expected columns:

| Column | Meaning |
| --- | --- |
| `scenario` | Recovery scenario identifier |
| `event_day` | Scenario timing marker |
| `bridge_minor`, `bridge_moderate`, `bridge_extensive`, `bridge_severe` | Capacity recovery rate by bridge damage level |
| `road_minor`, `road_moderate`, `road_extensive`, `road_severe` | Capacity recovery rate by ordinary-road damage level |

Recovery functions:

- `bridge_recovery()`
- `ordinary_road_recovery()`

For non-`no` damage, recovered capacity is:

```text
pre_event_capacity * recovery_rate[damage_level][day_index]
```

## Rerouting And Disruption Candidate Assumptions

Implemented in:

- `scripts/4_rerouting_and_recovery_scenario_loop.py`
- `src/nird/road_revised.py`

Patch 4 adds:

```text
NIRD_BASELINE_PATH_OUTPUT_MODE=event_candidates
```

In this mode, the baseline assignment writes only OD rows whose path touches the event
damaged-edge set. This avoids writing full baseline `odpfc.pq` or a global OD-edge path
index.

Damaged-edge input for event-candidate mode:

```text
NIRD_EVENT_DAMAGED_EDGES_PATH=<csv-or-parquet>
```

Expected columns:

| Column | Required | Meaning |
| --- | --- | --- |
| `e_id` | Yes | Damaged edge ID |
| `event_id` | Optional | Event folder/key |
| `depth_key`, `flood_key` | Optional | Used to derive event ID if `event_id` is absent |
| `damage_level` | Optional | Informational for candidate generation |
| `road_label` | Optional | Informational for candidate generation |

Script 4 now first looks for:

```text
event_disrupted_candidates/<event_id>/disrupted_candidates.pq
event_disrupted_candidates/<event_id>/parts/*.pq
```

and falls back to legacy `odpfc` or path-index loaders only if event candidates are absent.

## Sensitivity Scripts

Scripts:

- `scripts/5_sensitivity_analysis_direct.py`
- `scripts/5_sensitivity_analysis_indirect.py`

These include additional sensitivity assumptions around:

- `damage_level` to numeric mappings;
- damage-ratio sensitivity;
- direct and indirect cost summaries.

They are analysis scripts rather than core numbered-workflow assumptions, but should be
checked before any final study write-up.

## Parameter File Checklist

Use this checklist before a full run:

- `config.json` points to the intended `paths.soge_clusters`.
- `<base_path>/parameters/flow_breakpoint_dict.json`
- `<base_path>/parameters/flow_cap_plph_dict.json`
- `<base_path>/parameters/free_flow_speed_dict.json`
- `<base_path>/parameters/min_speed_cap.json`
- `<base_path>/parameters/urban_speed_cap.json`
- One of the accepted `damage_ratio_road_flood.xlsx` locations.
- One of the accepted `damage_cost_road_flood.xlsx` locations.
- `<base_path>/tables/recovery design_updated.csv`
- For Patch 4/event-candidate runs: `NIRD_EVENT_DAMAGED_EDGES_PATH`.

## Code Reference Index

| Topic | Code |
| --- | --- |
| Speed/capacity initialization | `src/nird/road_revised.py:edge_initial_speed_func`, `edge_init` |
| Speed-flow degradation | `src/nird/road_revised.py:update_edge_speed` |
| Travel cost constants | `src/nird/constants.py` |
| Edge cost construction | `src/nird/road_revised.py:compute_costs_for_links` |
| Flood speed rule | `scripts/2_intersection_analysis.py:compute_maximum_speed_on_flooded_roads` |
| Damage-level thresholds | `scripts/2_intersection_analysis.py:compute_damage_levels_on_flooded_roads_vectorized` |
| Vulnerability curves | `scripts/3_damage_analysis.py:create_damage_curves` |
| Direct-damage cost formulas | `scripts/3_damage_analysis.py:compute_damage_values` |
| Recovery rates | `scripts/4_rerouting_and_recovery_scenario_loop.py:load_scenarios` |
| Recovery capacity update | `scripts/4_rerouting_and_recovery_scenario_loop.py:bridge_recovery`, `ordinary_road_recovery` |
