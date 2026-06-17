# Network Assignment Refactor Status: Patch 5 Baseline

Patch 5 is frozen as the current working baseline for near-term network-assignment runs. Do not implement Patch 6 unless it is explicitly requested later.

## Original Bottleneck

The original assignment workflow stalled during path realization. It expanded every OD path into path-edge rows using global `CROSS JOIN UNNEST(path)` style logic, then aggregated those rows back into OD costs and edge flows. At full scale, roughly 9.7 million OD paths can imply hundreds of millions to billions of logical OD-edge incidences, causing DuckDB spill, large temporary artifacts, and apparent hangs.

The model semantics that must be preserved are still the existing capacity-constrained all-or-nothing assignment semantics. User-equilibrium assignment is not part of this refactor.

## Patch Summary

| Patch | Change | Outcome |
| --- | --- | --- |
| Patch 1 | Added streaming/two-pass path realization. | Avoided global `exploded_paths` materialization and completed full-scale streaming realization. |
| Patch 2 | Decoupled post-realization OD output from mandatory persistent DuckDB `odpfc` insertion. | Avoided the post-streaming `odpfc` table stall and introduced direct Parquet/skip output modes. |
| Patch 3 | Tested global `path_index` output. | Correct, but rejected as a full-scale default because row count still scales with OD paths times path length. |
| Patch 4 | Added event-filtered disrupted-candidate output. | Wrote only OD paths touching damaged-event edges instead of writing all baseline OD paths. |
| Patch 5 | Fused event-candidate writing into streaming pass 2. | Avoided full `temp_flow_matrix` materialization and avoided a post-streaming scan over all OD paths. This is the current baseline. |

## Patch 5 Validation Results

The 20k Patch 4 reference vs Patch 5 fused-candidate validation passed exactly.

- Candidate row counts matched.
- OD ID sets matched.
- Ordered paths matched.
- Flood/damaged links matched.
- Cost and flow scalar diffs were `0.0`.
- Edge state diffs were `0.0`.
- `temp_edge_flow` was used directly.
- `UNNEST(e_id)` was not triggered.
- Validation result: `passed = true`.

Validation log:

- `logs/patch5_20k_validate_fused_candidates.log`

## Full-Flow One-Iteration Timing

The Patch 5 full-flow one-iteration synthetic-event smoke completed successfully.

Key results:

- OD path rows processed: `9,678,285`
- Edge rows: `221,214`
- Event candidates written: `68,211`
- Candidate output parts: `2`
- Full `odpfc` written: no
- Global path index written: no
- Full path-list `temp_flow_matrix` created: no
- Candidate writing fused into streaming pass 2: yes
- Total runtime: `6539.45` seconds, about `1h49m`

Timing breakdown:

- Least-cost path allocation: `1823.97s`, about `30.4 min`
- Stable `od_id` assignment: about `37.9 min`
- Streaming pass 1: `818.23s`, about `13.6 min`
- Streaming pass 2: `1477.86s`, about `24.6 min`
- Candidate write time inside pass 2: `10.50s`
- Cleanup: about `1.7 min`

Full-flow smoke log:

- `logs/patch5_fullflow_one_iter_fused_event_candidates_synthetic.log`

## Recommended Environment Settings

Use these settings for the current Patch 5 baseline:

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

Keep `NIRD_MAX_FLOW_ITERATIONS` explicit during smoke testing:

```powershell
$env:NIRD_MAX_FLOW_ITERATIONS = "1"  # already passed
$env:NIRD_MAX_FLOW_ITERATIONS = "2"  # next bounded smoke
```

Do not run unrestricted production until the acceptance criteria below pass.

## Known Remaining Bottleneck

The remaining major bottleneck is stable `od_id` assignment. In the full-flow one-iteration smoke, this step took about `37.9 min`.

Likely cause:

- `od_id` is assigned after `temp_flow_matrix_input` has already been written.
- This likely forces a full-table pass or rewrite over roughly 9.7 million OD rows.
- The cost is independent of the fused event-candidate write, so Patch 5 does not remove it.

This is not currently blocking because Patch 5 makes the workflow operational, but it is the clearest next optimization target.

## Deferred Patch 6 TODO

Patch 6 should not be implemented now. When explicitly requested later, the TODO is:

- Assign `od_id` during `temp_flow_matrix_input` insertion.
- Avoid post-hoc `ROW_NUMBER()` or other full-table rewrite logic.
- Decide whether OD IDs must be deterministic across multiprocessing runs.
- If deterministic IDs are needed, preassign OD IDs before multiprocessing or consume ordered results.
- If unordered multiprocessing is acceptable, document that `od_id` is stable only within a run.
- Update streaming realization to consume preassigned `od_id`.
- Validate Patch 6 against the frozen Patch 5 baseline on 20k samples.
- Re-run a full-flow one-iteration synthetic smoke before any production use.

## Acceptance Criteria Before Unrestricted Production

Before unrestricted multi-iteration production, complete:

1. 20k validation against Patch 4 or a stored Patch 5 reference.
2. Full-flow one-iteration event-candidate smoke.
3. Full-flow two-iteration synthetic event-candidate smoke.
4. One real-event smoke using actual Script 2/3 damaged-edge outputs.
5. Script 4 recovery smoke using the event-candidate loader.
6. Confirm logs show `temp_edge_flow` direct loading and no `UNNEST(e_id)` fallback.
7. Confirm no full `odpfc`, global path index, or full path-list `temp_flow_matrix` is created in Patch 5 event-candidate mode.

## Smoke Launchers

Patch 5 baseline smoke launcher:

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\dev_run_patch5_smokes_windows.ps1
```

This opens separate titled PowerShell windows and writes logs under `logs/`.
