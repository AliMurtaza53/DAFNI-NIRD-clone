"""
Convert FAF5 Network Data to NIRD Format

This script converts FAF5 (Freight Analysis Framework) geodatabase format
to NIRD-compatible GeoParquet format based on actual FAF5 schema.

FAF5 Link Schema (as of V2021.05):
- ID: Link identifier
- LENGTH: Link length in miles
- DIR: Direction (0=bidirectional, 1=one-way)
- Class: Road classification code (1-19)
- Class_Description: Text description of road class
- AB_Lanes, BA_Lanes: Lanes in each direction
- Speed_Limit: Posted speed limit (mph)
- Urban_Code: Urban area code (99999 = rural)
- FAFZONE: FAF zone identifier
- Various toll and state attributes
"""

import geopandas as gpd
import pandas as pd
from pathlib import Path
import fiona


# Road classification mapping: FAF5 Class -> NIRD road_classification
CLASS_MAPPING = {
    1: 'motorway',           # Interstate
    2: 'trunk',              # Principal Arterial - Freeways
    3: 'primary',            # Principal Arterial - Other
    4: 'primary',            # Minor Arterial
    5: 'secondary',          # Major Collector
    6: 'tertiary',           # Minor Collector
    7: 'unclassified',       # Local
    8: 'motorway_link',      # Ramp
    9: 'service',            # Service/Frontage Road
    19: 'service',           # Facility Access/Circulator
    50: 'centroid_connector' # Centroid connector (will be filtered)
}

# Default parameters if missing in FAF5 data
DEFAULTS = {
    'lanes': 2,
    'average_toll_cost': 0.0,
    'road_bridge': 'no',
    'meters_per_lane': 3.5,
}


def list_gdb_layers(gdb_path):
    """List all available layers in a geodatabase."""
    layers = fiona.listlayers(gdb_path)
    print(f"Available layers in {gdb_path}:")
    for i, layer in enumerate(layers, 1):
        print(f"  {i}. {layer}")
    return layers


def extract_node_connectivity(faf5_links, link_id_col='ID', faf5_nodes=None):
    """
    Extract node connectivity from link geometry.
    
    If FAF5 has explicit node IDs (ANODE/BNODE columns), use those.
    Otherwise, extract from geometry endpoints.
    
    Args:
        faf5_links: GeoDataFrame with link data
        link_id_col: Column name for link ID
        faf5_nodes: Optional GeoDataFrame with node data (for filtering centroids)
    
    Returns:
        from_ids, to_ids, nodes dictionary
    """
    # Check if FAF5 has explicit node columns
    if 'ANODE' in faf5_links.columns and 'BNODE' in faf5_links.columns:
        print("Using explicit ANODE/BNODE from FAF5 data...")
        from_ids = faf5_links['ANODE'].tolist()
        to_ids = faf5_links['BNODE'].tolist()
        
        # Create nodes dictionary from unique node IDs
        all_nodes = set(from_ids + to_ids)
        nodes = {node_id: node_id for node_id in all_nodes}
        
        print(f"  Found {len(nodes)} unique nodes from ANODE/BNODE")
        return from_ids, to_ids, nodes
    
    # Otherwise extract from geometry
    print("Extracting node connectivity from link geometry...")
    
    nodes = {}
    node_id = 0
    
    def get_or_create_node(coord):
        nonlocal node_id
        # Round coordinates to avoid floating point issues
        key = (round(coord[0], 6), round(coord[1], 6))
        if key not in nodes:
            nodes[key] = node_id
            node_id += 1
        return nodes[key]
    
    from_ids = []
    to_ids = []
    
    for geom in faf5_links.geometry:
        coords = list(geom.coords)
        from_ids.append(get_or_create_node(coords[0]))
        to_ids.append(get_or_create_node(coords[-1]))
    
    print(f"  Created {len(nodes)} unique nodes from geometry")
    return from_ids, to_ids, nodes


def filter_centroid_connectors(faf5_links):
    """
    Filter out centroid connector links (Class==50).
    
    Centroid connectors are artificial links connecting FAF zone centroids
    to the actual road network. They should be excluded from routing analysis.
    
    Args:
        faf5_links: GeoDataFrame with FAF5 link data
    
    Returns:
        Filtered GeoDataFrame without centroid connectors
    """
    original_count = len(faf5_links)
    
    if 'Class' in faf5_links.columns:
        centroid_connectors = faf5_links['Class'] == 50
        filtered = faf5_links[~centroid_connectors].copy()
        removed = centroid_connectors.sum()
        
        if removed > 0:
            print(f"\nFiltering centroid connectors:")
            print(f"  Removed {removed} Class==50 centroid connector links")
            print(f"  Remaining: {len(filtered)} real road links")
        
        return filtered
    else:
        print("  Warning: 'Class' column not found, cannot filter centroid connectors")
        return faf5_links


