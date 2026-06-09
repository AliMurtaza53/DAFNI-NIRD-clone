# Reproducible Modeling Project Checklist and Best Practices Guide

For modeling projects, the standard approach is to treat the work like a small software product, not just a pile of scripts. The goal is simple:

> If someone else clones the repository later, they should be able to recreate the environment, run the pipeline, and reproduce the same type of results without guessing.

This does not mean every result must be bit-for-bit identical across machines. It means the project clearly documents the software, data, configuration, workflow, and assumptions needed to rerun the analysis.

---

## 1. Core Principle

A reproducible modeling project makes three layers explicit:

| Layer       | Key Question                     | What Should Be Declared                       |
| ----------- | -------------------------------- | --------------------------------------------- |
| Environment | What software is needed?         | Python version, packages, system dependencies |
| Code        | What does the model do?          | Scripts, modules, functions, workflow steps   |
| Data        | What files are read and written? | Input paths, data versions, output folders    |

A project becomes hard to reproduce when these layers are implicit, scattered, or dependent on manual steps.

---

# A. Recommended Project Structure

A mature default structure looks like this:

```text
project-name/
│
├── README.md
├── environment.yaml
├── pyproject.toml
├── .gitignore
├── .env.example
│
├── config/
│   ├── default.yaml
│   ├── local.example.yaml
│   └── scenarios/
│       ├── baseline.yaml
│       └── disruption_test.yaml
│
├── src/
│   └── project_name/
│       ├── __init__.py
│       ├── io/
│       ├── preprocessing/
│       ├── assignment/
│       ├── analysis/
│       └── utils/
│
├── scripts/
│   ├── 01_prepare_network.py
│   ├── 02_prepare_od.py
│   ├── 03_run_assignment.py
│   ├── 04_summarize_results.py
│   └── run_pipeline.py
│
├── notebooks/
│   ├── exploration/
│   └── figures/
│
├── tests/
│   ├── test_config.py
│   ├── test_io.py
│   └── test_smoke_pipeline.py
│
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
│
├── results/
│   ├── runs/
│   ├── figures/
│   └── tables/
│
└── docs/
    ├── reproducibility_checklist.md
    ├── data_dictionary.md
    └── model_assumptions.md
```

---

# B. Repository Organization Checklist

## Code

* [ ] Put reusable code in `src/project_name/`.
* [ ] Keep workflow scripts in `scripts/`.
* [ ] Avoid writing the main modeling logic only in notebooks.
* [ ] Break large scripts into functions and modules.
* [ ] Avoid copy-pasting the same logic across scripts.
* [ ] Use descriptive names for scripts, modules, functions, and outputs.
* [ ] Keep experimental scratch work separate from production workflow code.

Best practice:

* Notebooks are for understanding.
* Scripts are for running.
* Modules/packages are for reuse.
* Config files are for settings.

---

## Data

* [ ] Separate raw, interim, and processed data.
* [ ] Do not modify raw data manually.
* [ ] Do not commit large data files to GitHub unless they are small examples.
* [ ] Use `.gitignore` to exclude large or sensitive data.
* [ ] Keep a small sample dataset for testing if possible.
* [ ] Document where the full dataset lives.
* [ ] Record the data source, date downloaded, version, and any preprocessing steps.
* [ ] Use relative paths or config-based paths instead of hardcoded local paths.

Suggested structure:

```text
data/
├── raw/          # original input data, never edited manually
├── interim/      # intermediate files
├── processed/    # cleaned/model-ready files
└── sample/       # small test/demo data that can be committed
```

---

## Results and Outputs

* [ ] Write outputs to a known `results/` directory.
* [ ] Create one folder per model run.
* [ ] Save parameter settings with each run.
* [ ] Save summary logs, warnings, and runtime information.
* [ ] Avoid overwriting important outputs unless explicitly intended.
* [ ] Keep large outputs out of GitHub.
* [ ] Commit only small, final figures or tables when useful.

Example output structure:

```text
results/
└── runs/
    └── 2026-06-04_baseline_test/
        ├── config_used.yaml
        ├── run_log.txt
        ├── summary_metrics.csv
        ├── edge_flows.parquet
        └── figures/
```

---

# C. Environment Management Checklist

For scientific, transportation, geospatial, and network modeling work, `conda`, `mamba`, or `micromamba` is usually safer than plain `venv + pip`.

This is because packages such as GDAL, Fiona, Rasterio, GeoPandas, Shapely, PyProj, and related geospatial libraries often depend on native system libraries, not just Python packages.

## Recommended Environment Practice

