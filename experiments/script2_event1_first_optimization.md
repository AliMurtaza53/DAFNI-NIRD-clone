# Script 2 Event 1 — First Optimization Experiment

## Goal
Reduce redundant work in `scripts/2_intersection_analysis.py` before deeper optimization.

## Change
- Removed a duplicate `gpd.read_parquet(road_links_path)` load in the event-processing path.
- Reused the road-links frame already loaded for the event, so the candidate run avoids one full disk read.

## Baseline
- Profile: `profiles/2_intersection_analysis_depth30_event1.prof`
- Summary: `profiles/summary/2_intersection_analysis_depth30_event1_top.csv`
- Plot: `experiments/comparisons/2_intersection_analysis_depth30_event1_top_top20.png`

## Candidate
- Profile target: `profiles/2_intersection_analysis_depth30_event1_candidate.prof`
- Scenario: event 1
- Depth: 30 cm

## Comparison Plan
1. Run the optimized Script 2 on event 1 under `cProfile`.
2. Copy the profile into `experiments/candidates/script2_event1_first_optimization/` with metadata.
3. Regenerate summary CSVs.
4. Plot baseline vs candidate using the same event and depth.

## Result
- Baseline total runtime: ~2044.70 s
- Candidate v5 total runtime: ~2055.40 s
- Outcome: **slight regression** (~0.5%), not an improvement
- The vectorized rewrite reduced some row-wise work, but the end-to-end runtime is still dominated by the geometry intersection path.

## Interpretation
- Removing the duplicate read was too small relative to the main bottleneck.
- Vectorizing `max_speed` and damage-level assignment helped reduce row-wise pandas work, but not enough to overcome the heavy raster/intersection cost.
- The next optimization should target geometry intersection / split logic or reduce repeated DataFrame/GDF construction around those calls.

## What to look for
- Any reduction in file I/O time near the top of the profile.
- Whether `gpd.read_parquet` or downstream `pandas` construction costs shrink.
- Whether the major bottleneck remains geometry intersection work.