def convert_faf5_links_to_nird(faf5_links, target_crs='EPSG:2163', filter_centroids=True):
    """
    Convert FAF5 link GeoDataFrame to NIRD format.
    
    Args:
        faf5_links: GeoDataFrame with FAF5 link data
        target_crs: Target coordinate reference system (default: US Albers Equal Area)
                   Use 'EPSG:27700' for UK, 'EPSG:2163' for continental US
        filter_centroids: If True, remove Class==50 centroid connector links
    
    Returns:
        GeoDataFrame in NIRD format
    """
    # Filter centroid connectors first
    if filter_centroids:
        faf5_links = filter_centroid_connectors(faf5_links)
    
    print(f"\nConverting {len(faf5_links)} FAF5 links to NIRD format...")
    
    nird_links = gpd.GeoDataFrame()
    
    # 1. Edge ID
    nird_links['e_id'] = faf5_links['ID'].astype(str)
    print(f"  ✓ e_id: {len(nird_links['e_id'].unique())} unique links")
    
    # 2. Extract node connectivity
    from_ids, to_ids, nodes = extract_node_connectivity(faf5_links, 'ID')
    nird_links['from_id'] = from_ids
    nird_links['to_id'] = to_ids
    print(f"  ✓ from_id/to_id: {len(nodes)} nodes")
    
    # 3. Geometry - reproject if needed
    nird_links['geometry'] = faf5_links.geometry
    if faf5_links.crs != target_crs:
        print(f"  Reprojecting from {faf5_links.crs} to {target_crs}...")
        nird_links = nird_links.set_crs(faf5_links.crs, allow_override=True)
        nird_links = nird_links.to_crs(target_crs)
    else:
        nird_links = nird_links.set_crs(target_crs)
    
    # 4. Length - convert miles to meters
    if 'LENGTH' in faf5_links.columns:
        nird_links['length'] = faf5_links['LENGTH'] * 1609.34
    else:
        # Calculate from geometry
        nird_links['length'] = nird_links.geometry.length
    print(f"  ✓ length: {nird_links['length'].min():.1f} to {nird_links['length'].max():.1f} meters")
    
    # 5. Road classification - map from Class code
    if 'Class' in faf5_links.columns:
        nird_links['road_classification'] = faf5_links['Class'].map(CLASS_MAPPING)
        # Fill any unmapped values with 'unclassified'
        nird_links['road_classification'].fillna('unclassified', inplace=True)
    else:
        nird_links['road_classification'] = 'unclassified'
    print(f"  ✓ road_classification: {nird_links['road_classification'].nunique()} types")
    
    # 6. Lanes - take maximum of both directions
    if 'AB_Lanes' in faf5_links.columns and 'BA_Lanes' in faf5_links.columns:
        nird_links['lanes'] = faf5_links[['AB_Lanes', 'BA_Lanes']].max(axis=1)
    elif 'AB_Lanes' in faf5_links.columns:
        nird_links['lanes'] = faf5_links['AB_Lanes']
    else:
        nird_links['lanes'] = DEFAULTS['lanes']
    
    # Fill missing lanes with default
    nird_links['lanes'].fillna(DEFAULTS['lanes'], inplace=True)
    nird_links['lanes'] = nird_links['lanes'].astype(int)
    print(f"  ✓ lanes: {nird_links['lanes'].min()} to {nird_links['lanes'].max()}")
    
    # 7. Urban classification - based on Urban_Code
    if 'Urban_Code' in faf5_links.columns:
        # 99999 typically indicates rural areas in FAF5
        nird_links['urban'] = (faf5_links['Urban_Code'] != 99999).astype(int)
    else:
        nird_links['urban'] = 0  # Default to rural
    print(f"  ✓ urban: {nird_links['urban'].sum()} urban, {(~nird_links['urban'].astype(bool)).sum()} rural")
    
    # 8. Average width - estimated from lanes
    nird_links['averageWidth'] = nird_links['lanes'] * DEFAULTS['meters_per_lane']
    
    # 9. Toll cost - check toll fields
    if 'Toll_Type' in faf5_links.columns:
        # If Toll_Type is not null, we could estimate cost, but default to 0
        nird_links['average_toll_cost'] = DEFAULTS['average_toll_cost']
    else:
        nird_links['average_toll_cost'] = DEFAULTS['average_toll_cost']
    
    # 10. Bridge indicator - default to 'no'
    nird_links['road_bridge'] = DEFAULTS['road_bridge']
    
    # 11. Optional: Copy useful attributes
    optional_columns = ['Road_Name', 'STATE', 'County_Name', 'FAFZONE', 
                       'Speed_Limit', 'AB_FinalSpeed', 'BA_FinalSpeed']
    for col in optional_columns:
        if col in faf5_links.columns:
            nird_links[col] = faf5_links[col]
    
    # Report summary
    print(f"\n✓ Conversion complete: {len(nird_links)} links")
    print(f"  Road types: {dict(nird_links['road_classification'].value_counts())}")
    
    return nird_links


