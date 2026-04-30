# 🚀 Quick Start for Advisor - DAFNI-NIRD Demo

**You're receiving a clean, reproducible demo of the NIRD workflow.** Everything is pre-configured—just follow these 7 steps.

---

## 📥 STEP 1: Clone the Demo Repository

```bash
git clone https://github.com/nismod/DAFNI-NIRD.git
cd DAFNI-NIRD
git checkout demo/clean-sandbox-reproducible
```

**Expected**: You're now on the demo branch with all code ready.

---

## 🔧 STEP 2: Create Python Environment

```bash
# Using Micromamba (recommended, faster)
micromamba env create -f environment.yaml
micromamba activate nird

# OR using Conda (if you don't have micromamba)
conda env create -f environment.yaml
conda activate nird
```

**Expected**: Python 3.12 environment with 40+ packages installed.

**Verify**: 
```bash
python --version  # Should show Python 3.12.x
pip list | grep geopandas  # Should find geopandas
```

---

## 📥 STEP 3: Download Data from SharePoint

**SharePoint Link**: https://gmuedu-my.sharepoint.com/:f:/g/personal/akothaw_gmu_edu/IgDwyAa9TnQPSKJgzQi9Yyg8AVapqPIeV1wXE9celn7V1Nk?e=81agxV

1. Open the link
2. Download the entire **`fairfax_soge_clusters_toy`** folder
3. Place it in your cloned repository:

```
DAFNI-NIRD/
└── data/
    └── fairfax_soge_clusters_toy/  (← Downloaded from SharePoint)
```

**Expected folder structure inside**:
```
fairfax_soge_clusters_toy/
├── study_area/              # Study area boundary
├── inputs/
│   ├── networks/faf5/       # Road network
│   └── census_datasets/     # OD flow data
├── hazards/                 # Flood scenarios
├── parameters/              # Model parameters
├── damage_curves/           # Damage functions
├── asset_costs/             # Asset values
└── dbs/                     # Databases
```

**Size**: ~30–75 MB total

---

## ✅ STEP 4: Verify Data (Quick Check)

Run this Python snippet to confirm everything is in place:

```python
from pathlib import Path

data_path = Path("data/fairfax_soge_clusters_toy")
required = [
    "study_area",
    "inputs/networks/faf5",
    "inputs/census_datasets",
    "hazards", "parameters", "damage_curves", "asset_costs", "dbs"
]

all_good = True
for folder in required:
    p = data_path / folder
    status = "✓" if p.exists() else "✗"
    print(f"{status} {folder}")
    all_good = all_good and p.exists()

print(f"\nAll data ready: {all_good}")
```

**Expected output**: All folders have ✓ checkmarks

---

## 🔄 STEP 5: Prepare Network (One-Time)

```bash
python convert_faf5_to_nird.py
```

**What it does**: Converts FAF5 network format to NIRD format  
**Expected**: 5–10 seconds, no errors  
**Output**: Creates files in `data/fairfax_soge_clusters_toy/dbs/`

---

## 📊 STEP 6: Run Analysis Pipeline

Run these 6 commands in order. Each takes 30–60 seconds:

```bash
# 1. Network Flow Model
python scripts/1_network_flow_model_revision.py

# 2. Intersection Analysis  
python scripts/2_intersection_analysis.py

# 3. Damage Analysis
python scripts/3_damage_analysis.py

# 4. Rerouting & Recovery
python scripts/4_rerouting_and_recovery_scenario_loop.py

# 5. Sensitivity Analysis (Direct)
python scripts/5_sensitivity_analysis_direct.py

# 6. Sensitivity Analysis (Indirect)
python scripts/5_sensitivity_analysis_indirect.py
```

**Expected**: 
- All scripts complete without errors
- Output files created in `results/` directory
- Total time: 3–5 minutes

---

## 📈 STEP 7: Review Results

```bash
jupyter notebook scripts/visualize_pipeline_results.ipynb
```

**What you'll see**:
1. Network damage distribution (histogram)
2. Damage by road classification (bar chart)
3. Link travel time impact (scatter plot)
4. Recovery timeline (line plot)
5. Sensitivity analysis heatmap

**Expected**: Notebook opens in browser, all plots render cleanly

---

## ✨ You're Done!

All results are saved in the `results/` directory:
- Damage analysis outputs
- Recovery scenarios
- Sensitivity analysis results
- Visualization figures

---

## ⚙️ Configuration (If You Need to Customize)

The workflow uses `config.json` for all paths. It's **already configured correctly**:

```json
{
  "paths": {
    "soge_clusters": "data/fairfax_soge_clusters_toy",
    "base_path": "data/fairfax_soge_clusters_toy",
    "output_path": "results"
  }
}
```

**If you need to store data elsewhere**, edit `config.json`:

### Option A: OneDrive Symlink
```bash
# Windows: Create symbolic link
mklink /D "data\fairfax_soge_clusters_toy" "C:\OneDrive\...\fairfax_soge_clusters_toy"

# macOS/Linux: Create symbolic link
ln -s /path/to/OneDrive/fairfax_soge_clusters_toy data/fairfax_soge_clusters_toy
```
Then keep `config.json` as-is.

### Option B: Absolute Path
Change `config.json`:
```json
{
  "paths": {
    "soge_clusters": "C:/OneDrive/Your/Full/Path/fairfax_soge_clusters_toy",
    "base_path": "C:/OneDrive/Your/Full/Path/fairfax_soge_clusters_toy",
    "output_path": "results"
  }
}
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `micromamba activate nird` or `conda activate nird` |
| Data not found | Verify `data/fairfax_soge_clusters_toy/` exists with all 8 subdirectories |
| Out of memory | Close other applications or use a machine with more RAM |
| Jupyter won't open | Try `jupyter lab` instead of `jupyter notebook` |
| GDAL errors | Verify geospatial tools: `gdalinfo --version` |

---

## 📚 Detailed Documentation

For more information, see:

- **README.md** – Full workflow overview and architecture
- **SETUP_CHECKLIST.md** – Comprehensive step-by-step setup guide
- **DEMO_COMPLETE.md** – Summary of all improvements and fixes
- **data/README.md** – Detailed data file descriptions

---

## 🎯 What You're Running

This is a **complete, reproducible workflow** that:

1. **Loads FAF5 road network** for Fairfax County, Virginia
2. **Assigns traffic flows** based on OD matrices
3. **Analyzes network vulnerabilities** (bottlenecks, critical links)
4. **Simulates damage** under flood scenarios
5. **Models recovery** as links are repaired
6. **Performs sensitivity analysis** to understand parameter impact
7. **Visualizes results** with publication-quality figures

**Total runtime**: 3–5 minutes  
**Total data size**: 30–75 MB  
**Outputs**: Damage summaries, recovery timelines, sensitivity heatmaps

---

## 💡 Key Features

- ✅ **Self-contained** – No external dependencies beyond conda packages
- ✅ **Portable** – Works on Windows, macOS, Linux
- ✅ **Reproducible** – Pinned dependencies ensure consistent results
- ✅ **Well-documented** – 3 README files + inline code comments
- ✅ **Production-ready** – Used in academic research
- ✅ **Extensible** – Easy to modify parameters or add scenarios

---

**Questions?** Check the detailed documentation files in the repository.

**Ready to start?** Go to STEP 1! 🚀
