"""
Convert FAF5 Origin-Destination Data to NIRD Format

This script converts FAF5 OD flow data (by FAF zone) to NIRD's
node-to-node OD matrix format.

FAF5 OD Flow Structure:
- Origin FAF Zone (dms_orig)
- Destination FAF Zone (dms_dest) 
- Commodity type (sctg2)
- Mode (dms_mode)
- Tonnage values by year
- Value in dollars

NIRD OD Format Required:
- origin_node: Network node ID
- destination_node: Network node ID
- Car21: Flow volume (vehicles or freight units)
"""

import pandas as pd
import geopandas as gpd
from pathlib import Path
import numpy as np


def load_faf5_od_data(faf5_od_path):
    """
    Load FAF5 OD flow data.
    
    Args:
        faf5_od_path: Path to FAF5 OD CSV or database file
        
    Returns:
        DataFrame with FAF zone-to-zone flows
    """
    print(f"Loading FAF5 OD data from: {faf5_od_path}")
    
    # FAF5 data might be in CSV or database format
    if str(faf5_od_path).endswith('.csv'):
        df = pd.read_csv(faf5_od_path)
    else:
        # If in geodatabase, read appropriate table
        import geopandas as gpd
        df = gpd.read_file(faf5_od_path, layer='FAF5_OD_Flows')  # Adjust layer name
    
    print(f"  Loaded {len(df)} OD records")
    print(f"  Columns: {list(df.columns)}")
    
    return df


def load_faf_zone_centroids(faf_zones_path):
    """
    Load FAF zone boundaries and calculate centroids.
    
    Args:
        faf_zones_path: Path to FAF zone shapefile or GDB layer
        
    Returns:
        GeoDataFrame with FAF zone geometries and centroids
    """
    print(f"\nLoading FAF zones from: {faf_zones_path}")
    
    faf_zones = gpd.read_file(faf_zones_path)
    
    # Calculate centroids
    faf_zones['centroid'] = faf_zones.geometry.centroid
    
    print(f"  Loaded {len(faf_zones)} FAF zones")
    
    return faf_zones


def map_faf_zones_to_network_nodes(faf_zones=None, network_nodes=None, centroid_nodes_path=None):
    """
    Map each FAF zone to network nodes.
    
    Two methods:
    1. If centroid_nodes_path provided: Use FAF5's built-in centroid nodes
       with CentroidID to directly map zones to nodes
    2. If faf_zones provided: Map zone geometries to nearest network nodes
    
    Args:
        faf_zones: Optional GeoDataFrame with FAF zone geometries
        network_nodes: GeoDataFrame with network nodes
        centroid_nodes_path: Optional path to saved FAF5 centroid nodes
        
    Returns:
        Dictionary mapping FAF zone ID -> network node ID
    """
    print("\nMapping FAF zones to network nodes...")
    
    # Method 1: Use FAF5's centroid nodes directly
    if centroid_nodes_path and Path(centroid_nodes_path).exists():
        print("  Using FAF5 centroid nodes (Method 1: Direct CentroidID mapping)")
        centroid_nodes = gpd.read_parquet(centroid_nodes_path)
        
        zone_to_node = {}
        
        if 'CentroidID' in centroid_nodes.columns and 'node_id' in centroid_nodes.columns:
            # Direct mapping from CentroidID to node_id
            for idx, row in centroid_nodes.iterrows():
                zone_id = row['CentroidID']  # This is the FAF zone identifier
                
                # Find nearest real network node to this centroid
                distances = network_nodes.geometry.distance(row.geometry)
                nearest_node_idx = distances.idxmin()
                nearest_node_id = network_nodes.loc[nearest_node_idx, 'node_id']
                
                zone_to_node[zone_id] = nearest_node_id
            
            print(f"  Mapped {len(zone_to_node)} FAF zones via centroid nodes")
            return zone_to_node
    
    # Method 2: Use zone geometries
    if faf_zones is not None and network_nodes is not None:
        print("  Using FAF zone geometries (Method 2: Spatial proximity)")
        
        # Ensure same CRS
        if faf_zones.crs != network_nodes.crs:
            print(f"  Reprojecting FAF zones from {faf_zones.crs} to {network_nodes.crs}")
            faf_zones = faf_zones.to_crs(network_nodes.crs)
        
        zone_to_node = {}
        
        for idx, zone in faf_zones.iterrows():
            zone_id = zone['FAFZONE'] if 'FAFZONE' in zone else zone.name
            zone_centroid = zone.geometry.centroid
            
            # Find nearest network node
            distances = network_nodes.geometry.distance(zone_centroid)
            nearest_node_idx = distances.idxmin()
            nearest_node_id = network_nodes.loc[nearest_node_idx, 'node_id']
            
            zone_to_node[zone_id] = nearest_node_id
        
        print(f"  Mapped {len(zone_to_node)} FAF zones to network nodes")
        return zone_to_node
    
    raise ValueError("Must provide either centroid_nodes_path or (faf_zones + network_nodes)")