* [ ] Use `environment.yaml` for the main project environment.
* [ ] Pin the Python version.
* [ ] Use `conda-forge` where possible.
* [ ] Use `pip` only for Python-only packages or installing the project itself.
* [ ] Avoid manual terminal installs that are not recorded in the environment file.
* [ ] Test the environment on a clean machine or clean environment.
* [ ] Update the environment deliberately, not casually.

Example:

```yaml
name: project-name
channels:
  - conda-forge
dependencies:
  - python=3.11
  - geopandas
  - shapely
  - pyproj
  - pandas
  - numpy
  - scipy
  - networkx
  - duckdb
  - pyarrow
  - matplotlib
  - pytest
  - pip
  - pip:
      - -e .
```

Useful commands:

```bash
mamba env create -f environment.yaml
mamba activate project-name
pip install -e .
```

---

# D. Configuration Checklist

Do not hardcode paths, scenario assumptions, or model parameters inside scripts.

Instead, put them in a config file.

## What Should Go in Config?

* [ ] Input data paths.
* [ ] Output directory.
* [ ] Scenario name.
* [ ] Random seed.
* [ ] Model parameters.
* [ ] Capacity assumptions.
* [ ] Simulation settings.
* [ ] Run options.
* [ ] Logging level.
* [ ] Sample size or debug mode settings.

Example:

```yaml
run:
  name: baseline_test
  random_seed: 12345
  debug_mode: false

paths:
  network_edges: data/processed/network_edges.parquet
  od_matrix: data/processed/od_matrix.parquet
  output_dir: results/runs

assignment:
  method: shortest_path
  max_iterations: 50
  convergence_tolerance: 0.001
  save_sample_paths: true
  sample_path_count: 1000
```

Best practice:

* `config/default.yaml` should contain safe defaults.
* `config/local.yaml` can contain user-specific local paths.
* `config/local.yaml` should usually be ignored by Git.
* Provide `config/local.example.yaml` so others know what to create.

---

# E. Reproducible Workflow Checklist

The project should have a clear run path.

A new user should not have to ask:

* Which script runs first?
* Which data file is required?
* Where do outputs go?
* Which environment should I use?
* What counts as success?

## Minimum Workflow Standard

* [ ] Provide one command to run the full pipeline.
* [ ] Provide separate commands for each major step.
* [ ] Make the workflow restartable where possible.
* [ ] Add clear logging.
* [ ] Validate inputs before expensive runs.
* [ ] Fail with readable error messages.
* [ ] Save a copy of the config used for each run.

Example:

```bash
python scripts/run_pipeline.py --config config/scenarios/baseline.yaml
```

Or step-by-step:

```bash
python scripts/01_prepare_network.py --config config/scenarios/baseline.yaml
python scripts/02_prepare_od.py --config config/scenarios/baseline.yaml
python scripts/03_run_assignment.py --config config/scenarios/baseline.yaml
python scripts/04_summarize_results.py --config config/scenarios/baseline.yaml
```

---

# F. Testing Checklist

Tests do not need to be extensive at first. Start with smoke tests.

## Minimum Useful Tests

* [ ] Test that the config loads.
* [ ] Test that required input paths are recognized.
* [ ] Test that a small sample OD matrix can run.
* [ ] Test that the model produces expected output columns.
* [ ] Test that no major step silently returns empty results.
* [ ] Test critical utility functions.
* [ ] Test known edge cases.

Example tests:

```text
tests/
├── test_config.py
├── test_io.py
├── test_network_loading.py
├── test_assignment_small_network.py
└── test_smoke_pipeline.py
```

A smoke test should answer:

> Can the project run end-to-end on a tiny dataset without crashing?

That alone is extremely valuable.

---

# G. Version Control Checklist

Use Git for code, configs, documentation, and environment files.

Do not use Git for large raw data, large intermediate data, or large model outputs unless you are using a dedicated tool such as Git LFS or DVC.

## What to Commit

* [ ] Source code.
* [ ] Scripts.
* [ ] Config templates.
* [ ] Environment files.
* [ ] README.
* [ ] Documentation.
* [ ] Tests.
* [ ] Small sample data.
* [ ] Small final figures or tables if useful.

## What Not to Commit

* [ ] Large raw datasets.
* [ ] Large generated outputs.
* [ ] Temporary files.
* [ ] Local machine paths.
* [ ] Secrets, tokens, API keys, passwords.
* [ ] Personal config files.
* [ ] Cache directories.
* [ ] Notebook checkpoints.

Suggested `.gitignore` entries:

```text
data/raw/
data/interim/
data/processed/
results/
.env
config/local.yaml
__pycache__/
.ipynb_checkpoints/
*.log
*.tmp
```

---

