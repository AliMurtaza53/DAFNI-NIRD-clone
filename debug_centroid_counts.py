#!/usr/bin/env python
import geopandas as gpd
import pandas as pd

gdb_path = r'C:\Users\alimu\Desktop\Github\FAF5_Model_Highway_Network\Networks\Geodatabase Format\FAF5Network.gdb'
nodes = gpd.read_file(gdb_path, layer='FAF5_Nodes')

# Check centroids with different filters
centroids_all = nodes[nodes['Centroid'] == 1].copy()
print(f"Total centroids (Centroid==1): {len(centroids_all):,}")

# Filter by StateName contains Virginia
centroids_by_name = centroids_all[centroids_all['StateName'].astype(str).str.contains('Virginia', case=False, na=False)]
print(f"Centroids with StateName containing 'Virginia': {len(centroids_by_name):,}")

# Check what StateName values are in the 195
print(f"\nUnique StateName values in the 195:")
print(centroids_by_name['StateName'].unique())

# Check StateID==51 (Virginia should be 51)
centroids_by_id = centroids_all[centroids_all['StateID'] == 51]
print(f"\nCentrals with StateID==51: {len(centroids_by_id):,}")

# Show what StateIDs are in the centroids
print(f"\nStateID distribution in 195 centroids:")
print(centroids_by_name['StateID'].value_counts())

# The correct filter should be:
va_centroids_correct = nodes[(nodes['Centroid'] == 1) & (nodes['StateID'] == 51)]
print(f"\nCorrect VA centroids (Centroid==1 AND StateID==51): {len(va_centroids_correct):,}")

# Now check the road links - are they including out-of-state nodes on the periphery?
links = gpd.read_file(gdb_path, layer='FAF5_Links')
va_links = links[links['STATE'] == 'VA']
print(f"\n\nVA Links (STATE=='VA'): {len(va_links):,}")

# Extract endpoints from VA links
endpoints = set()
for geom in va_links.geometry:
    if geom.geom_type == 'LineString':
        coords = list(geom.coords)
        if len(coords) > 0:
            endpoints.add((round(coords[0][0], 6), round(coords[0][1], 6)))
            endpoints.add((round(coords[-1][0], 6), round(coords[-1][1], 6)))
    elif geom.geom_type == 'MultiLineString':
        for line in geom.geoms:
            coords = list(line.coords)
            if len(coords) > 0:
                endpoints.add((round(coords[0][0], 6), round(coords[0][1], 6)))
                endpoints.add((round(coords[-1][0], 6), round(coords[-1][1], 6)))

print(f"Unique endpoints from VA links: {len(endpoints):,}")

# Now check: are any of those endpoints outside Virginia?
from shapely.geometry import Point
endpoint_geoms = [Point(x, y) for x, y in endpoints]

# Check which endpoints are within VA state bounds
# For now, just check distance from VA centroid (rough estimate)
# Better: check which state each endpoint falls into

# Load all FAF5 nodes and find which endpoint falls into which state
all_nodes_with_state = nodes[['StateID', 'StateName', 'geometry']].copy()
all_nodes_with_state['StateID'] = all_nodes_with_state['StateID'].fillna(-1)

# For each endpoint, find nearest node to determine state
print("\nChecking state affiliation of endpoints from VA links...")
endpoint_states = {}
for x, y in list(endpoints)[:10]:  # Check first 10 as sample
    pt = Point(x, y)
    distances = all_nodes_with_state.geometry.distance(pt)
    nearest_idx = distances.idxmin()
    state_id = all_nodes_with_state.loc[nearest_idx, 'StateID']
    state_name = all_nodes_with_state.loc[nearest_idx, 'StateName']
    endpoint_states[(x, y)] = (state_id, state_name)

# Sample of endpoint states
print("Sample of endpoint state affiliations (first 10):")
for (x, y), (state_id, state_name) in list(endpoint_states.items())[:10]:
    print(f"  ({x:.2f}, {y:.2f}) -> {state_name} (StateID={state_id})")

# Count non-VA endpoints
non_va_count = sum(1 for state_id, state_name in endpoint_states.values() if state_id != 51)
print(f"\nOut-of-state endpoints in sample: {non_va_count} / {len(endpoint_states)}")

# Check the road node file I created
print(f"\n\nLet me check the actual centroid nodes I used...")
centroid_nodes_path = r'C:\Users\alimu\Desktop\Github\DAFNI-NIRD-clean\results_va_workflow\faf5_centroid_nodes_VA.gpq'
try:
    saved_centroids = gpd.read_parquet(centroid_nodes_path)
    print(f"Saved centroid nodes: {len(saved_centroids):,}")
    
    # What states are represented?
    if 'StateName' in saved_centroids.columns:
        print(f"StateName distribution:")
        print(saved_centroids['StateName'].value_counts())
    if 'StateID' in saved_centroids.columns:
        print(f"StateID distribution:")
        print(saved_centroids['StateID'].value_counts())
except Exception as e:
    print(f"Could not read saved centroids: {e}")
