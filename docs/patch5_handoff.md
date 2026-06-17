# Patch 5 Handoff

## Current Branch And Baseline

- GitHub repo: `https://github.com/AliMurtaza53/DAFNI-NIRD-clone.git`
- Branch: `codex/script2-raster-prefilter-handoff`
- Current working baseline: Patch 5 fused event-candidate writing.
- Model logic status: no Patch 6 implementation; Patch 5 is frozen as the current operational baseline.
- Primary status document: `docs/network_assignment_refactor_status_patch5.md`
- Attempt log: `docs/path_realization_attempt_log.md`

## New Environment Pickup

Use this when resuming from a new IDE or machine:

```powershell
git clone https://github.com/AliMurtaza53/DAFNI-NIRD-clone.git
cd DAFNI-NIRD-clone
git checkout codex/script2-raster-prefilter-handoff
```

Then review these files first:

- `docs/patch5_handoff.md`
- `docs/network_assignment_refactor_status_patch5.md`
- `docs/path_realization_attempt_log.md`
- `docs/assumptions_inputs/README.md`

Expected local data/config assumption in the current working copy:

- `config.json` points to `C:\Users\akothaw\Desktop\data\soge_clusters`
- Outputs are written under `C:\Users\akothaw\Desktop\data\results`

If using another machine, update `config.json` to that machine's data paths before running smoke tests.

## What Patch 5 Solved

The original bottleneck was full OD path-edge realization through global path materialization, especially `UNNEST(path)`/`UNNEST(e_id)` style logic and persistent full `odpfc` output. At full scale this created huge logical intermediates and caused stalls.

Patch 5 keeps the current assignment semantics but writes event-disrupted candidates during streaming realization pass 2. It avoids:

- full `temp_flow_matrix` creation in event-candidate mode,
- full persistent `odpfc` output,
- global path index output,
- post-streaming scan over all OD paths,
- `UNNEST(e_id)` edge-flow fallback.

## Validation Already Completed

Patch 5 20k validation passed exactly against the Patch 4 reference.

- Candidate rows matched.
- OD IDs matched.
- Ordered paths matched.
- Flood/damaged links matched.
- Flow/cost scalar diffs were `0.0`.
- Edge state diffs were `0.0`.
- `temp_edge_flow` was used directly.
- `UNNEST(e_id)` was not triggered.

Validation log:

- `logs/patch5_20k_validate_fused_candidates.log`

## Full-Flow Smoke Runs

### One-Iteration Synthetic Smoke

Completed successfully.

- OD rows processed: `9,678,285`
- Edge rows: `221,214`
- Event candidate rows: `68,211`
- Candidate parts: `2`
- Total runtime: `6539.45s`, about `1h49m`
- Full `odpfc`: not written
- Full path index: not written
- Full path-list `temp_flow_matrix`: not created
- `UNNEST(e_id)`: not triggered

Log:

- `logs/patch5_fullflow_one_iter_fused_event_candidates_synthetic.log`

### Two-Iteration Synthetic Smoke

Completed successfully after the Patch 5 handoff launcher was added.

- Max iterations: `2`
- Iteration 2 OD rows processed: `5,860,740`
- Iteration 2 edge rows: `144,125`
- Iteration 2 candidate rows: `40,693`
- Total candidate parts after run: `2`
- Remaining flow after iteration 2: `287,083.1778912996`
- Total simulation time: `8444.35s`, about `2h20m`
- Full `odpfc`: not written
- `temp_edge_flow`: used directly
- `UNNEST(e_id)`: not triggered

Log:

- `logs/patch5_fullflow_two_iter_fused_event_candidates_synthetic.log`

## Commands Used

Patch 5 baseline smoke launcher:

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\dev_run_patch5_smokes_windows.ps1 -NumChunks 20 -NumCpu 1
```

Placeholder relaunch after log-text cleanup:

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\dev_run_patch5_smokes_windows.ps1 -SkipIter2
```

The launcher opens separate titled PowerShell windows and writes `Tee-Object` logs under `logs/`.

## Placeholder Smoke Status

Real-event smoke placeholder:

- Log: `logs/patch5_real_event_smoke_placeholder.log`
- No real-event model run launched.
- Waiting on actual Script 2/3 damaged-edge parquet.

Script 4 event-candidate loader placeholder:

- Log: `logs/patch5_script4_event_candidate_loader_placeholder.log`
- No Script 4 recovery run launched.
- Waiting on real Patch 5 event-candidate output root.

## Recommended Environment Settings

```powershell
$env:NIRD_PATH_REALIZATION_STRATEGY = "streaming_arrays"
$env:NIRD_DIRECT_DUCKDB_OUTPUTS = "1"
$env:NIRD_BASELINE_PATH_OUTPUT_MODE = "event_candidates"
$env:NIRD_CREATE_FULL_TEMP_FLOW_MATRIX = "0"
$env:NIRD_ODPFC_OUTPUT_MODE = "skip"
$env:NIRD_WRITE_FULL_ODPFC = "0"
$env:NIRD_COMBINE_EVENT_CANDIDATE_PARTS = "0"
$env:NIRD_EVENT_DAMAGED_EDGES_PATH = "<event damaged edges parquet>"
```

Use an explicit bounded iteration setting for smoke tests:

```powershell
$env:NIRD_MAX_FLOW_ITERATIONS = "1"
$env:NIRD_MAX_FLOW_ITERATIONS = "2"
```

## Known Remaining Bottleneck

The main remaining bottleneck is stable `od_id` assignment. In the one-iteration full-flow smoke this took about `37.9 min`.

Do not implement Patch 6 now unless explicitly requested. The deferred Patch 6 idea is to assign `od_id` during `temp_flow_matrix_input` insertion and avoid a post-hoc `ROW_NUMBER()` or full-table rewrite. This needs careful treatment of deterministic vs unordered multiprocessing behavior.

## Before Unrestricted Production

Complete these gates before unrestricted production:

1. Use Patch 5 as the baseline; do not add Patch 6 casually.
2. Run one real-event smoke once Script 2/3 damaged-edge outputs are available.
3. Run Script 4 recovery smoke using the Patch 5 event-candidate loader.
4. Confirm logs show `temp_edge_flow` direct loading.
5. Confirm logs show no `UNNEST(e_id)` fallback.
6. Confirm no full `odpfc`, global path index, or full path-list `temp_flow_matrix` is created in event-candidate mode.
