# Path Realization Attempt Log

This log tracks the NIRD network-assignment path-realization bottleneck work. The current objective is to preserve existing capacity-constrained all-or-nothing assignment semantics while replacing global path-edge materialization with a streaming/two-pass method.

## Attempts And Outcomes

| Date | Attempt | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-06-04 | Direct DuckDB output export for script 1 | Useful, but not sufficient | Avoided loading large `odpfc`/isolation outputs back into pandas. This improves final output writing, but does not remove the path-realization bottleneck. |
| 2026-06-04 | Option 1 sampled direct-output comparison | Passed after isolation filter fix | Sampled outputs matched after excluding self-pair and zero-flow isolation rows consistently. |
| 2026-06-05 | Chunked DuckDB path expansion | Stalled at full scale | Still relied on repeated `UNNEST(path)` over the full OD path set. Full run grew large DuckDB/temp artifacts and did not complete acceptably. |
| 2026-06-06 | Legacy compact SQL path aggregation | Stalled after edge total table | It avoided physically creating `exploded_paths`, but still made DuckDB process huge global `CROSS JOIN UNNEST(path)` aggregates. It computed compact edge totals, then stalled during subsequent OD path-cost/adjustment work. |
| 2026-06-06 | Streaming arrays implementation | Pending validation | New branch streams compact OD path rows in two passes, accumulates edge candidate and adjusted flows in NumPy arrays, and writes `temp_flow_matrix` plus `temp_edge_flow` without a global exploded path table. |
| 2026-06-06 | First dev harness launch | Failed harness check | The sampler cast OD node IDs to strings, but the igraph node names in this network are integers. This produced zero valid paths and no `temp_flow_matrix`. The harness now follows the production dtype pattern. |
| 2026-06-06 | Streaming vs legacy smoke test, 10 OD sample | Passed | Same OD keys, same ordered path lists, same edge flow keys, same edge flows, and only roundoff-level path-cost differences. |
| 2026-06-06 | Streaming vs legacy 1k and 20k visible-window comparisons | Passed | 1k and 20k reports passed all checks. At 20k: 16,783 valid OD paths, 3,217 isolated rows, zero path mismatches, max OD flow diff 0, max edge-flow diff `4.55e-13`. |
| 2026-06-06/07 | Full-scale streaming path realization | Completed streaming, then stalled downstream | Full run reached `Streaming path realization complete: 9678285 OD rows, 221214 edge rows`, then stalled with zero CPU/log/DB growth. This identified the next bottleneck as post-realization OD path output materialization into persistent DuckDB `odpfc`. |
| 2026-06-07 | Patch 2: post-realization direct-output decoupling, 20k validation | Passed | `iteration_parquet` wrote one `odpfc_parts/odpfc_iter_000001.pq` part with 16,776 rows, combined output matched `duckdb_table` exactly, and logs confirm streaming loaded `temp_edge_flow` directly with no `UNNEST(e_id)`. |
| 2026-06-07 | Patch 2: full-flow one-iteration smoke | In progress | Visible window launched with `streaming_arrays + iteration_parquet + combine off + max_iterations=1`. It is currently in least-cost path allocation; this is the run that should prove the code gets past the previous post-realization stall at full scale. |
| 2026-06-08 | Patch 3: 20k full_odpfc vs path_index validation | Correct but poor scaling | Validation passed: 16,776 reconstructed OD paths matched legacy full_odpfc exactly, affected OD IDs/flood links matched for 50 damaged-edge test, and pre-event costs matched. However, the 20k path index wrote 15,472,112 rows across 20 parts and was larger than full_odpfc at this scale. |
| 2026-06-08 | Patch 3: full-flow one-iteration path_index smoke | Stopped before output | The run was stopped during least-cost path allocation after the 20k test showed path_index would likely expand to billions of rows at full scale. This avoided creating an enormous path-index artifact. |
| 2026-06-08 | Patch 4: event-filtered disrupted candidates | Implementation staged | New `event_candidates` mode writes full path rows only for OD paths touching synthetic or real event damaged edges. This avoids full `odpfc` and global `path_index` by default. Visible-window runs are staged for 20k legacy reference, 20k event candidates, validation, and full-flow one-iteration synthetic smoke. |
| 2026-06-08 | Patch 5: fused event-candidate writing | 20k validation passed; full-flow smoke running | Fused mode writes event candidates inside streaming pass 2 and skips full `temp_flow_matrix` when `NIRD_CREATE_FULL_TEMP_FLOW_MATRIX=0`. The 20k Patch 4 reference vs fused comparison passed exactly for candidate rows, paths, flood links, scalar costs, edge flow state, and pre-event costs. Full-flow one-iteration fused smoke launched in a visible PowerShell window. |

## Current Diagnosis

The problem is not only shortest-path calculation. The expensive step is realizing roughly 9.7 million OD paths into OD-edge incidences. If average path length is 40-80 edges, the logical intermediate can reach hundreds of millions of rows before grouping or writing.

The current model still needs:

- OD path edge lists and path costs,
- unadjusted candidate edge totals,
- OD bottleneck adjustment ratios,
- adjusted OD flows,
- adjusted edge flows for road-link updates.

It does not need a full persistent `exploded_paths` table to compute those values.

## Validation Gate

The controlled 20,000 OD comparison passed on 2026-06-06. Full-scale production can now be tested with `NIRD_PATH_REALIZATION_STRATEGY=streaming_arrays`, but it should still run in a visible PowerShell window with a dedicated log because the full-scale runtime/memory profile has not been proven yet.

The 20,000 OD validation checked:

- same OD key set,
- same ordered path lists,
- near-identical adjusted OD flows and path costs,
- near-identical edge adjusted flows,
- same assigned-flow accounting,
- no full-scale `exploded_paths` table in streaming mode.

## Current Test Assets

- `scripts/dev_compare_path_realization.py`
- `scripts/dev_run_path_realization_windows.ps1`
- `scripts/dev_validate_post_realization_patch2.py`
- `scripts/dev_run_post_realization_patch2_windows.ps1`
- expected logs under `logs/path_realization_*.log`
- expected Patch 2 logs under `logs/patch2_*.log`
- expected reports under `results/dev/path_realization_comparison_*.json`
- expected Patch 2 reports under `experiments/patch2_post_realization/`
