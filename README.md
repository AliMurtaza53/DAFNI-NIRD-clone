# DAFNI-NIRD

National Infrastructure Resilience Demonstrator (NIRD)

**A reproducible workflow for assessing road network disruption, damage, and recovery under flooding scenarios.**


## Quick Start: Running the Reproducible Demo

This branch contains a **cleaned, ready-to-run demonstration** of the NIRD workflow using synthetic FAF5 data for Fairfax County, Virginia.

### Prerequisites


### Setup in 5 Steps

1. **Clone and checkout this demo branch:**
   ```bash
   git clone https://github.com/nismod/DAFNI-NIRD.git
   cd DAFNI-NIRD
   git checkout demo/clean-sandbox-reproducible
   ```

2. **Create conda environment:**
   ```bash
   micromamba env create -f environment.yaml
   micromamba activate nird
   ```

3. **Download and organize data:**
   
   Download the `fairfax_soge_clusters_toy` folder from SharePoint and place it in the repository as `data/fairfax_soge_clusters_toy/`:
   
   **SharePoint Link**: https://gmuedu-my.sharepoint.com/:f:/g/personal/akothaw_gmu_edu/IgDwyAa9TnQPSKJgzQi9Yyg8AVapqPIeV1wXE9celn7V1Nk?e=81agxV
   
   After download, your folder structure should look like:
   ```
   DAFNI-NIRD/
   ├── data/
   │   └── fairfax_soge_clusters_toy/
   │       ├── study_area/
   │       ├── inputs/
   │       │   ├── networks/faf5/
   │       │   └── census_datasets/
   │       ├── hazards/
   │       ├── parameters/
   │       ├── damage_curves/
   │       ├── asset_costs/
   │       └── dbs/
   ├── config.json (already configured)
   └── ...
   ```
   
   For full details on data files, see [data/README.md](data/README.md).

4. **Prepare network (one-time):**
   ```bash
   python convert_faf5_to_nird.py
   ```
   This converts FAF5 network format to NIRD-compatible link and node tables.

Note: If you already have the converted NIRD parquet files in place, you can skip `convert_faf5_to_nird.py` and begin the workflow at `scripts/1_network_flow_model_revision.py`.

Profiling runner (local, optional):

- Script: `tools/profile_runner.py`
- Output: `profiles/` (contains `.prof`, `*_summary.txt`, `timings.csv`, `timings.png`)

Short status of the latest profiling run:
- A rerun completed for scripts 1–3 and produced `profiles/`; scripts 4–5 still failed on input/data issues, so their timings are blank for now.
- Observed wall times: script 1 = 8.770s, script 2 = 5.185s, script 3 = 47.820s.
- Script 4 failed looking for `recovery_dfesign_updated.csv`; script 5 failed with `ZeroDivisionError` in the Morris analysis path.
- A `profiles/timings.png` bar chart is available for the completed scripts.
- Re-run the profiler from the recommended environment if you want a fresh pass:

```powershell
micromamba activate nird
python tools\profile_runner.py
```

The runner writes per-script cProfile files, `timings.csv`, and `timings.png` under `profiles/`.

5. **Run the analysis pipeline:**
   ```bash
   python scripts/1_network_flow_model_revision.py
    # Script 2 must be run once per scenario (depth_key=30 cm shown here)
    # event_key: 1=base, 2=low, 3=high
    python scripts/2_intersection_analysis.py 30 1
    python scripts/2_intersection_analysis.py 30 2
    python scripts/2_intersection_analysis.py 30 3
   python scripts/3_damage_analysis.py
   python scripts/3_postprocess_damage.py
   python scripts/4_rerouting_and_recovery_scenario_loop.py
   ```
   The two `5_xx` sensitivity scripts are intentionally skipped for now and are not included in profiling.

    For toy Fairfax inputs, Script 2 scenario keys are:
    - `1` = base
    - `2` = low
    - `3` = high


**Output**: Results and figures are saved to `results/` directory.


## Workflow Overview

