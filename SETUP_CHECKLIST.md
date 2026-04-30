# Demo Setup Checklist for External Collaborators

This checklist confirms that your demo is **self-contained and ready for your advisor** to run independently.

---

## ✅ Pre-Setup Verification

- [x] Repository cleaned (sandbox/docs/experiments removed)
- [x] Demo branch created: `demo/clean-sandbox-reproducible`
- [x] All 5 numbered scripts ready to execute sequentially
- [x] Visualization notebook ready for final review
- [x] Configuration system centralized in `config.json`
- [x] Data folder structure documented
- [x] Environment specifications in `environment.yaml`

---

## 📋 Advisor Setup Steps

### Step 1: Clone the Demo Repository
```bash
git clone https://github.com/nismod/DAFNI-NIRD.git
cd DAFNI-NIRD
git checkout demo/clean-sandbox-reproducible
```

**Expected result**: Demo branch checked out; `config.json` has relative paths pointing to `data/fairfax_soge_clusters_toy/`

---

### Step 2: Create Conda Environment
```bash
micromamba env create -f environment.yaml
micromamba activate nird
```

**Expected result**: 
- Python 3.12 active
- 40+ packages installed (geopandas, snkit, duckdb, jupyter, etc.)
- No errors during environment creation

---

### Step 3: Download Data from SharePoint

**SharePoint Link**: https://gmuedu-my.sharepoint.com/:f:/g/personal/akothaw_gmu_edu/IgDwyAa9TnQPSKJgzQi9Yyg8AVapqPIeV1wXE9celn7V1Nk?e=81agxV

Download the entire **`fairfax_soge_clusters_toy`** folder and place in repo:

```bash
# After downloading, organize as:
# DAFNI-NIRD/
# └── data/
#     └── fairfax_soge_clusters_toy/
#         ├── study_area/
#         ├── inputs/
#         │   ├── networks/faf5/
#         │   └── census_datasets/
#         ├── hazards/
#         ├── parameters/
#         ├── damage_curves/
#         ├── asset_costs/
#         └── dbs/
```

**Expected result**: 
- `data/fairfax_soge_clusters_toy/` exists with all 8 subdirectories
- Total size: ~30–75 MB (variable depending on file compression)

---

### Step 4: Verify Data Files

Run this quick verification:

```python
from pathlib import Path
import json

# Load config
with open("config.json") as f:
    config = json.load(f)

base_path = Path(config["paths"]["soge_clusters"])

# Check all required subdirectories
required_dirs = [
    "study_area",
    "inputs/networks/faf5",
    "inputs/census_datasets",
    "hazards",
    "parameters",
    "damage_curves",
    "asset_costs",
    "dbs"
]

for dir_name in required_dirs:
    dir_path = base_path / dir_name
    exists = dir_path.exists()
    status = "✓" if exists else "✗"
    print(f"{status} {dir_path}")

# Check critical files
critical_files = [
    "study_area/fairfax_study_area.gpkg",
    "inputs/networks/faf5/faf5_road_links.gpq",
    "inputs/census_datasets/faf5_od_matrix.pq",
    "inputs/census_datasets/faf5_od_node_mapping.csv"
]

print("\nCritical files:")
for file_name in critical_files:
    file_path = base_path / file_name
    exists = file_path.exists()
    size_mb = file_path.stat().st_size / 1e6 if exists else 0
    status = "✓" if exists else "✗"
    print(f"{status} {file_name} ({size_mb:.1f} MB)")
```

**Expected result**: 
- All 8 directories exist
- All 4 critical files found and readable
- Combined size ~ 30–75 MB

---

### Step 5: Prepare Network (One-Time)

```bash
python convert_faf5_to_nird.py
```

**Expected output**:
- Converts FAF5 network to NIRD format
- Creates parquet files in `data/fairfax_soge_clusters_toy/dbs/`
- Execution time: 5–10 seconds (depends on hardware)
- No errors or warnings

---

### Step 6: Run Pipeline Scripts (Sequential)

Run scripts in order (each takes 30–60 seconds; adjust for your hardware):