# H. README Checklist

The README is the front door of the project.

It should answer the basic questions quickly.

## README Should Include

* [ ] Project title.
* [ ] Short project description.
* [ ] What the model does.
* [ ] Required software.
* [ ] Installation instructions.
* [ ] Environment setup.
* [ ] Data requirements.
* [ ] Configuration instructions.
* [ ] How to run the pipeline.
* [ ] How to run tests.
* [ ] Expected outputs.
* [ ] Troubleshooting notes.
* [ ] Contact or maintainer information.

Suggested README outline:

```markdown
# Project Name

## Overview

## Repository Structure

## Installation

## Data Requirements

## Configuration

## Running the Pipeline

## Running Tests

## Outputs

## Troubleshooting

## Notes for Future Contributors
```

---

# I. Continuous Integration Checklist

Continuous integration means the project is tested automatically on GitHub or another platform.

For a modeling project, CI does not need to run the full heavy model. It should run lightweight checks.

## Useful CI Checks

* [ ] Create the environment.
* [ ] Install the package.
* [ ] Run formatting checks.
* [ ] Run linting checks.
* [ ] Run unit tests.
* [ ] Run smoke tests on small sample data.
* [ ] Confirm that scripts can be imported.

Recommended tools:

* `pytest` for tests.
* `ruff` for linting and formatting.
* GitHub Actions for CI.

Minimum CI goal:

> A fresh machine should be able to install the project and run the small test pipeline.

---

# J. Modeling-Specific Best Practices

For modeling, simulation, network assignment, and resilience analysis, reproducibility also depends on model assumptions.

## Modeling Assumptions

* [ ] Record assumptions clearly.
* [ ] Save parameter values with every run.
* [ ] Document units.
* [ ] Document coordinate reference systems.
* [ ] Document time periods.
* [ ] Document demand scaling.
* [ ] Document capacity assumptions.
* [ ] Document disruption assumptions.
* [ ] Document convergence criteria.
* [ ] Document any filtering rules.

## Randomness

* [ ] Put random seeds in config.
* [ ] Set random seeds consistently.
* [ ] Record the seed used for each run.
* [ ] Avoid hidden randomness where possible.

## Performance

* [ ] Log runtime for major steps.
* [ ] Log memory-heavy operations.
* [ ] Avoid unnecessary path materialization.
* [ ] Save intermediate files only when they are useful.
* [ ] Prefer efficient formats such as Parquet for large tabular data.
* [ ] Profile before optimizing.
* [ ] Keep a small debug mode for fast iteration.

## Validation

* [ ] Check row counts after major joins.
* [ ] Check for missing values in key fields.
* [ ] Check network connectivity.
* [ ] Check OD totals before and after processing.
* [ ] Check units before combining datasets.
* [ ] Compare outputs against known benchmarks where possible.
* [ ] Save summary diagnostics after every run.

---

# K. Practical Gold-Standard Setup

For a serious modeling project, a strong default stack is:

* `environment.yaml` for scientific/geospatial dependencies.
* `pyproject.toml` for package metadata and Python tooling.
* `src/project_name/` for reusable code.
* `scripts/` for workflow entry points.
* `config/` for paths, parameters, and scenarios.
* `tests/` for unit and smoke tests.
* `data/` outside version control if large.
* `results/` ignored by Git.
* `docs/` for assumptions, data dictionaries, and reproducibility notes.
* GitHub Actions for fresh-machine validation.
* README with install, run, test, and troubleshoot instructions.

---

# L. Simple Rule of Thumb

Use this stack for scientific and transportation modeling work:

* Conda or mamba for the environment.
* A pinned Python version.
* A package-managed codebase.
* Config files for inputs, outputs, and parameters.
* Scripts for repeatable workflows.
* Notebooks only for exploration and communication.
* Tests for the critical path.
* CI for fresh-machine verification.
* Documentation for data, assumptions, and run instructions.

---

# M. Minimum Viable Version

If the full setup feels like too much, start with this minimum:

* [ ] `README.md`
* [ ] `environment.yaml`
* [ ] `config/default.yaml`
* [ ] `scripts/run_pipeline.py`
* [ ] `src/project_name/`
* [ ] `tests/test_smoke_pipeline.py`
* [ ] `.gitignore`
* [ ] `docs/model_assumptions.md`

This is enough to turn a loose script collection into a reproducible modeling project.

---

# N. Final Mental Model

A weak project says:

> “Run these scripts on my machine and hopefully it works.”

A strong project says:

> “Here is the environment, here are the inputs, here are the settings, here is the command, here are the outputs, and here is how to verify the result.”

That is the standard to aim for.