```
1. Data Preparation
   ├─ convert_faf5_to_nird.py
   │  └─ Input: FAF5 GeoDataFrame (data/fairfax_soge_clusters_toy/inputs/networks/faf5/)
   │     Output: NIRD road links/nodes (parquet files)
   │
2. Network Analysis (Scripts 1–4)
   ├─ 1_network_flow_model_revision.py
   │  └─ Assign baseline traffic flows to network
   │
   ├─ 2_intersection_analysis.py
   │  └─ Identify critical intersections and bottlenecks
   │
   ├─ 3_damage_analysis.py
   │  └─ Compute damage fractions and costs per link
   │
   ├─ 3_postprocess_damage.py
   │  └─ Summarize per-event damage outputs
   │
   ├─ 4_rerouting_and_recovery_scenario_loop.py
   │  └─ Simulate rerouting behavior and recovery dynamics
   │
   └─ 5_xx sensitivity scripts are skipped for now and not profiled

3. Visualization & Review
   └─ visualize_pipeline_results.ipynb
      └─ Generate summary figures and diagnostic plots
```


## Data & Configuration

### Data Files

All input data files are documented in [data/README.md](data/README.md):

**Total data size**: ~30–75 MB (compressible to ~5–10 MB)

### Configuration

The `config.json` file is **pre-configured** with relative paths:

```json
{
  "paths": {
    "soge_clusters": "data/fairfax_soge_clusters_toy",
    "base_path": "data/fairfax_soge_clusters_toy",
    "output_path": "results"
  }
}
```

All scripts read from these paths automatically. **You only need to customize `config.json` if:**

If you need to modify paths, edit the `paths` section with either:


## Development Setup (for Contributors)

Clone this repository:

    git clone git@github.com:nismod/DAFNI-NIRD.git

(Or, if you prefer to use HTTPS authentication, `git clone https://github.com/nismod/DAFNI-NIRD.git`)

Move into the cloned folder:

    cd DAFNI-NIRD

