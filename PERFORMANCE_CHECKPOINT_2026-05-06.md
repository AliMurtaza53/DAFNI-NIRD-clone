# Performance Checkpoint (2026-05-06)

## Scope
This checkpoint finalizes:
- **Script 2** optimization choice: **Candidate C (split cache)**.
- **Script 4** optimization: **cached batch path parsing** controlled by `NIRD_VECTORIZE_PATH_PARSING=1`.

## Script 2 — Final choice: Candidate C
Implementation file: `scripts/2_intersection_analysis.py`

### What changed
- Added split-result cache for repeated geometry/raster split operations.
- Cache key includes edge IDs, grid metadata, transform, and simplify tolerance.
- Controlled by env flag:
  - `NIRD_ENABLE_SPLIT_CACHE=1`

### Profiling snapshot (event 1, depth 30)
From profile summaries:
- Baseline current total cumtime: **3481.32 s**
- Candidate C total cumtime: **854.76 s**
- Improvement: **~75.4% faster**

## Script 4 — Implemented optimization
Implementation file: `scripts/4_rerouting_and_recovery_scenario_loop.py`

### What changed
- Added cached parser for stringified path payloads with `@lru_cache`.
- Added batch series parser `to_edge_id_list_vectorized()` that:
  - parses unique string payloads once,
  - maps parsed values back to full Series,
  - falls back to row parser for non-string values.
- Controlled by env flag:
  - `NIRD_VECTORIZE_PATH_PARSING=1`

### Profiling snapshot (event 1, depth 30, chunks=1, cpu=1)
Using `main()` cumulative time for apples-to-apples run logic:
- Baseline final `main` cumtime: **13.83 s**
- Optimized (AB final) `main` cumtime: **13.35 s**
- Improvement: **~3.5% faster**

> Note: top-level module cumtime can fluctuate due import/cold-start overhead; `main()` is the preferred execution-path metric here.

## Repro commands
```powershell
# Script 2 (Candidate C)
$env:NIRD_ENABLE_SPLIT_CACHE="1"
.\.venv\Scripts\python.exe scripts\2_intersection_analysis.py 30 1

# Script 4 baseline
$env:NIRD_VECTORIZE_PATH_PARSING="0"
.\.venv\Scripts\python.exe -m cProfile -o profiles\4_rerouting_candidate_baseline_final.prof scripts\4_rerouting_and_recovery_scenario_loop.py 30 1 1 1

# Script 4 optimized
$env:NIRD_VECTORIZE_PATH_PARSING="1"
.\.venv\Scripts\python.exe -m cProfile -o profiles\4_rerouting_candidate_AB_final.prof scripts\4_rerouting_and_recovery_scenario_loop.py 30 1 1 1
```

## Artifacts used
- `profiles/summary/2_intersection_analysis_depth30_event1_candidate_baseline_current_top.csv`
- `profiles/summary/2_intersection_analysis_depth30_event1_candidate_C_cache_top.csv`
- `profiles/summary/4_rerouting_candidate_baseline_final_top.csv`
- `profiles/summary/4_rerouting_candidate_AB_final_top.csv`

## Follow-up Candidates: Baseline Path Realization

### Question
Script 4 still needs OD-level baseline paths. It does not directly need
`baseline.duckdb`, but it needs either:

- `results/disruption_analysis/<variant>/od/odpfc_<depth>_<event>.pq`, or
- the fallback `results/base_scenario/<variant>/odpfc.pq`.

The current Script 2 path does not create the event-specific OD file, so Script 4
normally falls back to the full baseline `odpfc.pq`.

### Option 1 candidate
Files:

- `scripts/1_network_flow_model_revision.py`
- `scripts/1_network_flow_model_revision_option1_direct_duckdb.py`
- `src/nird/road_revised.py`

Controls:

- `NIRD_DIRECT_DUCKDB_OUTPUTS=1`
- `NIRD_DUCKDB_CHUNKED_PATH_EXPANSION=0` by default
- `NIRD_BASE_SCENARIO_OUT_DIR=<candidate output dir>`

What it tests:

- writes `trip_isolations.pq` and `odpfc.pq` directly from DuckDB instead of
  loading the whole `odpfc` table into pandas;
