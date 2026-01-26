# FAF5 Integration Guide for NIRD Codebase

This guide explains how to integrate FAF5 (Freight Analysis Framework) network data into the NIRD codebase that currently uses OSM-based data and igraph.

## Overview of Current NIRD Network Structure

### Required GeoDataFrame Columns for Links:
```python
# Essential columns for NIRD road_links:
- 'from_id'           # Origin node ID
- 'to_id'             # Destination node ID  
- 'e_id'              # Unique edge/link ID
- 'geometry'          # LineString geometry (Shapely)
- 'road_classification'  # Road type classification
- 'length'            # Length in meters
- 'lanes'             # Number of lanes
- 'average_toll_cost' # Toll cost (can be 0)
- 'urban'             # Boolean: urban (1) or rural (0)
- 'averageWidth'      # Road width in meters
- 'road_bridge'       # Is it a bridge? (boolean)

# Optional but useful:
- 'min_z', 'max_z', 'mean_z'  # Elevation data
- 'road_classification_number' # e.g., "M1", "A40"
- 'name_1'            # Road name
```

### Required DataFrame Columns for OD Matrix:
```python
# Essential columns for OD matrix:
- 'origin_node'       # Origin node ID (must match node IDs in network)
- 'destination_node'  # Destination node ID
- 'Car21' or freight flow column  # Flow volume
```

## Step-by-Step FAF5 Integration

### 1. Extract FAF5 Network from GDB

```python
import geopandas as gpd
import pandas as pd
from pathlib import Path

# Read FAF5 geodatabase layers
gdb_path = "path/to/FAF5_network.gdb"

# List available layers
import fiona
layers = fiona.listlayers(gdb_path)
print("Available layers:", layers)

# Read links and nodes
faf5_links = gpd.read_file(gdb_path, layer="Highway_Network_Link")  # Adjust layer name
faf5_nodes = gpd.read_file(gdb_path, layer="Highway_Network_Node")  # Adjust layer name
```

### 2. Map FAF5 Columns to NIRD Schema

```python
def convert_faf5_to_nird_links(faf5_links):
    """
    Convert FAF5 link attributes to NIRD format.
    
    FAF5 typical columns:
    - ID, ANODE, BNODE (node IDs)
    - MILES, KILOMETERS (length)
    - THRULANES, THRULANEAB (lane counts)
    - THRUCAP, THRUCAPAB (capacity)
    - TYPE1, FAF_ZONE (classifications)
    - TOLLS (toll flags)
    - URBAN_CODE (urban area codes)
    """
    
    nird_links = gpd.GeoDataFrame()
    
    # Map basic identifiers
    nird_links['from_id'] = faf5_links['ANODE'].astype(str)
    nird_links['to_id'] = faf5_links['BNODE'].astype(str)
    nird_links['e_id'] = faf5_links['ID'].astype(str)
    
    # Geometry (ensure CRS is appropriate, reproject if needed)
    nird_links['geometry'] = faf5_links.geometry
    if faf5_links.crs != 'EPSG:27700':  # UK National Grid for GB data
        nird_links = nird_links.to_crs('EPSG:27700')  # Or appropriate CRS for US
    
    # Calculate length in meters
    if 'KILOMETERS' in faf5_links.columns:
        nird_links['length'] = faf5_links['KILOMETERS'] * 1000  # km to meters
    elif 'MILES' in faf5_links.columns:
        nird_links['length'] = faf5_links['MILES'] * 1609.34  # miles to meters
    else:
        nird_links['length'] = faf5_links.geometry.length  # Calculate from geometry
    
    # Lane information
    if 'THRULANES' in faf5_links.columns:
        nird_links['lanes'] = faf5_links['THRULANES']
    elif 'THRULANEAB' in faf5_links.columns:
        nird_links['lanes'] = faf5_links['THRULANEAB']
    else:
        nird_links['lanes'] = 2  # Default assumption
    
    # Road classification - map FAF5 types to NIRD categories
    road_class_mapping = {
        1: 'Motorway',      # Interstate
        2: 'A Road',        # Principal arterial
        3: 'A Road',        # Minor arterial
        4: 'B Road',        # Major collector
        5: 'B Road',        # Minor collector
        6: 'Unclassified', # Local
    }
    
    if 'TYPE1' in faf5_links.columns:
        nird_links['road_classification'] = faf5_links['TYPE1'].map(
            road_class_mapping
        ).fillna('Unclassified')
    else:
        nird_links['road_classification'] = 'Unclassified'
    
    # Toll information
    if 'TOLLS' in faf5_links.columns:
        # FAF5 TOLLS: 0=no toll, 1=toll
        nird_links['average_toll_cost'] = faf5_links['TOLLS'] * 5.0  # Adjust factor
    else:
        nird_links['average_toll_cost'] = 0.0
    
    # Urban classification
    if 'URBAN_CODE' in faf5_links.columns:
        nird_links['urban'] = (faf5_links['URBAN_CODE'] > 0).astype(int)
    else:
        nird_links['urban'] = 0  # Default to rural
    
    # Width estimation based on lanes and road type
    nird_links['averageWidth'] = nird_links['lanes'] * 3.5  # 3.5m per lane
    
    # Bridge flag (may not be in FAF5 - set default)
    nird_links['road_bridge'] = False
    
    # Additional useful fields
    nird_links['road_classification_number'] = ''
    nird_links['name_1'] = faf5_links.get('ST_NAME', '')
    
    # Elevation (if available, otherwise set defaults)
    nird_links['min_z'] = 0.0
    nird_links['max_z'] = 0.0
    nird_links['mean_z'] = 0.0
    
    return nird_links


def convert_faf5_to_nird_nodes(faf5_nodes):
    """Convert FAF5 node attributes to NIRD format."""
    
    nird_nodes = gpd.GeoDataFrame()
    
    nird_nodes['id'] = faf5_nodes['ID'].astype(str)
    nird_nodes['geometry'] = faf5_nodes.geometry
    
    # Reproject if needed
    if faf5_nodes.crs != 'EPSG:27700':
        nird_nodes = nird_nodes.to_crs('EPSG:27700')
    
    return nird_nodes
```