def convert_tonnage_to_vehicles(tonnage, commodity_type='all', year=2021):
    """
    Convert freight tonnage to equivalent number of vehicles.
    
    Args:
        tonnage: Freight weight in tons
        commodity_type: SCTG commodity code (optional)
        year: Data year
        
    Returns:
        Estimated number of vehicles
        
    Assumptions:
        - Average truck payload: 15-25 tons depending on commodity
        - Can be refined based on commodity type
    """
    # Average truck payload in tons
    AVG_PAYLOAD = {
        'default': 20.0,
        'bulk': 25.0,      # Coal, minerals
        'container': 20.0,  # Manufactured goods
        'food': 18.0,      # Perishables
    }
    
    payload = AVG_PAYLOAD.get(commodity_type, AVG_PAYLOAD['default'])
    
    # Calculate vehicles needed
    vehicles = tonnage / payload
    
    return max(1, round(vehicles))  # At least 1 vehicle


def aggregate_faf5_flows(faf5_od, year_column='tons_2021', mode_filter='Truck'):
    """
    Aggregate FAF5 OD flows by origin-destination pairs.
    
    Args:
        faf5_od: DataFrame with FAF5 OD flows
        year_column: Column with tonnage data (e.g., 'tons_2021')
        mode_filter: Transportation mode to filter (e.g., 'Truck')
        
    Returns:
        Aggregated DataFrame with zone-to-zone flows
    """
    print(f"\nAggregating FAF5 flows for mode: {mode_filter}, year: {year_column}")
    
    # Filter by mode if specified
    if mode_filter and 'dms_mode' in faf5_od.columns:
        faf5_od = faf5_od[faf5_od['dms_mode'] == mode_filter].copy()
        print(f"  Filtered to {len(faf5_od)} {mode_filter} records")
    
    # Group by origin-destination pairs and sum tonnage
    agg_cols = ['dms_orig', 'dms_dest']
    
    if year_column not in faf5_od.columns:
        print(f"  Warning: Column {year_column} not found. Available: {list(faf5_od.columns)}")
        # Try to find a tonnage column
        tonnage_cols = [col for col in faf5_od.columns if 'tons' in col.lower()]
        if tonnage_cols:
            year_column = tonnage_cols[0]
            print(f"  Using {year_column} instead")
    
    od_flows = faf5_od.groupby(agg_cols)[year_column].sum().reset_index()
    od_flows.columns = ['origin_zone', 'destination_zone', 'tonnage']
    
    print(f"  Aggregated to {len(od_flows)} unique OD pairs")
    print(f"  Total tonnage: {od_flows['tonnage'].sum():,.0f} tons")
    
    return od_flows


def convert_faf5_od_to_nird(faf5_od_flows, zone_to_node_mapping):
    """
    Convert FAF5 zone-to-zone flows to NIRD node-to-node OD matrix.
    
    Args:
        faf5_od_flows: DataFrame with aggregated zone-to-zone flows
        zone_to_node_mapping: Dictionary mapping FAF zone -> network node
        
    Returns:
        DataFrame in NIRD OD format
    """
    print("\nConverting FAF5 OD to NIRD format...")
    
    nird_od = []
    skipped = 0
    
    for idx, row in faf5_od_flows.iterrows():
        origin_zone = row['origin_zone']
        dest_zone = row['destination_zone']
        tonnage = row['tonnage']
        
        # Map zones to nodes
        if origin_zone not in zone_to_node_mapping:
            skipped += 1
            continue
        if dest_zone not in zone_to_node_mapping:
            skipped += 1
            continue
        
        origin_node = zone_to_node_mapping[origin_zone]
        dest_node = zone_to_node_mapping[dest_zone]
        
        # Convert tonnage to vehicles
        vehicles = convert_tonnage_to_vehicles(tonnage)
        
        nird_od.append({
            'origin_node': origin_node,
            'destination_node': dest_node,
            'Car21': vehicles,
            'tonnage': tonnage  # Keep original tonnage for reference
        })
    
    nird_od_df = pd.DataFrame(nird_od)
    
    print(f"  Converted {len(nird_od_df)} OD pairs")
    if skipped > 0:
        print(f"  Skipped {skipped} pairs due to missing zone mappings")
    print(f"  Total vehicles: {nird_od_df['Car21'].sum():,.0f}")
    
    return nird_od_df


