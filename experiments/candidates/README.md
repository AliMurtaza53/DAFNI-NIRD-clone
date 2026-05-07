# Candidate Experiments

Store optimized Script 2 runs here, one folder per experiment.

Suggested layout:

```
experiments/candidates/
└── script2_event1_first_optimization/
    ├── metadata.json
    ├── 2_intersection_analysis_depth30_event1_candidate.prof
    ├── 2_intersection_analysis_depth30_event1_candidate.log
    └── summary.csv
```

Use `experiments/experiment_tracker.py` to save the profile and metadata once the run finishes.