### 3. Create FAF5 OD Matrix in NIRD Format

```python
def create_faf5_od_matrix(faf5_od_data, node_mapping=None):
    """
    Convert FAF5 OD flows to NIRD format.
    
    FAF5 OD typical columns:
    - dms_orig, dms_dest (FAF zone IDs)
    - tons_YYYY (tonnage by commodity)
    - value_YYYY (value by commodity)
    
    You need to map FAF zones to network nodes.
    """
    
    od_matrix = pd.DataFrame()
    
    # Map FAF zones to network nodes
    # This requires creating a mapping from FAF zones to nearest network nodes
    if node_mapping is not None:
        od_matrix['origin_node'] = faf5_od_data['dms_orig'].map(node_mapping)
        od_matrix['destination_node'] = faf5_od_data['dms_dest'].map(node_mapping)
    else:
        # Direct mapping if zone IDs match node IDs
        od_matrix['origin_node'] = faf5_od_data['dms_orig'].astype(str)
        od_matrix['destination_node'] = faf5_od_data['dms_dest'].astype(str)
    
    # Aggregate commodity flows (example: total tons)
    # For freight: use tons, for passenger equivalent: convert to vehicles
    flow_columns = [col for col in faf5_od_data.columns if 'tons_' in col]
    if flow_columns:
        od_matrix['Car21'] = faf5_od_data[flow_columns].sum(axis=1)
    else:
        od_matrix['Car21'] = faf5_od_data['tons_2021']  # Or appropriate year
    
    # Remove zero flows
    od_matrix = od_matrix[od_matrix['Car21'] > 0]
    
    return od_matrix


def map_faf_zones_to_nodes(faf_zones_gdf, network_nodes_gdf):
    """
    Create mapping from FAF zones to nearest network nodes.
    
    faf_zones_gdf: GeoDataFrame with FAF zone geometries
    network_nodes_gdf: GeoDataFrame with network node points
    """
    
    # Find centroid of each FAF zone
    faf_zones_gdf['centroid'] = faf_zones_gdf.geometry.centroid
    
    # Find nearest node to each zone centroid
    from shapely.ops import nearest_points
    
    zone_to_node = {}
    for idx, zone in faf_zones_gdf.iterrows():
        zone_id = zone['ZONE_ID']  # Adjust column name
        nearest_node = network_nodes_gdf.sindex.nearest(
            zone['centroid'], return_all=False
        )[1][0]
        node_id = network_nodes_gdf.iloc[nearest_node]['id']
        zone_to_node[zone_id] = node_id
    
    return zone_to_node
```