Create a conda environment using
[micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html)
to install packages specified in the [`environment.yaml`
file](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#create-env-file-manually):

    micromamba env create -f environment.yaml

(In case micromamba fails to install pip packages, you can install them manually
by running `micromamba activate nerd` then `pip install --editable .[dev]`)

Activate it:

    micromamba activate nird

Configure the [pre-commit](https://pre-commit.com/) checks:

    pre-commit install

There are several tools and helpers set up to run automatically, on `git commit`
and in [GitHub Actions](https://docs.github.com/en/actions) continuous
integration steps. Each of these can be run locally too.

Run the tests using [pytest](https://docs.pytest.org):

    python -m pytest

Run formatting using [black](https://black.readthedocs.io/):

    black .

Run linting using [ruff](https://docs.astral.sh/ruff/):

    ruff check .

Run type-checking using [mypy](https://mypy.readthedocs.io/):

    mypy --strict .

### Updating setup

To install new packages, add them to `environment.yaml` then run:

    micromamba install -f environment.yaml

To add new pre-commit hooks, configure them in `.pre-commit-config.yaml` then run:

    pre-commit run --all-files

### Documentation

This clean demo branch does not include the previous `docs/` site or its Sphinx build files.
Use the notebook and the two README files in this repository instead:


## Troubleshooting

### Data Files Not Found
Ensure the `data/` directory structure matches exactly (case-sensitive paths):
```
data/
└── fairfax_soge_clusters_toy/
    ├── study_area/
    │   ├── fairfax_study_area.geojson
    │   └── fairfax_study_area.gpkg
    ├── inputs/
    │   ├── networks/faf5/
    │   │   └── faf5_road_links.gpq
    │   └── census_datasets/
    │       ├── faf5_od_matrix.pq
    │       └── faf5_od_node_mapping.csv
    ├── hazards/
    ├── parameters/
    ├── damage_curves/
    ├── asset_costs/
    └── dbs/
```

### Script Errors
1. **ModuleNotFoundError**: Run `micromamba activate nird` before executing scripts
2. **Memory errors**: Reduce dataset size or increase available RAM
3. **GIS errors**: Verify GDAL/GEOS installation via `gdalinfo --version`

### Visualization Issues
If Jupyter notebooks fail to load:
```bash
jupyter nbconvert --to notebook --execute scripts/visualize_pipeline_results.ipynb
```


## Outstanding Issues & TODOs

1. **Setup a README/user guide/batch file** to run all scripts followed by visualization so an external collaborator can execute the full pipeline independently
2. **Clean repo and upload the working, current toy version** with fake data to enable easier onboarding and testing ✅ **(completed on this branch)**
3. **Profile the code or add functionality** in the batch file to track execution time and resource usage across pipeline stages
4. **Add validation** to check whether daily flows are in sync with current (or available) flows from DOTs
5. **Check whether a 500x scenario** triggers script 4 recovery as it should (verify scenario multiplier scaling in recovery logic)
6. **Centroid connector filtering** – ensure centroid connectors are consistently excluded from damage totals across all pipeline outputs (currently filtered in visualization layer; best practice would move to converter or damage-analysis script)


## File Structure (Cleaned Demo Branch)

```
DAFNI-NIRD/
├── data/                          # Input data (download from SharePoint)
│   ├── README.md                  # Data documentation & setup guide
│   └── fairfax_soge_clusters_toy/ # Main data directory
│       ├── study_area/            # Boundary for clipping
│       ├── inputs/
│       │   ├── networks/faf5/     # FAF5 road network
│       │   └── census_datasets/   # OD flow matrices
│       ├── hazards/               # Flood depth scenarios
│       ├── parameters/            # Model parameters
│       ├── damage_curves/         # Asset damage curves
│       ├── asset_costs/           # Asset cost data
│       └── dbs/                   # Database files
├── src/nird/                      # Python package with analysis functions
│   ├── utils.py                   # Config loading, helpers
│   ├── road_revised.py            # Network flow model
│   ├── road_capacity.py           # Road capacity calculations
│   ├── road_functions.py          # Routing & flow assignment
│   └── constants.py               # Constants (damage curves, asset costs)
├── scripts/                       # Numbered analysis pipeline
│   ├── 1_network_flow_model_revision.py
│   ├── 2_intersection_analysis.py
│   ├── 3_damage_analysis.py
│   ├── 3_postprocess_damage.py
│   ├── 4_rerouting_and_recovery_scenario_loop.py
│   ├── 5_sensitivity_analysis_direct.py
│   ├── 5_sensitivity_analysis_indirect.py
│   └── visualize_pipeline_results.ipynb
├── convert_faf5_to_nird.py        # FAF5 → NIRD network converter
├── convert_faf5_od_to_nird.py     # FAF5 OD → NIRD OD converter (variant)
├── config.json                    # Pipeline configuration (pre-configured)
├── environment.yaml               # Conda environment specification
├── pyproject.toml                 # Python package metadata
├── README.md                      # This file
└── LICENSE                        # Project license
```


## Key References



## Contact & Attribution

**Project Team**: University of Oxford (Env Change Institute) & George Mason University

**Contributors**: [List contributors]

**Citation**: If you use this workflow in research, please cite:
```
[Author(s)]. (2026). NIRD: National Infrastructure Resilience Demonstrator. 
GitHub: https://github.com/nismod/DAFNI-NIRD
```


## Docker and DAFNI (Full Production Setup)

This repository builds two images: `nismod/nird_road-recovery` and
`nismod/nird_road-damages`. The Dockerfiles, wrapper shell scripts and DAFNI
metadata model definitions are found in this repository at
`containers/nird_road`.

```bash
# Build the image - run this from the root of the repository
docker build -f ./containers/nird_road/Dockerfile-recovery -t nismod/nird_road-recovery:latest .
```

```bash
# Run image using test data - run this from the data directory
docker run --rm -v ${PWD}/test_inputs:/data/inputs -v ${PWD}/test_outputs:/data/outputs --env NUMBER_CPUS=1 --env DEPTH_THRESHOLD=30 nismod/nird_road-recovery
```

```bash
# Save image to file
docker save -o nird_road-recovery.tar nismod/nird_road-recovery:latest
```

Then upload the saved image and corresponding model definition `.yml` to DAFNI.

## Acknowledgments

This project is being developed as part of a NSF UCAR EdEC supplemental funding summer fellowship 
The project draws from work at Env Change Institute, University of Oxford, led by Raghav Pant.
