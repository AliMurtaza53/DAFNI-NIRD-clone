#!/usr/bin/env python
import geopandas as gpd
from pathlib import Path

gdb_path = r'C:\Users\alimu\Desktop\Github\FAF5_Model_Highway_Network\Networks\Geodatabase Format\FAF5Network.gdb'
nodes = gpd.read_file(gdb_path, layer='FAF5_Nodes')

# Show centroids info
centroids = nodes[nodes['Centroid'] == 1].copy()
print(f'Total Centroid==1 nodes: {len(centroids):,}')
print(f'\nColumns in FAF5_Nodes:')
print(list(nodes.columns))

# Check StateName column
if 'StateName' in nodes.columns:
    print(f'\nUnique StateName values (first 15):')
    print(nodes['StateName'].unique()[:15])
    print(f'\nVirginia StateName values:')
    va_by_name = nodes[nodes['StateName'].str.contains('Virginia', case=False, na=False)]
    print(f'  Matches with "Virginia": {len(va_by_name):,}')
    va_centroids_by_name = centroids[centroids['StateName'].str.contains('Virginia', case=False, na=False)]
    print(f'  VA Centroids (by StateName): {len(va_centroids_by_name):,}')

# Check for State column
if 'State' in nodes.columns:
    print(f'\nUnique State values: {nodes["State"].unique()}')
    va_by_abbr = nodes[nodes['State'] == 'VA']
    print(f'  Matches with State==VA: {len(va_by_abbr):,}')
    va_centroids_by_abbr = centroids[centroids['State'] == 'VA']
    print(f'  VA Centroids (by State): {len(va_centroids_by_abbr):,}')

# Check StateNameAbb or similar
for col in nodes.columns:
    if 'state' in col.lower():
        print(f'\nColumn {col}:')
        print(f'  Unique values (first 10): {nodes[col].unique()[:10]}')
        va_matches = nodes[nodes[col].astype(str).str.upper() == 'VA']
        print(f'  VA matches: {len(va_matches):,}')

# Show FAFID info
if 'FAFID' in centroids.columns:
    print(f'\nVA Centroid FAFIDs:')
    va_centroids_sample = centroids[centroids['StateName'].str.contains('Virginia', case=False, na=False)]['FAFID'].unique()
    print(f'  Total unique FAFIDs: {len(va_centroids_sample):,}')
    print(f'  First 20: {sorted(va_centroids_sample)[:20]}')
