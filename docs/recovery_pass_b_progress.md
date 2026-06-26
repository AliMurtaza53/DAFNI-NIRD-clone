# CONUS Recovery Pass B Progress and Production Tuning

This document records the aborted full-convergence Pass B run (June 17–18, 2026),
the decision to switch to a bounded 2-iteration demo pipeline, and follow-up tuning
ideas for production runs.

## Run context

| Item | Value |
| --- | --- |
| Branch | `codex/script2-raster-prefilter-handoff` |
| Data root | `C:\Users\akothaw\Desktop\data\soge_clusters` |
| Results root | `C:\Users\akothaw\Desktop\data\results` |
| Variant | `revision` |
| Depth / events | depth `30`, toy hazards events `1`, `2`, `3` |
| Pass B mode | Patch 5 `event_candidates` + `streaming_arrays` |
| Aborted setting | `NIRD_MAX_FLOW_ITERATIONS=0` (unbounded) |
| Replacement setting | `MaxFlowIterations=2` (Patch 5 validated smoke) |

## Completed before Pass B switch

| Step | Status | Notes |
| --- | --- | --- |
| Pass A (baseline Script 1) | Done | `edge_flows.gpq` from June 4 baseline run |
| Script 2 (events 1–3) | Done | Projection fixes applied; no snail segfault |
| Export damaged edges | Done | 372 rows → `tables/event_damaged_edges_depth30_toy.pq` |
| Script 3 + postprocess | Done | `damage_analysis/revision/*_with_damage_values.csv` |

## Aborted Pass B (`MaxFlowIterations=0`)

**Log:** `logs/20260617_183501_passB_script1_event_candidates.log`

**Started:** 2026-06-17 ~18:35  
**Stopped:** manually before natural convergence (after iteration 17 started)

### Convergence controls

```text
max_iterations=unbounded
min_progress_rel=1e-06
stagnant_limit=3
```

Convergence requires **three consecutive iterations** with `progress_rel < 1e-06`.
The log never reached `stagnant_iterations=1/3`; progress remained hundreds to
thousands of times above threshold.

### Iteration history

| Iter | progress_rel | stagnant |
| --- | --- | --- |
| 1 | 78.34175227% | 0/3 |
| 2 | 5.11485826% | 0/3 |
| 3 | 1.68483514% | 0/3 |
| 4 | 3.34832742% | 0/3 |
| 5 | 1.45692963% | 0/3 |
| 6 | 1.37782566% | 0/3 |
| 7 | 2.13699503% | 0/3 |
| 8 | 0.98277090% | 0/3 |
| 9 | 0.76294656% | 0/3 |
| 10 | 2.34325281% | 0/3 |
| 11 | 0.83031735% | 0/3 |
| 12 | 0.48866506% | 0/3 |
| 13 | 0.20474698% | 0/3 |
| 14 | 0.13319791% | 0/3 |
| 15 | **0.04269378%** | 0/3 |
| 16 | 0.14705501% | 0/3 |
| 17 | 0.19336375% | 0/3 |
| 18 | started, not completed | — |

**Best recent REL:** iteration 15 at `4.27e-4` (~**427×** above `1e-6` threshold).

### Observed per-iteration wall time

| Phase | Early iters (1–10) | Later iters (11–17) |
| --- | --- | --- |
| Full iteration | ~65–185 min | ~48–80 min |
| Least-cost paths (iter 17) | — | ~11 min (1.55M path rows) |

Later iterations were faster because fewer OD rows remained in `remain_od`.

### Why the run was stopped

Full strict convergence on CONUS (~9.7M ODs) was projected to take **many more
hours to days** with continued REL bouncing. For advisor/demo panels and Script 4
validation, the team switched to **Patch 5 two-iteration Pass B** (~2–4 h),
documented in `docs/patch5_handoff.md`.

## Bounded demo relaunch (current plan)