### 4. Add Missing Attributes for NIRD Functions

```python
def prepare_nird_network(nird_links, flow_capacity_dict, free_flow_speed_dict):
    """
    Add NIRD-specific attributes required for traffic assignment.
    
    Parameters from config files:
    - flow_capacity_dict: {'M': 2500, 'A_dual': 1500, ...}
    - free_flow_speed_dict: {'M': 112, 'A_dual': 97, ...}
    """
    
    # Map road classification to capacity and speed
    road_class_map = {
        'Motorway': 'M',
        'A Road': 'A_dual',  # or 'A_single' based on lanes
        'B Road': 'B',
        'Unclassified': 'B'
    }
    
    nird_links['road_label'] = nird_links['road_classification'].map(road_class_map)
    
    # Set initial capacities (vehicles per hour)
    nird_links['flow_capacity'] = nird_links['road_label'].map(flow_capacity_dict)
    nird_links['flow_capacity'] = nird_links['flow_capacity'].fillna(1500)
    
    # Adjust capacity by number of lanes
    nird_links['flow_capacity'] = nird_links['flow_capacity'] * nird_links['lanes']
    
    # Set free flow speeds (km/h)
    nird_links['free_flow_speed'] = nird_links['road_label'].map(free_flow_speed_dict)
    nird_links['free_flow_speed'] = nird_links['free_flow_speed'].fillna(60)
    
    return nird_links
```

### 5. Integration Script Template

```python
"""
faf5_to_nird_converter.py

Complete script to convert FAF5 data to NIRD format.
"""

import geopandas as gpd
import pandas as pd
from pathlib import Path
import json

def main():
    # Paths
    faf5_gdb = Path("data/FAF5_network.gdb")
    faf5_od_file = Path("data/FAF5_OD_flows.csv")
    output_dir = Path("C:/Users/alimu/NIRD_Data/faf5_network")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Read FAF5 data
    print("Reading FAF5 network...")
    faf5_links = gpd.read_file(faf5_gdb, layer="Highway_Network_Link")
    faf5_nodes = gpd.read_file(faf5_gdb, layer="Highway_Network_Node")
    faf5_od = pd.read_csv(faf5_od_file)
    
    # 2. Convert to NIRD format
    print("Converting links...")
    nird_links = convert_faf5_to_nird_links(faf5_links)
    
    print("Converting nodes...")
    nird_nodes = convert_faf5_to_nird_nodes(faf5_nodes)
    
    # 3. Prepare network attributes
    print("Adding NIRD attributes...")
    
    # Load NIRD config parameters
    with open("config_params/flow_capacity_dict.json", "r") as f:
        flow_capacity_dict = json.load(f)
    with open("config_params/free_flow_speed_dict.json", "r") as f:
        free_flow_speed_dict = json.load(f)
    
    nird_links = prepare_nird_network(
        nird_links, 
        flow_capacity_dict, 
        free_flow_speed_dict
    )
    
    # 4. Create OD matrix
    print("Creating OD matrix...")
    # Option A: Direct mapping if FAF zones match nodes
    nird_od = create_faf5_od_matrix(faf5_od)
    
    # Option B: With zone-to-node mapping
    # faf_zones = gpd.read_file(faf5_gdb, layer="FAF_Zones")
    # zone_mapping = map_faf_zones_to_nodes(faf_zones, nird_nodes)
    # nird_od = create_faf5_od_matrix(faf5_od, zone_mapping)
    
    # 5. Save outputs
    print("Saving converted data...")
    nird_links.to_parquet(output_dir / "FAF5_road_links.gpq")
    nird_nodes.to_parquet(output_dir / "FAF5_road_nodes.gpq")
    nird_od.to_parquet(output_dir / "FAF5_od_matrix.pq")
    
    print(f"Conversion complete!")
    print(f"  Links: {len(nird_links):,}")
    print(f"  Nodes: {len(nird_nodes):,}")
    print(f"  OD pairs: {len(nird_od):,}")
    print(f"  Total flow: {nird_od['Car21'].sum():,.0f}")

if __name__ == "__main__":
    main()
```