def validate_nird_od(od_df, network_nodes):
    """
    Validate that OD matrix nodes exist in the network.
    
    Args:
        od_df: NIRD OD matrix DataFrame
        network_nodes: GeoDataFrame with network nodes
        
    Returns:
        Boolean indicating if validation passed
    """
    print("\nValidating NIRD OD matrix...")
    
    node_ids = set(network_nodes['node_id'].values)
    origin_nodes = set(od_df['origin_node'].values)
    dest_nodes = set(od_df['destination_node'].values)
    
    all_od_nodes = origin_nodes.union(dest_nodes)
    missing_nodes = all_od_nodes - node_ids
    
    if missing_nodes:
        print(f"  ⚠ Warning: {len(missing_nodes)} OD nodes not found in network")
        print(f"    Examples: {list(missing_nodes)[:5]}")
        return False
    else:
        print(f"  ✓ All {len(all_od_nodes)} OD nodes exist in network")
        return True


def main():
    """Main OD conversion workflow."""
    
    # Configuration - UPDATE THESE PATHS
    FAF5_OD_PATH = r"C:\Path\To\FAF5_regional_flows_origin_destination.csv"
    FAF_ZONES_PATH = r"C:\Path\To\FAF5_zones.gdb"  # Or shapefile (optional)
    NETWORK_NODES_PATH = r"C:\Users\alimu\NIRD_Data\soge_clusters\networks\faf5\faf5_road_nodes.gpq"
    CENTROID_NODES_PATH = r"C:\Users\alimu\NIRD_Data\soge_clusters\networks\faf5\faf5_centroid_nodes.gpq"  # From link conversion
    OUTPUT_DIR = Path(r"C:\Users\alimu\NIRD_Data\soge_clusters\census_datasets")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("FAF5 OD to NIRD OD Matrix Conversion")
    print("=" * 80)
    
    # Step 1: Load FAF5 OD data
    faf5_od = load_faf5_od_data(FAF5_OD_PATH)
    
    # Step 2: Aggregate flows (truck mode, 2021 data)
    faf5_od_agg = aggregate_faf5_flows(
        faf5_od, 
        year_column='tons_2021',  # Adjust year as needed
        mode_filter='Truck'
    )
    
    # Step 3: Load network nodes
    print(f"\nLoading network nodes from: {NETWORK_NODES_PATH}")
    network_nodes = gpd.read_parquet(NETWORK_NODES_PATH)
    print(f"  Loaded {len(network_nodes)} network nodes")
    
    # Step 4: Map FAF zones to network nodes
    # Try using centroid nodes first (if available from link conversion)
    if Path(CENTROID_NODES_PATH).exists():
        print(f"Found centroid nodes file: {CENTROID_NODES_PATH}")
        zone_to_node = map_faf_zones_to_network_nodes(
            network_nodes=network_nodes,
            centroid_nodes_path=CENTROID_NODES_PATH
        )
    else:
        # Fall back to using FAF zone geometries
        print(f"Centroid nodes not found, using FAF zone geometries")
        faf_zones = load_faf_zone_centroids(FAF_ZONES_PATH)
        zone_to_node = map_faf_zones_to_network_nodes(
            faf_zones=faf_zones,
            network_nodes=network_nodes
        )
    
    # Step 5: Convert to NIRD format
    nird_od = convert_faf5_od_to_nird(faf5_od_agg, zone_to_node)
    
    # Step 6: Validate
    validate_nird_od(nird_od, network_nodes)
    
    # Step 7: Save
    output_path = OUTPUT_DIR / "faf5_od_matrix.pq"
    print(f"\nSaving NIRD OD matrix to: {output_path}")
    nird_od.to_parquet(output_path, index=False)
    print(f"✓ Saved {len(nird_od)} OD pairs")
    
    # Summary statistics
    print("\n" + "=" * 80)
    print("Conversion Summary")
    print("=" * 80)
    print(f"Total OD pairs: {len(nird_od):,}")
    print(f"Total vehicles: {nird_od['Car21'].sum():,}")
    print(f"Total tonnage: {nird_od['tonnage'].sum():,.0f} tons")
    print(f"Avg vehicles per OD: {nird_od['Car21'].mean():.1f}")
    print(f"Max vehicles for single OD: {nird_od['Car21'].max():,}")
    
    return nird_od


if __name__ == "__main__":
    main()