def create_node_geodataframe(nodes_dict, crs='EPSG:2163'):
    """
    Create a GeoDataFrame of nodes from the connectivity dictionary.
    
    Args:
        nodes_dict: Dictionary mapping (lon, lat) -> node_id
        crs: Coordinate reference system
    
    Returns:
        GeoDataFrame with node geometries
    """
    from shapely.geometry import Point
    
    node_data = []
    for (lon, lat), node_id in nodes_dict.items():
        node_data.append({
            'node_id': node_id,
            'geometry': Point(lon, lat)
        })
    
    nodes_gdf = gpd.GeoDataFrame(node_data, crs=crs)
    print(f"\nCreated node GeoDataFrame: {len(nodes_gdf)} nodes")
    
    return nodes_gdf


def validate_nird_network(links_gdf):
    """Validate that the converted network has all required NIRD columns."""
    required_cols = ['from_id', 'to_id', 'e_id', 'geometry', 'length', 
                     'lanes', 'road_classification', 'average_toll_cost', 
                     'urban', 'averageWidth', 'road_bridge']
    
    missing = [col for col in required_cols if col not in links_gdf.columns]
    
    if missing:
        print(f"\n⚠ Warning: Missing required columns: {missing}")
        return False
    else:
        print(f"\n✓ Validation passed: All required columns present")
        return True


def main():
    """Main conversion workflow."""
    
    # Configuration
    FAF5_GDB_PATH = r"C:\Path\To\FAF5_network.gdb"  # UPDATE THIS PATH
    OUTPUT_DIR = Path(r"C:\Users\alimu\NIRD_Data\soge_clusters\networks\faf5")
    TARGET_CRS = 'EPSG:2163'  # US Albers Equal Area projection
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 1: List available layers
    print("=" * 80)
    print("FAF5 to NIRD Network Conversion")
    print("=" * 80)
    
    layers = list_gdb_layers(FAF5_GDB_PATH)
    
    # Step 2: Read FAF5 links (adjust layer name as needed)
    link_layer = "Highway_Network_Link"  # Common FAF5 layer name
    node_layer = "Highway_Network_Node"  # Node layer
    
    print(f"\nReading layer: {link_layer}")
    faf5_links = gpd.read_file(FAF5_GDB_PATH, layer=link_layer)
    
    print(f"  Read {len(faf5_links)} links")
    print(f"  CRS: {faf5_links.crs}")
    print(f"  Columns: {list(faf5_links.columns)}")
    
    # Also read nodes to identify centroids
    print(f"\nReading layer: {node_layer}")
    try:
        faf5_nodes = gpd.read_file(FAF5_GDB_PATH, layer=node_layer)
        print(f"  Read {len(faf5_nodes)} nodes")
        
        # Check for centroid information
        if 'Centroid' in faf5_nodes.columns:
            centroid_count = (faf5_nodes['Centroid'] == 1).sum()
            print(f"  Found {centroid_count} centroid nodes (FAF zone centroids)")
            print(f"  Found {len(faf5_nodes) - centroid_count} real network nodes")
        
        # Save centroid nodes for zone mapping
        centroid_nodes_path = OUTPUT_DIR / "faf5_centroid_nodes.gpq"
        if 'Centroid' in faf5_nodes.columns:
            centroids = faf5_nodes[faf5_nodes['Centroid'] == 1].copy()
            centroids.to_parquet(centroid_nodes_path)
            print(f"  ✓ Saved {len(centroids)} centroid nodes to: {centroid_nodes_path}")
    except Exception as e:
        print(f"  Warning: Could not read nodes layer: {e}")
        faf5_nodes = None
    
    # Step 3: Convert to NIRD format
    nird_links = convert_faf5_links_to_nird(faf5_links, target_crs=TARGET_CRS)
    
    # Step 4: Validate
    validate_nird_network(nird_links)
    
    # Step 5: Save to GeoParquet
    output_path = OUTPUT_DIR / "faf5_road_links.gpq"
    print(f"\nSaving to: {output_path}")
    nird_links.to_parquet(output_path)
    print(f"✓ Saved {len(nird_links)} links")
    
    # Optional: Save nodes as well
    # Extract nodes dictionary from the conversion
    _, _, nodes = extract_node_connectivity(faf5_links)
    nodes_gdf = create_node_geodataframe(nodes, crs=TARGET_CRS)
    nodes_output_path = OUTPUT_DIR / "faf5_road_nodes.gpq"
    nodes_gdf.to_parquet(nodes_output_path)
    print(f"✓ Saved {len(nodes_gdf)} nodes to: {nodes_output_path}")
    
    print("\n" + "=" * 80)
    print("Conversion complete!")
    print("=" * 80)
    
    return nird_links


if __name__ == "__main__":
    main()