- leaves DuckDB path expansion on the original single-query path by default.

`NIRD_DUCKDB_CHUNKED_PATH_EXPANSION=1` remains available as an experimental
switch, but it should not be used for full runs yet. A full sampled-to-national
attempt on 2026-06-04 produced a ~20 GB DuckDB file plus temp spill and did not
complete overnight, because the chunked branch still materializes very large
per-OD edge-flow intermediates.

Follow-up fix:

- `NIRD_DUCKDB_COMPACT_PATH_AGG=1` is now the default for table-backed path
  realization.
- This path avoids materializing the giant `exploded_paths` table. It aggregates
  directly from `UNNEST(path)` into compact tables:
  - edge-level total flow/capacity,
  - OD-level path cost/list,
  - OD-level capacity adjustment.
- The old materialized `exploded_paths` branch remains available with
  `NIRD_DUCKDB_COMPACT_PATH_AGG=0` for debugging only.

### Script 1 path-realization strategy matrix

The path-realization bottleneck should now be tested as a strategy matrix rather
than a single patch.

Environment switch:

- `NIRD_PATH_REALIZATION_STRATEGY=compact_sql`
- `NIRD_PATH_REALIZATION_STRATEGY=duckdb_chunked_compact`
- `NIRD_PATH_REALIZATION_STRATEGY=pandas_chunked`
- `NIRD_PATH_REALIZATION_STRATEGY=legacy_materialized`

Options:

- Option 1 / default: `compact_sql`
  - Direct SQL aggregates from `UNNEST(path)` into compact tables.
  - Scans the path-edge expansion multiple times but does not store the giant
    exploded table.
- Option 2: `duckdb_chunked_compact`
  - Adds row numbers, processes bounded DuckDB row ranges, and appends compact
    edge/OD aggregates.
  - Intended fallback if one huge SQL aggregate still hangs or spills.
- Option 3: `pandas_chunked`
  - Pulls bounded chunks into pandas, explodes each chunk, writes compact
    aggregates back to DuckDB.
  - Expected to be slower, but easiest to reason about and memory-bound by chunk
    size. Tune with `NIRD_PANDAS_PATH_CHUNK_SIZE` if needed.
- Legacy: `legacy_materialized`
  - Original giant `exploded_paths` table.
  - Use only as a reference on small samples.

Visible-window matrix command for a bounded smoke test:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\launch_script1_strategy_matrix.ps1 `
  -NumChunks 20 `
  -NumCpu 1 `
  -SampleStride 500 `
  -MaxFlowIterations 1
```

Then compare profiles:

```powershell
& "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe" tools\compare_profiles.py `
  --profiles_dir experiments\option_profiles `
  --out_dir experiments\option_profiles\summary
```

Recommended full-run escalation after the smoke test:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\launch_script1_profile_window.ps1 `
  -NumChunks 20 `
  -NumCpu 1 `
  -SampleStride 1 `
  -MaxFlowIterations 1 `
  -RunName script1_option2_full_iter1 `
  -PathStrategy duckdb_chunked_compact
```

If option 2 still hangs/spills, try option 3 with a smaller pandas chunk:

```powershell
$env:NIRD_PANDAS_PATH_CHUNK_SIZE="25000"
powershell.exe -ExecutionPolicy Bypass -File .\scripts\launch_script1_profile_window.ps1 `
  -NumChunks 20 `
  -NumCpu 1 `
  -SampleStride 1 `
  -MaxFlowIterations 1 `
  -RunName script1_option3_full_iter1 `
  -PathStrategy pandas_chunked
Remove-Item Env:\NIRD_PANDAS_PATH_CHUNK_SIZE
```

This remains behaviorally closest to the current workflow because it still
creates the full baseline path database.

### Option 5 candidate
File:

- `scripts/4_prepare_disrupted_od_option5.py`

What it tests:

- loads damaged edges from Script 2's `road_links_<event>.gpq`;
- computes baseline least-cost paths from the OD matrix;
- keeps only OD paths that touch damaged edges;
- writes the event-specific `odpfc_<depth>_<event>.pq` consumed by Script 4.

