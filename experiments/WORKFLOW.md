# Experiment Workflow & Hierarchy

## Directory Structure

```
experiments/
├── baselines/               # Baseline profiles (reference, no changes)
│   └── script2_event1_baseline/
│       ├── metadata.json    # {"exp_id", "branch", "timestamp", "description"}
│       ├── *.prof           # raw cProfile output
│       └── summary.csv      # top-N functions from pstats
├── candidates/              # Candidate profiles (with code changes)
│   └── script2_event1_optimized_caching/
│       ├── metadata.json
│       ├── *.prof
│       └── summary.csv
└── comparisons/             # Comparison plots & deltas
    └── script2_event1_baseline_vs_optimized_caching.png
```

## Workflow: Baseline → Improve → Compare

### 1. Establish Baseline

```bash
# Run script 2 event 1 under cProfile
python -m cProfile -o profiles/script2_event1_baseline.prof scripts/2_intersection_analysis.py 30 1 2>&1 | tee profiles/script2_event1_baseline.log

# Move to experiments/baselines/ with metadata
python experiments/experiment_tracker.py --action save_profile \
  --profile_path profiles/script2_event1_baseline.prof \
  --exp_dir experiments/baselines/script2_event1_baseline \
  --exp_id "script2_event1_baseline" \
  --branch "demo/clean-sandbox-reproducible" \
  --description "Baseline: no optimizations applied"
```

### 2. Implement Improvement

Edit target code (e.g., `scripts/2_intersection_analysis.py`):
- Apply caching, reduce geometry precision, parallelize, etc.
- Commit: `git commit -m "opt: add caching to intersections_with_damage"`

### 3. Re-profile Candidate

```bash
# Run improved script 2 event 1
python -m cProfile -o profiles/script2_event1_optimized_caching.prof scripts/2_intersection_analysis.py 30 1 2>&1 | tee profiles/script2_event1_optimized_caching.log

# Move to experiments/candidates/ with metadata
python experiments/experiment_tracker.py --action save_profile \
  --profile_path profiles/script2_event1_optimized_caching.prof \
  --exp_dir experiments/candidates/script2_event1_optimized_caching \
  --exp_id "script2_event1_optimized_caching" \
  --branch "demo/clean-sandbox-reproducible" \
  --description "Optimization: add caching & merge minimization"
```

### 4. Compare Baseline vs Candidate

```bash
# Generate comparison plot (baseline on left, candidate on right)
python tools/plot_profile_comparison.py \
  --baseline experiments/baselines/script2_event1_baseline/summary.csv \
  --candidate experiments/candidates/script2_event1_optimized_caching/summary.csv \
  --output experiments/comparisons/ \
  --top_n 20

# View generated PNG
# Outputs: experiments/comparisons/script2_event1_baseline_vs_optimized_caching.png
```

### 5. Document Results

Add markdown cell to `notebooks/profile_analysis.ipynb`:

```markdown
### Experiment: Caching in script 2 event 1

**Baseline**: `experiments/baselines/script2_event1_baseline/`  
**Candidate**: `experiments/candidates/script2_event1_optimized_caching/`  
**Change**: Added per-raster caching of road_links & base_scenario_links  
**Result**: ~X% improvement (or regression)

![Comparison](../experiments/comparisons/script2_event1_baseline_vs_optimized_caching.png)
```

## Key Points

- **Always save with metadata**: exp_id, branch, timestamp, description.
- **Name clearly**: `{script}_{event}_{optimization}` or `{script}_{event}_baseline`.
- **Compare same scenario**: baseline event 1 vs optimized event 1 (not event 1 vs event 2).
- **Focus on top-N**: Plot only top 20–25 slowest functions, sorted by cumtime.
- **Clean names**: Strip file paths, show only function name + module.
