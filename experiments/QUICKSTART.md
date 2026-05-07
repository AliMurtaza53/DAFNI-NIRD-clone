# Experiments Structure & Quick Start

## What Changed

Your experiment infrastructure now has **clear structure** to compare baseline vs optimized code:

```
experiments/
├── baselines/
│   └── script2_event1_baseline/          # Baseline: event 1, no changes
│       ├── metadata.json                 # {exp_id, branch, commit, timestamp, description}
│       ├── 2_intersection_analysis_depth30_event1.prof    # Raw cProfile output
│       ├── 2_intersection_analysis_depth30_event1.log     # Execution logs
│       └── summary.csv                   # Top functions (cumtime)
├── candidates/
│   └── script2_event1_optimized_caching/ # Candidate: event 1 with optimization X
│       ├── metadata.json
│       ├── script2_event1_opt.prof
│       ├── script2_event1_opt.log
│       └── summary.csv
└── comparisons/
    └── summary_vs_*.png                  # Clean comparison plot + delta CSV
```

## Key Improvements to Plotting

The new `tools/plot_profile_comparison.py`:

✅ **Short function names**: Strips file paths, shows only `module:function`  
✅ **Top-N focus**: Shows only top 20 slowest functions (by cumtime)  
✅ **Color coding**: Green bars = faster (improvement), Red bars = slower (regression)  
✅ **Delta table**: CSV with % change for each function  
✅ **Clean title & legend**: Minimal clutter

Example output from test run:
- Plot: [experiments/comparisons/summary_vs_2_intersection_analysis_depth30_event2_top.png](experiments/comparisons/summary_vs_2_intersection_analysis_depth30_event2_top.png)
- Delta CSV: [experiments/comparisons/summary_vs_2_intersection_analysis_depth30_event2_top_delta.csv](experiments/comparisons/summary_vs_2_intersection_analysis_depth30_event2_top_delta.csv)

## Quick Start: Run an Experiment

### 1. Establish Baseline (DONE)

Already created: `experiments/baselines/script2_event1_baseline/`

View metadata:
```bash
cat experiments/baselines/script2_event1_baseline/metadata.json
```

### 2. Implement Optimization

Edit target code, e.g., `scripts/2_intersection_analysis.py`:
```python
# Add caching, reduce geometry precision, parallelize raster ops, etc.
```

Commit:
```bash
git add -A
git commit -m "opt: add caching to intersections_with_damage"
```

### 3. Re-profile with Candidate

```bash
python -m cProfile -o profiles/script2_event1_optimized.prof scripts/2_intersection_analysis.py 30 1 2>&1 | tee profiles/script2_event1_optimized.log
```

### 4. Save as Candidate

```bash
python experiments/experiment_tracker.py --action save_profile \
  --profile_path profiles/script2_event1_optimized.prof \
  --exp_dir experiments/candidates/script2_event1_optimized_caching \
  --exp_id "script2_event1_optimized_caching" \
  --description "Optimization: add caching & merge minimization"
```

### 5. Extract Summary

```bash
python tools/compare_profiles.py --profiles_dir profiles --out_dir profiles/summary
# (This will regenerate *_top.csv files)

cp profiles/summary/script2_event1_optimized_top.csv experiments/candidates/script2_event1_optimized_caching/summary.csv
```

### 6. Compare & Plot

```bash
python tools/plot_profile_comparison.py \
  --baseline experiments/baselines/script2_event1_baseline/summary.csv \
  --candidate experiments/candidates/script2_event1_optimized_caching/summary.csv \
  --output experiments/comparisons \
  --top_n 20
```

Output:
- **Plot**: `experiments/comparisons/summary_vs_script2_event1_optimized_top.png`
- **Delta CSV**: `experiments/comparisons/summary_vs_script2_event1_optimized_top_delta.csv`

### 7. Interpret Results

Open the PNG to see:
- Which functions got faster (green)
- Which got slower (red)
- Magnitude of change

Open the delta CSV to see % improvement per function.

## Next Steps for You

1. **Identify optimization target**: Look at the baseline summary.csv or plot—which function takes the most time?
2. **Implement fix**: Apply caching, parallelization, or geometry simplification.
3. **Re-profile**: Run steps 3–6.
4. **Compare**: Is it faster? By how much?
5. **Iterate**: Rinse and repeat with the next optimization.

---

All infrastructure is now ready. Just follow the workflow above to drive iterations.
