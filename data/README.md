# Data Files for NIRD Fairfax Demonstration

This directory contains **example data files** needed to run the reproducible NIRD workflow demonstration on a Fairfax County, Virginia case study.

## Data Overview

The demonstration uses a toy subset of the full Fairfax network with inflated and modified FAF5 origin-destination (OD) data.

### Files to Upload to SharePoint

**Please download the following files from the source location and upload them to the SharePoint folder provided by your advisor:**

```
https://gmuedu-my.sharepoint.com/:f:/g/personal/akothaw_gmu_edu/IgDwyAa9TnQPSKJgzQi9Yyg8AVapqPIeV1wXE9celn7V1Nk?e=81agxV
```

#### **1. Study Area Boundary** (GeoJSON & GeoPackage)
- **Source path**: `fairfax_soge_clusters_toy/study_area/`
- **Files**:
  - `fairfax_study_area.geojson` – Study boundary in GeoJSON format (for clipping)
  - `fairfax_study_area.gpkg` – Study boundary in GeoPackage format (for spatial joins)
- **Purpose**: Defines the spatial extent for analysis; used by scripts to clip networks and filter data
- **Size**: ~50–100 KB combined
- **Format**: WGS84 (EPSG:4326)

#### **2. FAF5 Road Network**
- **Source path**: `fairfax_soge_clusters_toy/inputs/networks/faf5/`
- **Files**:
  - `faf5_road_links.gpq` – FAF5 road network in Parquet format (GeoDataFrame)
- **Purpose**: Original FAF5 network; converted to NIRD format by `convert_faf5_to_nird.py`
- **Size**: ~10–50 MB
- **Format**: Parquet (geopandas-compatible); includes geometry, road classification, capacity

#### **3. FAF5 Origin-Destination Data**
- **Source path**: `fairfax_soge_clusters_toy/inputs/census_datasets/`
- **Files**:
  - `faf5_od_matrix.pq` – OD flow matrix (Parquet table)
  - `faf5_od_node_mapping.csv` – Mapping of OD zones to network nodes
- **Purpose**: Base OD flows; inflated and modified to create synthetic demand scenarios
- **Size**: ~5–20 MB (depends on matrix sparsity)
- **Format**: Parquet (faf5_od_matrix); CSV (node mapping)

---

## Setup Instructions

### Step 1: Create Data Directories

After cloning this repository, create the following directory structure:

```bash
cd DAFNI-NIRD
mkdir -p data/study_area
mkdir -p data/networks/faf5
mkdir -p data/od_data
```

### Step 2: Download Data from SharePoint

Access the shared SharePoint folder (link above) and download:

```
study_area/
├── fairfax_study_area.geojson
└── fairfax_study_area.gpkg

networks/
└── faf5/
    └── faf5_road_links.gpq

od_data/
├── faf5_od_matrix.pq
└── faf5_od_node_mapping.csv
```

### Step 3: Organize Locally

Place downloaded files in the matching local directory structure:

```
data/
├── study_area/
│   ├── fairfax_study_area.geojson
│   └── fairfax_study_area.gpkg
├── networks/
│   └── faf5/
│       └── faf5_road_links.gpq
└── od_data/
    ├── faf5_od_matrix.pq
    └── faf5_od_node_mapping.csv
```

### Step 4: Verify Data

Run a quick integrity check to ensure all files are present:

```bash
python -c "
import os
import pandas as pd
import geopandas as gpd

required_files = {
    'data/study_area/fairfax_study_area.geojson': 'geojson',
    'data/study_area/fairfax_study_area.gpkg': 'gpkg',
    'data/networks/faf5/faf5_road_links.gpq': 'parquet',
    'data/od_data/faf5_od_matrix.pq': 'parquet',
    'data/od_data/faf5_od_node_mapping.csv': 'csv',
}

print('Checking data files...')
for fpath, ftype in required_files.items():
    if os.path.exists(fpath):
        try:
            if ftype == 'geojson':
                gpd.read_file(fpath)
            elif ftype == 'gpkg':
                gpd.read_file(fpath)
            elif ftype == 'parquet':
                pd.read_parquet(fpath)
            elif ftype == 'csv':
                pd.read_csv(fpath)
            print(f'✓ {fpath}')
        except Exception as e:
            print(f'✗ {fpath}: {e}')
    else:
        print(f'✗ {fpath}: NOT FOUND')
"
```

---

## Data Configuration in Pipeline Scripts

The `config.json` and `configs.json` files contain path references to these data directories. Ensure paths are set correctly before running scripts:

**Example `config.json` snippet:**
```json
{
  "study_area_boundary": "data/study_area/fairfax_study_area.gpkg",
  "faf5_network_path": "data/networks/faf5/faf5_road_links.gpq",
  "faf5_od_matrix_path": "data/od_data/faf5_od_matrix.pq",
  "faf5_od_node_mapping_path": "data/od_data/faf5_od_node_mapping.csv"
}
```

Update these paths if you place data in alternative locations.

---

## Data Size Summary

| File | Type | Approx. Size | Purpose |
|------|------|--------------|---------|
| `fairfax_study_area.geojson` | GeoJSON | 50 KB | Boundary clipping |
| `fairfax_study_area.gpkg` | GeoPackage | 50 KB | Spatial joins |
| `faf5_road_links.gpq` | Parquet | 20–50 MB | Network base |
| `faf5_od_matrix.pq` | Parquet | 5–20 MB | OD flows |
| `faf5_od_node_mapping.csv` | CSV | 100 KB–1 MB | OD zone mapping |
| **Total** | — | **~30–75 MB** | — |

---

## Data Provenance & Licensing

- **FAF5 Network & OD Data**: Derived from the [Freight Analysis Framework (FAF5)](https://faf.ornl.gov/) published by the U.S. Department of Transportation (USDOT). FAF5 data is public domain.
- **Study Area Boundary**: Fairfax County administrative boundary (public GIS data)
- **Modifications**: OD flows have been inflated and modified for demonstration purposes (not real traffic)

---

## Questions?

If you encounter issues downloading or setting up data, refer to the main [README.md](../README.md) for troubleshooting, or contact the project team.
