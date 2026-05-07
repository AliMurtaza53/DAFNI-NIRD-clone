Profiling experiments

This folder documents how to run profiling and compare results.

Recommended workflow

1. Run profiling using the provided runner (or manually):

```powershell
micromamba activate nird
python tools\profile_runner.py
```

Or run individual scripts with cProfile to re-run a scenario (example):

```powershell
python -m cProfile -o profiles\2_event1.prof scripts\2_intersection_analysis.py 30 1
```

2. Summarize .prof files for the notebook:

```powershell
python tools\compare_profiles.py --profiles_dir profiles --out_dir profiles\summary
```

3. Open the notebook `notebooks/profile_analysis.ipynb` and run all cells to visualize and compare runs.

What to record

- Baseline timings before a change (store the `.prof` and the `profiles/summary` outputs)
- Repeat after change and compare using the notebook

Notes

- Script 3 is a batch that processes all `intersections_*.pq` files in `results/disruption_analysis/*/intersections`.
- Script 4 is per-event and must be re-run for each event key.
