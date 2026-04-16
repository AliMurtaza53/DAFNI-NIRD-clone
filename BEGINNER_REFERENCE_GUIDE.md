# Beginner Reference Guide (Working Draft)

_Last updated: 2026-04-12_

This is a living beginner guide. It consolidates existing quickstarts/READMEs and adds a practical file index. We will expand and refine definitions as we go.

## Table of Contents

- [1) Start Here (Existing Guides)](#1-start-here-existing-guides)
- [2) Pipeline at a Glance (Scripts 1–5)](#2-pipeline-at-a-glance-scripts-15)
- [3) Detailed File I/O Structure (Current FAF toy setup)](#3-detailed-file-io-structure-current-faf-toy-setup)
- [4) Parameter Files (starter notes)](#4-parameter-files-starter-notes)
- [5) Complete Script Inventory (all files under scripts/)](#5-complete-script-inventory-all-files-under-scripts)
- [6) Full Workspace File Catalog (211 files)](#6-full-workspace-file-catalog-211-files)

## 1) Start Here (Existing Guides)

- [README.md](README.md): project overview, setup, tests, docs build, container basics.
- [FAF5_QUICK_START.md](FAF5_QUICK_START.md): quickest path for FAF5 conversion and first run.
- [PIPELINE_INPUTS_OUTPUTS.md](PIPELINE_INPUTS_OUTPUTS.md): most complete current script I/O reference.
- [README_PHASE1.md](README_PHASE1.md): phase-oriented execution notes.
- [BRANCH_ROADMAP.md](BRANCH_ROADMAP.md): branch strategy and development phases.

## 2) Pipeline at a Glance (Scripts 1–5)

| Step | Script | Main inputs | Main outputs |
|---|---|---|---|
| 1 | scripts/1_network_flow_model_revision.py | FAF links, FAF OD matrix, speed/capacity parameter JSONs | base `edge_flows.gpq`, `trip_isolations.pq`, `odpfc.pq` |
| 2 | scripts/2_intersection_analysis.py | base links/flows + hazard rasters + study area | disrupted intersections and links by event/depth |
| 3 | scripts/3_damage_analysis.py | Script 2 intersections + damage curve/cost lookup files | direct-damage CSVs per event |
| 4 | scripts/4_rerouting_and_recovery_scenario_loop.py | Script 2 links + Script 3 damage + recovery table + OD paths | rerouting costs, edge flows, trip isolations by scenario/day |
| 5A | scripts/5_sensitivity_analysis_direct.py | direct damage outputs/features | direct sensitivity analysis outputs |
| 5B | scripts/5_sensitivity_analysis_indirect.py | rerouting/indirect outputs/features | indirect sensitivity analysis outputs |

## 3) Detailed File I/O Structure (Current FAF toy setup)

### Core configured base paths
- `config.json` / `configs.json` currently point `paths.soge_clusters` to `sandbox/fairfax_soge_clusters_toy`.
- Most generated outputs are under `sandbox/results`.

### Script 1 (Baseline flow)
**Inputs**
- `sandbox/fairfax_soge_clusters_toy/inputs/networks/faf5/faf5_road_links.gpq`
- `sandbox/fairfax_soge_clusters_toy/inputs/census_datasets/faf5_od_matrix.pq`
- `sandbox/fairfax_soge_clusters_toy/parameters/flow_breakpoint_dict.json`
- `sandbox/fairfax_soge_clusters_toy/parameters/flow_cap_plph_dict.json`
- `sandbox/fairfax_soge_clusters_toy/parameters/free_flow_speed_dict.json`
- `sandbox/fairfax_soge_clusters_toy/parameters/min_speed_cap.json`
- `sandbox/fairfax_soge_clusters_toy/parameters/urban_speed_cap.json`
**Outputs**
- `sandbox/results/base_scenario/revision/edge_flows.gpq`
- `sandbox/results/base_scenario/revision/trip_isolations.pq`
- `sandbox/results/base_scenario/revision/odpfc.pq`

### Script 2 (Hazard intersection/disruption)
**Inputs**
- Script 1 base outputs (especially `edge_flows.gpq`)
- Hazard rasters from `sandbox/fairfax_soge_clusters_toy/inputs/test_17node/` or `hazards/completed/...`
- Study area from `sandbox/fairfax_soge_clusters_toy/study_area/`
**Outputs**
- `sandbox/results/disruption_analysis/revision/{depth_key}/intersections/intersections_{flood_key}.pq`
- `sandbox/results/disruption_analysis/revision/{depth_key}/links/road_links_{flood_key}.gpq`
- `sandbox/results/disruption_analysis/revision/{depth_key}/event_summary_depth{depth_key}.csv`

### Script 3 (Direct damages)
**Inputs**
- Script 2 intersections parquet files
- `sandbox/fairfax_soge_clusters_toy/damage_curves/damage_ratio_road_flood_uk.xlsx`
- `sandbox/fairfax_soge_clusters_toy/asset_costs/damage_cost_road_flood_uk.xlsx`
**Outputs**
- `sandbox/results/damage_analysis/revision/intersections_{flood_key}_with_damage_values.csv`

### Script 4 (Rerouting + recovery)
**Inputs**
- Script 2 disrupted links
- Script 3 damage CSVs
- Script 1/2 OD paths (`odpfc`)
- `sandbox/fairfax_soge_clusters_toy/tables/recovery design_updated.csv`
- Flow breakpoint params (`flow_breakpoint_dict.json`)
**Outputs**
- `sandbox/results/rerouting_analysis/revision/{depth_key}/{flood_key}/cost_matrix_by_scenario.csv`
- `sandbox/results/rerouting_analysis/revision/{depth_key}/{flood_key}/edge_flows_{scenario}.gpq`
- `sandbox/results/rerouting_analysis/revision/{depth_key}/{flood_key}/rerouting_cost_{scenario}.csv`
- `sandbox/results/rerouting_analysis/revision/{depth_key}/{flood_key}/trip_isolations_{scenario}.csv`
- `sandbox/results/rerouting_analysis/revision/{depth_key}/{flood_key}/odpfc_{scenario}.pq`

### Script 5 (Sensitivity)
**Inputs**
- Script 3 and Script 4 generated features/tables.
**Outputs**
- Sensitivity metrics and plots/tables generated by direct/indirect scripts.

## 4) Parameter Files (starter notes)

- `flow_breakpoint_dict.json`: flow threshold breakpoints by modeled road class label.
- `flow_cap_plph_dict.json`: per-lane per-hour capacity assumptions by class.
- `free_flow_speed_dict.json`: uncongested/free-flow speeds by class.
- `min_speed_cap.json`: lower bounds on speed under congestion/disruption.
- `urban_speed_cap.json`: speed caps for urban links.
- `capt_minor.json`, `capt_moderate.json`, `capt_extensive.json`, `capt_severe.json`: recovery/capacity progression curves by damage severity (list values from 0 to 1 over time index).

## 5) Complete Script Inventory (all files under scripts/)

### Core pipeline (scripts 1-5)

- `scripts/1_network_flow_model_revision.py`: Script 1: baseline network flow assignment and base outputs.
- `scripts/2_intersection_analysis.py`: Script 2: flood-hazard intersection analysis and disrupted links.
- `scripts/3_damage_analysis.py`: Script 3: direct damage estimation from depth + vulnerability curves.
- `scripts/4_rerouting_and_recovery_scenario_loop.py`: Script 4: rerouting/recovery simulation across scenarios and days.
- `scripts/5_sensitivity_analysis_direct.py`: Script 5A: direct-damage sensitivity analysis.
- `scripts/5_sensitivity_analysis_indirect.py`: Script 5B: indirect/rerouting sensitivity analysis.

### Alternate/legacy pipeline variants

- `scripts/2_int_analysis.py`: Legacy/alternate Script 2 implementation.
- `scripts/3_postprocess_damage.py`: Post-processing for Script 3 damage outputs.

### Workspace and utility script

- `scripts/DAFNI_NIRD.code-workspace`: Project file.
- `scripts/organize_spatial_data.ps1`: PowerShell helper for organizing spatial datasets.

### DAFNI platform demos and wrappers (`scripts/dafni_plat`)

- `scripts/dafni_plat/demo_baseline flow modelling.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/dafni_plat/demo_damage analysis.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/dafni_plat/demo_traffic flow disruption and rerouting analysis.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/dafni_plat/nird_3_damage_analysis.py`: DAFNI platform-oriented Python workflow script.
- `scripts/dafni_plat/nird_4_rerouting_and_recovery.py`: DAFNI platform-oriented Python workflow script.
- `scripts/dafni_plat/visualise_damage_analysis.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.

### Experimental and prototype workflows (`scripts/experiments`)

- `scripts/experiments/1_network_flow_model_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/2_intersection_analysis_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/3_damage_analysis_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_batch_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_fixed.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_scenario.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/convert_uuid.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/ibis_rerouting_event1.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_event5.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_preprocess.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/ibis_rerouting_preprocess_15.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_preprocess_30.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_preprocess_60.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_scenario.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_disruption.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_distributed.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_osm.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_revised.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/od_gb_oa_2021.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/od_gb_oa_2021_node.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/od_truncation.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/postprocess_plot.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/postprocess_rerouting_isolation.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/recovery_process_design.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_disruption_damage.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_disruption_maxSpeed.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_network_creation.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_network_preprocess.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/test.py`: Experimental/prototype Python script for scenario testing or method development.

### External project variants

- `scripts/macchub/1_network_flow_model_macchub.py`: Python source script/module used in project workflows.
- `scripts/miraca/1_network_flow_model_miraca.py`: Python source script/module used in project workflows.

### NIST rail workflow (`scripts/nist-rail`)

- `scripts/nist-rail/1_network_creation.py`: NIST rail workflow step script.
- `scripts/nist-rail/2_network_track_speed.py`: NIST rail workflow step script.
- `scripts/nist-rail/3_estimate_daily_station_entries_exits.py`: NIST rail workflow step script.
- `scripts/nist-rail/4_timetable_origin_destination_pairs.py`: NIST rail workflow step script.
- `scripts/nist-rail/5_rail_od_inputs.py`: NIST rail workflow step script.
- `scripts/nist-rail/6_rail_od_prediction.py`: NIST rail workflow step script.
- `scripts/nist-rail/7_rail_flow_modelling.py`: NIST rail workflow step script.

### NIST road workflow (`scripts/nist-road`)

- `scripts/nist-road/1_network_flow_model_nist.py`: NIST road workflow step script.

## 6) Full Workspace File Catalog (211 files)

One-line explainer is intentionally concise in this first draft; we can expand any section/file in later revisions.

<details>
<summary>Expand full catalog</summary>


- `.github/workflows/docs.yml`: YAML environment/configuration or model-definition file.
- `.github/workflows/test.yml`: YAML environment/configuration or model-definition file.
- `.gitignore`: Project file.
- `.pre-commit-config.yaml`: YAML environment/configuration or model-definition file.
- `BRANCH_ROADMAP.md`: Branch strategy and phased implementation roadmap.
- `FAF5_INTEGRATION_GUIDE.md`: Detailed FAF5-to-NIRD schema and workflow integration notes.
- `FAF5_QUICK_START.md`: FAF5 conversion and toy-run quickstart.
- `File and Data Str.docx`: Working notes document (Word format).
- `GPU_PARALLELIZATION_GUIDE.md`: GPU/distributed scaling guidance for future optimization.
- `LICENSE`: Project file.
- `PIPELINE_INPUTS_OUTPUTS.md`: Most complete current script-level input/output reference.
- `README.md`: Primary project overview and developer setup instructions.
- `README_PHASE1.md`: Phase-1 setup/status notes and workflow guidance.
- `SETUP_SUMMARY.md`: Repository setup summary and branch/admin notes.
- `Script 3 updates for FAF.docx`: Working notes document (Word format).
- `config.json`: Active path configuration for sandbox toy runs.
- `configs.json`: Alternative/duplicate path configuration file.
- `containers/nird_road/Dockerfile-damage`: Project file.
- `containers/nird_road/Dockerfile-recovery`: Project file.
- `containers/nird_road/dafni-run-damage.sh`: Shell wrapper script for containerized execution.
- `containers/nird_road/dafni-run-recovery.sh`: Shell wrapper script for containerized execution.
- `containers/nird_road/environment.yaml`: YAML environment/configuration or model-definition file.
- `containers/nird_road/model-definition-damage.yml`: YAML environment/configuration or model-definition file.
- `containers/nird_road/model-definition-recovery.yml`: YAML environment/configuration or model-definition file.
- `convert_faf5_od_to_nird.py`: Converts FAF5 OD flow data into NIRD-compatible OD parquet.
- `convert_faf5_to_nird.py`: Converts FAF5 link/network data into NIRD-compatible files.
- `docs/Makefile`: Project file.
- `docs/source/_static/theme_tweaks.css`: Stylesheet for documentation site appearance.
- `docs/source/conf.py`: Python source script/module used in project workflows.
- `docs/source/getting_started.md`: Documentation file.
- `docs/source/index.rst`: Documentation file.
- `docs/source/license.rst`: Documentation file.
- `environment_skmob.yaml`: Conda environment specification for SKMob-related workflows.
- `pyproject.toml`: Python package metadata and tooling configuration.
- `sandbox/fairfax_baseline/inputs/admin_boundaries/README.md`: Documentation file.
- `sandbox/fairfax_baseline/inputs/networks/faf5/faf5_road_links.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_baseline/inputs/test_17node/faf5_od_matrix_17x17_test.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/fairfax_baseline/inputs/test_17node/faf5_od_matrix_17x17_test.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_centroid_nodes_17.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_class50_connectors.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_base.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_base.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_base.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_high.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_high.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_high.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_low.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_low.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_baseline/inputs/test_17node/fairfax_hazard_class50_17node_low.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/study_area/fairfax_study_area.geojson`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline/study_area/fairfax_study_area.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_baseline_prep.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `sandbox/fairfax_soge_clusters_toy/asset_costs/damage_cost_road_flood_uk.xlsx`: Spreadsheet lookup/parameter file for damage or asset costs.
- `sandbox/fairfax_soge_clusters_toy/damage_curves/damage_ratio_road_flood_uk.xlsx`: Spreadsheet lookup/parameter file for damage or asset costs.
- `sandbox/fairfax_soge_clusters_toy/dbs/baseline.duckdb`: DuckDB database storing intermediate simulation tables.
- `sandbox/fairfax_soge_clusters_toy/dbs/recovery_30_1.duckdb`: DuckDB database storing intermediate simulation tables.
- `sandbox/fairfax_soge_clusters_toy/hazards/completed/river/dmv_toy/Raster/dmv_RD_FLRF_1.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/hazards/completed/river/dmv_toy/Raster/dmv_RD_FLRF_2.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/hazards/completed/river/dmv_toy/Raster/dmv_RD_FLRF_3.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/hazards/completed/surface/dmv_toy/Raster/dmv_RD_FLSW_1.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/hazards/completed/surface/dmv_toy/Raster/dmv_RD_FLSW_2.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/hazards/completed/surface/dmv_toy/Raster/dmv_RD_FLSW_3.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/inputs/census_datasets/faf5_od_matrix.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_soge_clusters_toy/inputs/census_datasets/faf5_od_node_mapping.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/fairfax_soge_clusters_toy/inputs/networks/faf5/faf5_road_links.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/fairfax_soge_clusters_toy/inputs/test_17node/fairfax_hazard_class50_17node.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/inputs/test_17node/fairfax_hazard_class50_17node_base.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/inputs/test_17node/fairfax_hazard_class50_17node_high.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/inputs/test_17node/fairfax_hazard_class50_17node_low.tif`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/parameters/capt_extensive.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/capt_minor.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/capt_moderate.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/capt_severe.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/flow_breakpoint_dict.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/flow_cap_plph_dict.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/free_flow_speed_dict.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/min_speed_cap.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/parameters/urban_speed_cap.json`: Model parameter file (JSON) used by flow/damage/recovery logic.
- `sandbox/fairfax_soge_clusters_toy/study_area/fairfax_study_area.geojson`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/study_area/fairfax_study_area.gpkg`: Spatial data file (vector/raster) used as model input/output.
- `sandbox/fairfax_soge_clusters_toy/tables/recovery design_updated.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/input_files_deep_dive.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `sandbox/results/base_scenario/revision/edge_flows.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/base_scenario/revision/odpfc.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/base_scenario/revision/trip_isolations.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/damage_analysis/revision/intersections_1_with_damage_values.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/damage_analysis/revision/intersections_2_with_damage_values.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/damage_analysis/revision/intersections_3_with_damage_values.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/disruption_analysis/revision/30/event_summary_depth30.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/disruption_analysis/revision/30/intersections/intersections_1.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/disruption_analysis/revision/30/intersections/intersections_2.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/disruption_analysis/revision/30/intersections/intersections_3.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/disruption_analysis/revision/30/links/road_links_1.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/disruption_analysis/revision/30/links/road_links_2.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/disruption_analysis/revision/30/links/road_links_3.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/disruption_analysis/revision/od/odpfc_30_1.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/cost_matrix_by_scenario.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_0.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_1.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_2.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_3.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_4.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_5.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_6.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_7.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/edge_flows_8.gpq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_0.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_1.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_2.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_3.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_4.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_5.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_6.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_7.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/odpfc_8.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_0.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_1.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_2.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_3.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_4.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_5.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_6.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_7.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/rerouting_cost_8.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_0.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_0.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_1.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_1.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_2.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_2.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_3.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_3.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_4.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_4.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_5.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_5.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_6.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_6.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_7.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_7.pq`: Columnar geospatial/data parquet output or input dataset.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_8.csv`: Tabular CSV input/output file for model workflow.
- `sandbox/results/rerouting_analysis/revision/30/1/trip_isolations_8.pq`: Columnar geospatial/data parquet output or input dataset.
- `scripts/1_network_flow_model_revision.py`: Script 1: baseline network flow assignment and base outputs.
- `scripts/2_int_analysis.py`: Legacy/alternate Script 2 implementation.
- `scripts/2_intersection_analysis.py`: Script 2: flood-hazard intersection analysis and disrupted links.
- `scripts/3_damage_analysis.py`: Script 3: direct damage estimation from depth + vulnerability curves.
- `scripts/3_postprocess_damage.py`: Post-processing for Script 3 damage outputs.
- `scripts/4_rerouting_and_recovery_scenario_loop.py`: Script 4: rerouting/recovery simulation across scenarios and days.
- `scripts/5_sensitivity_analysis_direct.py`: Script 5A: direct-damage sensitivity analysis.
- `scripts/5_sensitivity_analysis_indirect.py`: Script 5B: indirect/rerouting sensitivity analysis.
- `scripts/DAFNI_NIRD.code-workspace`: Project file.
- `scripts/dafni_plat/demo_baseline flow modelling.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/dafni_plat/demo_damage analysis.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/dafni_plat/demo_traffic flow disruption and rerouting analysis.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/dafni_plat/nird_3_damage_analysis.py`: DAFNI platform-oriented Python workflow script.
- `scripts/dafni_plat/nird_4_rerouting_and_recovery.py`: DAFNI platform-oriented Python workflow script.
- `scripts/dafni_plat/visualise_damage_analysis.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/1_network_flow_model_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/2_intersection_analysis_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/3_damage_analysis_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_batch_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_fixed.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_local.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/4_rerouting_and_recovery_scenario.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/convert_uuid.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/ibis_rerouting_event1.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_event5.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_preprocess.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/ibis_rerouting_preprocess_15.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_preprocess_30.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_preprocess_60.ipynb`: Notebook for exploratory analysis, demonstrations, or experiments.
- `scripts/experiments/ibis_rerouting_scenario.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_disruption.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_distributed.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_osm.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/network_flow_model_revised.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/od_gb_oa_2021.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/od_gb_oa_2021_node.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/od_truncation.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/postprocess_plot.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/postprocess_rerouting_isolation.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/recovery_process_design.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_disruption_damage.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_disruption_maxSpeed.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_network_creation.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/road_network_preprocess.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/experiments/test.py`: Experimental/prototype Python script for scenario testing or method development.
- `scripts/macchub/1_network_flow_model_macchub.py`: Python source script/module used in project workflows.
- `scripts/miraca/1_network_flow_model_miraca.py`: Python source script/module used in project workflows.
- `scripts/nist-rail/1_network_creation.py`: NIST rail workflow step script.
- `scripts/nist-rail/2_network_track_speed.py`: NIST rail workflow step script.
- `scripts/nist-rail/3_estimate_daily_station_entries_exits.py`: NIST rail workflow step script.
- `scripts/nist-rail/4_timetable_origin_destination_pairs.py`: NIST rail workflow step script.
- `scripts/nist-rail/5_rail_od_inputs.py`: NIST rail workflow step script.
- `scripts/nist-rail/6_rail_od_prediction.py`: NIST rail workflow step script.
- `scripts/nist-rail/7_rail_flow_modelling.py`: NIST rail workflow step script.
- `scripts/nist-road/1_network_flow_model_nist.py`: NIST road workflow step script.
- `scripts/organize_spatial_data.ps1`: PowerShell helper for organizing spatial datasets.
- `src/nird/__init__.py`: Python source script/module used in project workflows.
- `src/nird/constants.py`: Python source script/module used in project workflows.
- `src/nird/road.py`: Python source script/module used in project workflows.
- `src/nird/road_capacity.py`: Python source script/module used in project workflows.
- `src/nird/road_functions.py`: Shared flood, damage, and feature-processing utilities.
- `src/nird/road_osm.py`: Python source script/module used in project workflows.
- `src/nird/road_revised.py`: Primary revised road-network modeling module used by scripts 1 and 4.
- `src/nird/road_validation.py`: Python source script/module used in project workflows.
- `src/nird/utils.py`: General helper functions (config loading, shared utilities).
- `tests/test_constants.py`: Unit test coverage for constants module.

</details>