### 6. Modify NIRD Scripts to Use FAF5 Data

Update Script 1 to load FAF5 data:

```python
# In scripts/1_network_flow_model_revision.py

# Replace OSM network loading:
# OLD:
# road_link_file = gpd.read_parquet(
#     base_path / "networks" / "test_subnetwork" / "GB_road_links_with_bridges_subnetwork.gpq"
# )

# NEW:
road_link_file = gpd.read_parquet(
    base_path / "networks" / "FAF5_road_links.gpq"
)

# Replace OD matrix loading:
# OLD:
# od_node_2021 = pd.read_parquet(
#     base_path / "census_datasets" / "od_gb_oa_2021_node_with_bridges_subnetwork.pq"
# )

# NEW:
od_node_2021 = pd.read_parquet(
    base_path / "census_datasets" / "FAF5_od_matrix.pq"
)
```

## Key Differences to Handle

### 1. CRS (Coordinate Reference System)
- **OSM/GB data**: EPSG:27700 (British National Grid)
- **FAF5 data**: Typically EPSG:4326 (WGS84) or EPSG:3857 (Web Mercator)
- **Solution**: Reproject FAF5 to appropriate projected CRS (e.g., EPSG:2163 for US Albers)

### 2. Units
- **FAF5**: Miles, tons
- **NIRD**: Meters, vehicles
- **Solution**: Convert in preprocessing

### 3. Road Classification
- **FAF5**: Numeric codes (1-7)
- **NIRD**: String categories (Motorway, A Road, etc.)
- **Solution**: Create mapping dictionary

### 4. Freight vs Passenger
- **FAF5**: Freight tonnage
- **NIRD**: Passenger vehicles
- **Solution**: Convert tons to truck equivalents or keep as freight units

## Testing the Integration

```python
# Test script to verify conversion
def test_faf5_nird_conversion():
    import geopandas as gpd
    import pandas as pd
    
    # Load converted data
    links = gpd.read_parquet("output/FAF5_road_links.gpq")
    nodes = gpd.read_parquet("output/FAF5_road_nodes.gpq")
    od = pd.read_parquet("output/FAF5_od_matrix.pq")
    
    # Check required columns
    required_link_cols = ['from_id', 'to_id', 'e_id', 'geometry', 'length', 'lanes']
    assert all(col in links.columns for col in required_link_cols)
    
    # Check node references
    node_ids = set(nodes['id'])
    link_from_ids = set(links['from_id'])
    link_to_ids = set(links['to_id'])
    assert link_from_ids.issubset(node_ids), "Some from_id not in nodes"
    assert link_to_ids.issubset(node_ids), "Some to_id not in nodes"
    
    # Check OD matrix
    od_origin_ids = set(od['origin_node'])
    od_dest_ids = set(od['destination_node'])
    assert od_origin_ids.issubset(node_ids), "Some OD origins not in network"
    assert od_dest_ids.issubset(node_ids), "Some OD destinations not in network"
    
    print("✅ All validation checks passed!")
    print(f"Network: {len(links)} links, {len(nodes)} nodes")
    print(f"OD Matrix: {len(od)} pairs, {od['Car21'].sum():,.0f} total flow")

if __name__ == "__main__":
    test_faf5_nird_conversion()
```

## Next Steps

1. **Obtain FAF5 data** from FHWA website
2. **Create conversion script** using templates above
3. **Test with small subset** first
4. **Validate network connectivity** using igraph
5. **Run NIRD Script 1** with FAF5 data
6. **Adjust parameters** (capacity, speed) for US context

## Additional Resources

- FAF5 Documentation: https://ops.fhwa.dot.gov/freight/freight_analysis/faf/
- NIRD igraph documentation: See `src/nird/road_revised.py`
- TransCAD format specifications: Contact Caliper for documentation