```bash
# 1. Network Flow Model
python scripts/1_network_flow_model_revision.py

# 2. Intersection Analysis
python scripts/2_intersection_analysis.py

# 3. Damage Analysis
python scripts/3_damage_analysis.py

# 4. Rerouting & Recovery (variant with OD inflation)
python scripts/4_rerouting_and_recovery_scenario_loop.py

# 5. Sensitivity Analysis (direct and indirect)
python scripts/5_sensitivity_analysis_direct.py
python scripts/5_sensitivity_analysis_indirect.py
```

**Expected results**:
- All scripts complete without errors
- `results/` directory is created and populated with output files
- Final damage totals: ~226,898 network links (after centroid exclusion)
- Execution time: 3–5 minutes total (hardware-dependent)

---

### Step 7: Review Visualization Notebook

```bash
jupyter notebook scripts/visualize_pipeline_results.ipynb
```

**Expected output**:
- Notebook opens in browser
- All cells execute without errors
- Generates 5 summary figures:
  1. Network damage distribution
  2. Road classification damage comparison
  3. Link travel time impact
  4. Recovery timeline
  5. Sensitivity analysis heatmap

---

## 🎯 Success Criteria

**Full demo has completed successfully if:**

- [ ] All 5 scripts executed without errors
- [ ] `results/` directory contains output parquet files and CSV summaries
- [ ] Visualization notebook generates all 5 figures
- [ ] Damage totals match expected ranges (~226,898 links after centroid exclusion)
- [ ] No missing data file errors or path issues
- [ ] Total runtime: 3–5 minutes (varies by machine)

---

## ⚙️ Configuration Notes

### Default Configuration (`config.json`)
```json
{
  "paths": {
    "soge_clusters": "data/fairfax_soge_clusters_toy",
    "base_path": "data/fairfax_soge_clusters_toy",
    "output_path": "results"
  }
}
```

### Custom Configuration (if needed)

If your advisor needs to store data elsewhere, modify `config.json`:

**Option A: Symlink OneDrive**
```bash
# Create symbolic link from OneDrive to local repo data folder
mklink /D "data\fairfax_soge_clusters_toy" "C:\OneDrive\...\fairfax_soge_clusters_toy"
```
Then keep `config.json` as-is.

**Option B: Update Absolute Path**
```json
{
  "paths": {
    "soge_clusters": "C:/OneDrive/Your/Path/fairfax_soge_clusters_toy",
    "base_path": "C:/OneDrive/Your/Path/fairfax_soge_clusters_toy",
    "output_path": "results"
  }
}
```

**Option C: Copy Data to Local Folder**
Just download and place in `data/fairfax_soge_clusters_toy/` as recommended (default).

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `micromamba activate nird` before scripts |
| Data files not found | Verify `data/fairfax_soge_clusters_toy/` exists and has all 8 subdirs |
| Out of memory | Reduce dataset size or increase available RAM |
| Notebook won't open | Try: `jupyter nbconvert --to notebook --execute scripts/visualize_pipeline_results.ipynb` |
| GDAL/GEOS errors | Verify geospatial packages: `gdalinfo --version` |

---

## 📝 Outstanding Issues

For reference, these are documented in the main README under "Outstanding Issues & TODOs":

1. Batch file for fully automated pipeline execution
2. Execution time profiling and tracking
3. Daily flow validation against DOT data
4. 500x scenario recovery verification
5. Upstream centroid connector filtering (currently in visualization layer)

---

## 📞 Questions or Issues?

If your advisor encounters problems:

1. Check this checklist to verify all setup steps completed
2. Review the [data/README.md](data/README.md) for data structure details
3. Check [README.md](README.md) for troubleshooting section
4. Verify environment: `conda list | grep -E "geopandas|snkit|duckdb|jupyter"`

---

**Demo Status**: ✅ **Ready for External Collaboration**

**Commit**: `dc88689` – "Update docs: clarify data org, update config.json paths, remove unused configs.json"

**Branch**: `demo/clean-sandbox-reproducible`

**Last Updated**: 2024
