# FAF5 to NIRD Quick Start Guide

Based on actual FAF5 V2021.05 link data structure.

## Table of Contents

- [FAF5 Data Structure (Observed)](#faf5-data-structure-observed)
- [Critical Column Mappings](#critical-column-mappings)
- [Road Classification Mapping](#road-classification-mapping)
- [Workflow](#workflow)
- [Coordinate Reference Systems](#coordinate-reference-systems)
- [Key Differences: FAF5 vs OSM (UK NIRD)](#key-differences-faf5-vs-osm-uk-nird)
- [Tonnage to Vehicle Conversion](#tonnage-to-vehicle-conversion)
- [Sample Data Check](#sample-data-check)
- [Next Steps](#next-steps)
- [Troubleshooting](#troubleshooting)

## FAF5 Data Structure (Observed)

### Link Attributes Available
```
OBJECTID, SHAPE, ID, LENGTH, DIR, DATA, VERSION, Class, Class_Description,
Road_Name, Sign_Rte, Rte_Type, Rte_Number, Rte_Qualifier, Country, STATE,
STFIPS, County_Name, CTFIPS, Urban_Code, FAFZONE, Status, F_Class,
Facility_Type, NHS, STRAHNET, NHFN, Truck, AB_Lanes, BA_Lanes, Speed_Limit,
Toll_Type, Toll_Name, Toll_Link, Toll_Link_Name, HPMS_USA_RouteID,
HPMS_Begin_Point, HPMS_End_Point, BorderState1, BorderState2, BorderFAF1,
BorderFAF2, TRUCKTOLL, BorderLink, AddedBorderTime, AdjustSpeed, AdjustReason,
AB_FinalSpeed, BA_FinalSpeed, AB_CombinedSpeed, BA_CombinedSpeed,
AB_FreeFlowTime, BA_FreeFlowTime, SHAPE_Length
```

### Node Attributes Available
```
node_id, SHAPE, Centroid, CentroidID
```

- **Centroid** (1/0): Flag indicating if node is a FAF zone centroid
- **CentroidID**: FAF zone identifier (county/sub-county unique ID)

### Special Link Class: Centroid Connectors

- **Class == 50**: Centroid connector links
  - Artificial links connecting FAF zone centroids to real road network
  - **Filtered out** during conversion (not real roads)
  - Used only for mapping FAF zones to network nodes

## Critical Column Mappings

| FAF5 Column | NIRD Column | Conversion | Notes |
|-------------|-------------|------------|-------|
| `ID` | `e_id` | `str(ID)` | Unique link ID |
| Extracted from geometry | `from_id`, `to_id` | Node IDs from endpoints | Create node dictionary |
| `LENGTH` | `length` | `LENGTH * 1609.34` | Miles → meters |
| `Class` | `road_classification` | Via CLASS_MAPPING | See table below |
| `AB_Lanes` / `BA_Lanes` | `lanes` | `max(AB_Lanes, BA_Lanes)` | Use higher of two directions |
| `Urban_Code` | `urban` | `Urban_Code != 99999` | 99999 = rural |
| `lanes * 3.5` | `averageWidth` | Calculated | Assume 3.5m per lane |
| - | `average_toll_cost` | `0.0` | Default to free (unless toll data) |
| - | `road_bridge` | `'no'` | Default (unless bridge layer) |
| `SHAPE` | `geometry` | Reproject to target CRS | LineString |

## Road Classification Mapping

| FAF5 Class | Class_Description | NIRD road_classification |
|-----------|-------------------|-------------------------|
| 1 | Interstate | `'motorway'` |
| 2 | Principal Arterial - Freeways | `'trunk'` |
| 3 | Principal Arterial - Other | `'primary'` |
| 4 | Minor Arterial | `'primary'` |
| 5 | Major Collector | `'secondary'` |
| 6 | Minor Collector | `'tertiary'` |
| 7 | Local | `'unclassified'` |
| 8 | Ramp | `'motorway_link'` |
| 9 | Service/Frontage Road | `'service'` |
| 19 | Facility Access/Circulator | `'service'` |
| **50** | **Centroid Connector** | **FILTERED OUT** |

## Workflow

### 1. Get FAF5 Data

Download from: https://ops.fhwa.dot.gov/freight/freight_analysis/faf/

**Files needed**
- FAF5 Highway Network (geodatabase with links AND nodes)
- FAF5 Regional Flows (OD data by zone)
- FAF5 Zone boundaries (optional - can use centroid nodes instead)

### 2. Convert Network Links

```bash
# Update paths in convert_faf5_to_nird.py:
FAF5_GDB_PATH = r"C:\Path\To\FAF5_network.gdb"
OUTPUT_DIR = r"C:\Users\alimu\NIRD_Data\soge_clusters\networks\faf5"
TARGET_CRS = 'EPSG:2163'  # US Albers Equal Area

# Run conversion
python convert_faf5_to_nird.py
```

**Outputs**
- `faf5_road_links.gpq` - Real road network (Class 50 centroid connectors filtered out)
- `faf5_road_nodes.gpq` - All network nodes
- `faf5_centroid_nodes.gpq` - FAF zone centroid nodes with CentroidID

**Important**: Centroid connectors (Class==50) are automatically filtered out. These artificial links exist only to connect FAF zone centroids to the network and should not be included in routing.

### 3. Convert OD Matrix

```bash
# Update paths in convert_faf5_od_to_nird.py:
FAF5_OD_PATH = r"C:\Path\To\FAF5_regional_flows.csv"
NETWORK_NODES_PATH = r"C:\Users\alimu\NIRD_Data\soge_clusters\networks\faf5\faf5_road_nodes.gpq"
CENTROID_NODES_PATH = r"C:\Users\alimu\NIRD_Data\soge_clusters\networks\faf5\faf5_centroid_nodes.gpq"

# Run conversion
python convert_faf5_od_to_nird.py
```

**Output**: `faf5_od_matrix.pq`

**Zone mapping methods**
1. **Preferred**: Uses FAF5 centroid nodes directly (CentroidID → nearest real network node)
2. **Fallback**: Uses FAF zone geometries if centroid nodes not available

### 4. Update NIRD Scripts

Modify `scripts/1_network_flow_model_revision.py`:

```python
# Change network loading:
# OLD:
road_links = gpd.read_parquet(
    config["paths"]["soge_clusters"] / 
    "networks/test_subnetwork/GB_road_links_with_bridges_subnetwork.gpq"
)

# NEW:
road_links = gpd.read_parquet(
    config["paths"]["soge_clusters"] / 
    "networks/faf5/faf5_road_links.gpq"
)

# Change OD matrix loading:
# OLD:
od_matrix = gpd.read_parquet(
    config["paths"]["soge_clusters"] / 
    "census_datasets/od_gb_oa_2021_node_subnetwork.pq"
)

# NEW:
od_matrix = pd.read_parquet(
    config["paths"]["soge_clusters"] / 
    "census_datasets/faf5_od_matrix.pq"
)
```

### 5. Test with Subset

For initial testing, filter to a smaller region:

```python
# In convert_faf5_to_nird.py, add after reading:
# Filter to single state for testing
faf5_links = faf5_links[faf5_links['STATE'] == 'VA'].copy()  # Virginia
print(f"Filtered to {len(faf5_links)} links in Virginia")
```

## Coordinate Reference Systems

For US-wide analysis, use:
- **EPSG:2163** - US National Atlas Equal Area (recommended)
- **EPSG:5070** - NAD83 / Conus Albers
- **EPSG:3857** - Web Mercator (for visualization)

For UK data (original NIRD):
- **EPSG:27700** - British National Grid

## Key Differences: FAF5 vs OSM (UK NIRD)

| Aspect | FAF5 (US Freight) | OSM (UK NIRD) |
|--------|-------------------|---------------|
| **Geography** | Continental US | Great Britain |
| **CRS** | EPSG:2163 or 5070 | EPSG:27700 |
| **Link Length** | Miles | Meters |
| **Traffic Type** | Freight tonnage | Passenger vehicles |
| **Road Types** | Numeric Class codes | String classifications |
| **OD Units** | FAF zones (hundreds) | Census OAs (thousands) |
| **Flow Units** | Tons/year | Vehicles/day |
| **Node IDs** | Extracted from geometry | Explicit in OSM |
| **Urban Flag** | Urban_Code field | Derived from area |

## Tonnage to Vehicle Conversion

Default assumptions in `convert_faf5_od_to_nird.py`:

```python
AVG_PAYLOAD = {
    'default': 20.0,    # tons per truck
    'bulk': 25.0,       # coal, minerals
    'container': 20.0,  # manufactured goods
    'food': 18.0,       # perishables
}

# vehicles = tonnage / avg_payload
```

Adjust these based on your freight analysis needs.

## Sample Data Check

After conversion, verify:

```python
import geopandas as gpd
import pandas as pd

# Check links
links = gpd.read_parquet('faf5_road_links.gpq')
print(f"Links: {len(links)}")
print(f"Columns: {links.columns.tolist()}")
print(f"Road types: {links['road_classification'].value_counts()}")
print(f"Length range: {links['length'].min():.1f} - {links['length'].max():.1f} m")

# Check OD matrix
od = pd.read_parquet('faf5_od_matrix.pq')
print(f"\nOD pairs: {len(od)}")
print(f"Total vehicles: {od['Car21'].sum():,}")
print(f"Unique origins: {od['origin_node'].nunique()}")
print(f"Unique destinations: {od['destination_node'].nunique()}")
```

## Next Steps

1. Download FAF5 data from FHWA
2. Run `convert_faf5_to_nird.py` to create network files
3. Run `convert_faf5_od_to_nird.py` to create OD matrix
4. Validate outputs with sample checks
5. Update config.json with FAF5 paths
6. Test Script 1 on small subset
7. Iterate on capacity/speed parameters for freight
8. Run full analysis

## Troubleshooting

**Issue**: Node connectivity errors
- **Solution**: FAF5 may have disconnected components. Filter to largest connected component or specific states.

**Issue**: CRS warnings
- **Solution**: FAF5 geodatabase typically in EPSG:4326 (WGS84). Script will reproject to EPSG:2163.

**Issue**: Missing AB_Lanes/BA_Lanes
- **Solution**: Script defaults to 2 lanes. Check for alternative lane columns in your FAF5 version.

**Issue**: Very large OD matrix
- **Solution**: FAF5 has ~130 zones, resulting in manageable OD pairs. Much smaller than UK census OAs.

**Issue**: Tonnage vs vehicle mismatch
- **Solution**: Adjust conversion factors in `convert_tonnage_to_vehicles()` function.

**Issue**: Centroid connectors in routing analysis
- **Solution**: Class==50 links are automatically filtered. If you see routing through artificial connectors, ensure `filter_centroids=True` (default).

**Issue**: FAF zones not mapping to nodes
- **Solution**: Check that `faf5_centroid_nodes.gpq` exists. If missing, rerun link conversion or provide FAF zone shapefile for fallback method.

---

If you are new to this repository, continue with [BEGINNER_REFERENCE_GUIDE.md](BEGINNER_REFERENCE_GUIDE.md) for the full script inventory, file catalog, and pipeline I/O reference.