```powershell
cd C:\Users\akothaw\Desktop\DAFNI-NIRD-clone
.\scripts\run_patch5_recovery_conus.ps1 `
  -SkipPassA -SkipScript2 -SkipScript3 `
  -MaxFlowIterations 2 `
  -RunVizOdpfcSidecar `
  -RunNotebook
```

Launcher safeguards added:

- Backs up Pass A `edge_flows.gpq` → `edge_flows_pass_a.gpq` before Pass B
- Clears stale `event_disrupted_candidates/` before Pass B
- Viz sidecar sets `NIRD_COMBINE_ODPFC_PARTS=1` so `odpfc.pq` is produced for panels
- Notebook uses `scripts/visualizations/viz_data_loaders.py` for odpfc/edge-flow resolution

## Production tuning ideas

### 1. Iteration policy

| Goal | Setting |
| --- | --- |
| Demo / advisor panels | `MaxFlowIterations=2` (Patch 5 validated) |
| Faster stop | `NIRD_MIN_FLOW_PROGRESS_REL=1e-5`, `NIRD_STAGNANT_ITERATIONS=2` |
| Full production convergence | `MaxFlowIterations=0` + overnight/multi-day window |

### 2. Parallelization (Script 1)

Current recovery launcher defaults: `-NumChunks 20 -NumCpu 1`.

| Knob | Effect |
| --- | --- |
| `-NumCpu` | Parallel least-cost path pools; try `4` or `8` on a workstation |
| `-NumChunks` | Path-realization chunk count; tune with CPU count (avoid tiny chunks) |
| Fast SSD | DuckDB temp under `soge_clusters/dbs/` benefits from local NVMe |

Patch 5 smoke used `NumChunks=20`, `NumCpu=1`. Multi-CPU speedup is most visible in
least-cost path allocation (~30 min/iter in one-iter smoke).

### 3. Patch 6 (deferred code change)

Documented in `docs/network_assignment_refactor_status_patch5.md`:

- Assign stable `od_id` during `temp_flow_matrix_input` insertion
- Avoid post-hoc full-table `ROW_NUMBER()` rewrite (~**38 min/iter** in one-iter smoke)
- Validate against Patch 5 20k reference before any production use

### 4. Script 2 / Script 4 (already enabled in launcher)

```powershell
$env:NIRD_ENABLE_SPLIT_CACHE = "1"          # Script 2 split cache (~75% faster)
$env:NIRD_VECTORIZE_PATH_PARSING = "1"      # Script 4 path parsing cache
```

Script 4 events 1–3 can also run in parallel on separate terminals after Pass B.

### 5. Viz and flow diagnostics

| Choice | Rationale |
| --- | --- |
| `VizSampleStride=1` (default) | Step 1 uses full `faf5_od_matrix.pq` demand (~9.7M OD pairs); no 1/500 subsample |
| `RunVizOdpfcSidecar` (optional) | Only needed for path-distance plots; expensive at full scale |
| `edge_flows_pass_a.gpq` | Step 1 V/C maps use Pass A baseline, not 1-iter sidecar flows |
| `faf5_sctg_daily_trucks.pq` | Built by `scripts/build_faf5_sctg_summary.py` from county or regional FAF |
| `Desktop/data/faf5_data` | Local FAF5 root (sibling of `soge_clusters`); truck county factors live here |
| Consolidated USD damage | `prepare_damage_for_viz()` pairs C5/C6 curves; workbook units are MUSD |

Step 1 flow histograms and top-OD panels read the full assignment demand table. The optional
ODPFC sidecar remains available for assigned-path distance plots when explicitly enabled.

## Related docs

- `docs/patch5_handoff.md` — Patch 5 baseline and smoke timings
- `docs/network_assignment_refactor_status_patch5.md` — Patch 6 TODO
- `docs/geo_projection_conus.md` — Script 2 projection checklist
- `scripts/run_patch5_recovery_conus.ps1` — recovery orchestration
