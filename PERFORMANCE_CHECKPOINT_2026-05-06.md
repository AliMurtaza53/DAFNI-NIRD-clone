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