This is a targeted replacement for Script 4's full baseline `odpfc.pq`
dependency. It does not replace the need for baseline `edge_flows.gpq`, which
Script 2 and Script 4 still use as the base network state.

Option 5 is expected to be attractive when the event footprint is small. It is
less faithful to the full iterative capacity-feedback baseline because it uses
current least-cost paths for filtering rather than reproducing every assigned
baseline path row.

### Profile runner
Files:

- `experiments/profile_options_1_vs_5.py`
- `scripts/profile_script1_options.ps1`
- `scripts/launch_script1_profile_window.ps1`

Visible-window full Script 1 profile command:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\launch_script1_profile_window.ps1 `
  -NumChunks 20 `
  -NumCpu 1 `
  -SampleStride 1 `
  -MaxFlowIterations 1 `
  -RunName script1_default_full
```

This opens a separate PowerShell window, writes a visible log under `logs\`, and
writes the profile/output artifacts under `experiments\option_profiles\`.

Script-1-only comparison command:

```powershell
.\scripts\profile_script1_options.ps1 `
  -NumChunks 20 `
  -NumCpu 1 `
  -SampleStride 500 `
  -MaxFlowIterations 1
```

This writes baseline and option-1 outputs under
`experiments\option_profiles\` so comparison runs do not overwrite the main
`results\base_scenario\<variant>` artifacts.

### Script 1 option-1 profile result (2026-06-04)
Command:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\profile_script1_options.ps1 `
  -NumChunks 20 `
  -NumCpu 1 `
  -SampleStride 500 `
  -MaxFlowIterations 1
```

Artifacts:

- `experiments/option_profiles/script1_baseline.prof`
- `experiments/option_profiles/script1_option1_direct_duckdb.prof`
- `experiments/option_profiles/summary/script1_baseline_top.csv`
- `experiments/option_profiles/summary/script1_option1_direct_duckdb_top.csv`

Observed cProfile total time:

- Baseline: `640.618 s`
- Option 1: `259.796 s`
- Improvement: `~59.4% faster`

Top cumulative bottleneck in both runs remained shortest-path solving:

- Baseline `get_shortest_paths`: `256.604 s`
- Option 1 `get_shortest_paths`: `250.326 s`

The optimization therefore did not make pathfinding itself faster; it removed
most of the post-path overhead from full `odpfc` export/materialization.

Output check on the sampled run:

- `odpfc.pq`: both runs wrote `19,351` rows with matching flow sum
  (`3319.617014275888`).
- `edge_flows.gpq`: both runs wrote similarly sized outputs.
- `trip_isolations.pq`: direct DuckDB output initially included self-pair
  isolated rows that legacy Script 1 filtered out. This was patched in
  `src/nird/road_revised.py` by applying the same `origin_node != destination_node`
  and `flow > 0` filter in the DuckDB `COPY` path. Rerun option 1 after this
  patch for final output-equivalence confirmation.

Smoke profile command:

```powershell
New-Item -ItemType Directory -Force -Path experiments\option_profiles | Out-Null

<python> experiments/profile_options_1_vs_5.py `
  --depth-key 30 `
  --event-key 1 `
  --sample-stride 500 `
  --max-flow-iterations 1 `
  --damaged-edge-sample 100
```

Fuller event-profile command, after Script 2 has created
`road_links_<event>.gpq`:

```powershell
New-Item -ItemType Directory -Force -Path experiments\option_profiles | Out-Null

<python> experiments/profile_options_1_vs_5.py `
  --depth-key 30 `
  --event-key 1 `
  --sample-stride 1 `
  --max-flow-iterations 1
```

Outputs:

- `experiments/option_profiles/timings.csv`
- `experiments/option_profiles/option1_direct_duckdb.prof`
- `experiments/option_profiles/option1_direct_duckdb_summary.txt`
- `experiments/option_profiles/option5_event_prefilter.prof`
- `experiments/option_profiles/option5_event_prefilter_summary.txt`

### Current execution note
This workspace shell only exposed Microsoft Store Python aliases and unrelated
OneDrive Python environments without the required geospatial dependencies, so
the profile runner could not be executed here. Run the commands above with the
project Conda or virtualenv interpreter that has `pandas`, `geopandas`, `duckdb`,
and `igraph` installed.
