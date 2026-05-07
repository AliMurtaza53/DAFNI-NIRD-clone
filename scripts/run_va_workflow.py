"""
Virginia FAF5-to-NIRD workflow.

This script starts from the FAF5 GDB, clips the road network to Virginia,
extracts Virginia centroid connectors, and builds a synthetic OD matrix using
an inverse-distance model with a 25M trip benchmark.

It reuses the existing converter helpers in `convert_faf5_to_nird.py` and
`convert_faf5_od_to_nird.py` so the workflow stays aligned with the repo's
standard conversion logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import fiona


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import convert_faf5_to_nird as links_conv  # noqa: E402
import convert_faf5_od_to_nird as od_conv  # noqa: E402


DEFAULT_GDB_PATH = (
    r"C:\Users\alimu\Desktop\Github\FAF5_Model_Highway_Network\Networks\Geodatabase Format\FAF5Network.gdb"
)
DEFAULT_TARGET_CRS = "EPSG:2163"
DEFAULT_TOTAL_TRIPS = 25_000_000
DEFAULT_STATE = "VA"


def load_config() -> dict:
    config_path = REPO_ROOT / "config.json"
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text())


def load_gdb_layers(gdb_path: Path):
    print(f"Loading FAF5 GDB from: {gdb_path}")
    print("Available layers:", fiona.listlayers(str(gdb_path)))
    links = gpd.read_file(gdb_path, layer="FAF5_Links")
    nodes = gpd.read_file(gdb_path, layer="FAF5_Nodes")
    print(f"Loaded {len(links):,} links and {len(nodes):,} nodes")
    return links, nodes


def normalize_state_filter(state_value: str | list[str] | None):
    if state_value is None:
        return None
    if isinstance(state_value, str):
        state_value = [state_value]
    return [value.strip().upper() for value in state_value if value and value.strip()]


def filter_va_centroids(nodes: gpd.GeoDataFrame, state_name: str = "Virginia") -> gpd.GeoDataFrame:
    """Extract all centroid nodes for a given state.
    
    FAF5 centroid nodes are marked with Centroid==1. For Virginia, we use
    StateName to filter (not State abbreviation, as StateName has more matches).
    
    Args:
        nodes: FAF5_Nodes GeoDataFrame
        state_name: Full state name (e.g., 'Virginia')
        
    Returns:
        GeoDataFrame with all centroid nodes for the state
    """
    if "Centroid" not in nodes.columns:
        raise ValueError("FAF5_Nodes layer does not have a 'Centroid' column")

    centroids = nodes[nodes["Centroid"] == 1].copy()
    
    # Filter by StateName (preferred over State abbreviation as it has more matches)
    if "StateName" in centroids.columns:
        centroids = centroids[centroids["StateName"].astype(str).str.contains(state_name, case=False, na=False)]
    
    print(f"{state_name} centroids: {len(centroids):,} (Centroid==1 with matching StateName)")
    return centroids


def build_nodes_from_link_connectivity(nird_links: gpd.GeoDataFrame, crs: str):
    _, _, nodes_dict = links_conv.extract_node_connectivity(nird_links, link_id_col="e_id")
    return links_conv.create_node_geodataframe(nodes_dict, crs=crs)


def save_gdf(gdf: gpd.GeoDataFrame, path: Path, layer: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".pq", ".gpq", ".parquet"}:
        gdf.to_parquet(path, index=False)
    else:
        gdf.to_file(path, driver="GPKG", layer=layer)
    print(f"Wrote {len(gdf):,} rows to {path}")


def build_inverse_distance_od(
    centroid_nodes: gpd.GeoDataFrame,
    road_nodes: gpd.GeoDataFrame,
    total_trips: int,
    decay_power: float = 1.0,
    min_distance_m: float = 1.0,
) -> pd.DataFrame:
    """Build synthetic OD matrix using all centroid nodes (not just FAF aggregates).
    
    Traffic assignment happens at the centroid level, so we generate a full
    195 × 195 matrix (or similar) with inverse-distance decay.
    
    Args:
        centroid_nodes: GeoDataFrame with all Virginia centroid nodes
        road_nodes: GeoDataFrame with all road network nodes (to find nearest matches)
        total_trips: Total trips to distribute (e.g., 25,000,000)
        decay_power: Power for inverse-distance decay (1.0 = 1/d)
        min_distance_m: Minimum distance to avoid division by zero
        
    Returns:
        DataFrame with origin_node, destination_node, Car21 (trips) columns
    """
    centroid_nodes = centroid_nodes.copy().to_crs(DEFAULT_TARGET_CRS)
    
    if centroid_nodes.empty:
        raise ValueError("No Virginia centroid nodes provided")
    
    print(f"\nBuilding synthetic 25M-trip OD matrix for {len(centroid_nodes):,} centroids...")
    
    # Map each centroid to its nearest network node
    print("  Mapping centroids to network nodes...")
    centroid_to_network_node = {}
    for idx, cent_row in centroid_nodes.iterrows():
        cent_geom = cent_row.geometry
        distances = road_nodes.geometry.distance(cent_geom)
        nearest_idx = distances.idxmin()
        nearest_node_id = road_nodes.loc[nearest_idx, 'node_id']
        centroid_to_network_node[idx] = nearest_node_id
    
    # Extract coordinates for distance calculation (keep original index for mapping)
    coordinates = np.column_stack((
        centroid_nodes.geometry.x.to_numpy(),
        centroid_nodes.geometry.y.to_numpy()
    ))
    
    # Calculate pairwise distances
    delta = coordinates[:, None, :] - coordinates[None, :, :]
    distance_matrix = np.sqrt((delta**2).sum(axis=2))
    np.fill_diagonal(distance_matrix, np.inf)  # Exclude self-pairs
    
    # Build inverse-distance weights
    weights = 1.0 / np.power(np.maximum(distance_matrix, min_distance_m), decay_power)
    weights[np.isinf(weights)] = 0.0
    weights[np.isnan(weights)] = 0.0
    
    total_weight = weights.sum()
    if total_weight <= 0:
        raise ValueError("Inverse-distance weights sum to zero")
    
    # Normalize to total trips
    flows = weights * (float(total_trips) / total_weight)
    
    # Build OD rows
    rows = []
    centroid_indices = list(centroid_to_network_node.keys())
    
    for origin_idx_pos, origin_idx in enumerate(centroid_indices):
        origin_node = centroid_to_network_node[origin_idx]
        
        for dest_idx_pos, dest_idx in enumerate(centroid_indices):
            if origin_idx_pos == dest_idx_pos:
                continue  # Skip self-pairs
            
            destination_node = centroid_to_network_node[dest_idx]
            trip_flow = flows[origin_idx_pos, dest_idx_pos]
            
            if trip_flow <= 0:
                continue
            
            rows.append({
                "origin_node": origin_node,
                "destination_node": destination_node,
                "Car21": float(trip_flow),
                "distance_m": float(distance_matrix[origin_idx_pos, dest_idx_pos]),
            })
    
    od_df = pd.DataFrame(rows)
    if od_df.empty:
        raise ValueError("OD generation produced no rows")
    
    print(f"  Generated {len(od_df):,} OD pairs")
    print(f"  Total trips: {od_df['Car21'].sum():,.0f}")
    
    return od_df


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Virginia-only FAF5 → NIRD workflow")
    parser.add_argument("--gdb", default=DEFAULT_GDB_PATH, help="Path to FAF5 geodatabase")
    parser.add_argument("--state", default=DEFAULT_STATE, help="State abbreviation to clip to (default: VA)")
    parser.add_argument("--boundary", default=None, help="Optional state boundary file to clip the network")
    parser.add_argument("--total-trips", type=int, default=DEFAULT_TOTAL_TRIPS, help="Benchmark trips for synthetic OD")
    parser.add_argument("--decay-power", type=float, default=1.0, help="Inverse-distance decay power")
    parser.add_argument("--dry-run", action="store_true", help="Only report actions; do not write files")
    args = parser.parse_args()

    config = load_config()
    output_root = Path(config.get("paths", {}).get("output_path", "results"))
    if output_root.exists() and output_root.is_dir():
        va_root = output_root / "va_workflow"
    else:
        va_root = REPO_ROOT / "results_va_workflow"
        if output_root.exists() and output_root.is_file():
            print(f"Warning: configured output path {output_root} is a file; using {va_root} instead")
    va_root.mkdir(parents=True, exist_ok=True)

    gdb_path = Path(args.gdb)
    if not gdb_path.exists():
        print(f"FAF5 GDB not found: {gdb_path}")
        return 1

    links, nodes = load_gdb_layers(gdb_path)
    state_filter = normalize_state_filter(args.state)
    boundary_gdf = gpd.read_file(args.boundary) if args.boundary else None

    # Convert and clip the road network using the existing converter logic.
    # IMPORTANT: Keep class-50 centroid connectors (filter_centroids=False) because
    # they're the attachment points for the OD matrix.
    nird_links = links_conv.convert_faf5_links_to_nird(
        links,
        target_crs=DEFAULT_TARGET_CRS,
        filter_centroids=False,
        states=state_filter,
        boundary_gdf=boundary_gdf,
    )
    road_nodes = build_nodes_from_link_connectivity(nird_links, DEFAULT_TARGET_CRS)

    # Extract Virginia centroids from the FAF5 node layer.
    va_centroids = filter_va_centroids(nodes, state_name="Virginia")
    va_centroids = va_centroids.to_crs(DEFAULT_TARGET_CRS)

    centroid_path = va_root / f"faf5_centroid_nodes_{args.state.upper()}.gpq"
    road_links_path = va_root / f"faf5_road_links_{args.state.upper()}.gpq"
    road_nodes_path = va_root / f"faf5_road_nodes_{args.state.upper()}.gpq"
    od_path = va_root / f"faf5_od_matrix_{args.state.upper()}_inverse_distance_{int(args.total_trips/1_000_000)}m.pq"

    if args.dry_run:
        print(f"Dry run: would write road links to {road_links_path}")
        print(f"Dry run: would write road nodes to {road_nodes_path}")
        print(f"Dry run: would write centroid nodes to {centroid_path}")
        print(f"Dry run: would write synthetic OD to {od_path}")
        print(f"Road links after clipping: {len(nird_links):,}")
        print(f"Road nodes after clipping: {len(road_nodes):,}")
        print(f"Virginia centroids: {len(va_centroids):,}")
        return 0

    save_gdf(nird_links, road_links_path, layer="links")
    save_gdf(road_nodes, road_nodes_path, layer="nodes")
    save_gdf(va_centroids, centroid_path, layer="centroids")

    # Build a 25M-trip synthetic OD matrix with inverse-distance decay.
    # Use ALL 195 centroid nodes for assignment, not just FAF aggregates.
    od_df = build_inverse_distance_od(
        centroid_nodes=va_centroids,
        road_nodes=road_nodes,
        total_trips=args.total_trips,
        decay_power=args.decay_power,
    )
    od_df.to_parquet(od_path, index=False)
    print(f"Wrote synthetic OD matrix to {od_path}")
    print(f"OD rows: {len(od_df):,}")
    print(f"Total trips: {od_df['Car21'].sum():,.2f}")

    print("Virginia FAF5 → NIRD workflow complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
Run a lightweight VA-focused workflow to prepare inputs for scripts 1-4.

This script attempts to locate FAF5 network link files and centroid/node files
under the configured `soge_clusters` path (from `config.json`). It can filter
links by state code (default 'VA') or by a provided boundary file and writes
filtered outputs to `results/va_workflow/` for downstream scripts 1-4 to consume.

This is a safe, idempotent helper: if required input files are missing it will
print clear instructions and exit (no destructive changes).
"""
from pathlib import Path
import sys
import json
import argparse
import geopandas as gpd


def load_config(repo_root: Path):
    cfg_path = repo_root / "config.json"
    if not cfg_path.exists():
        return {}
    return json.loads(cfg_path.read_text())


def find_faf5_links(base: Path):
    # Look for common FAF5 link filenames under the soge_clusters folder
    patterns = ["**/*faf5*links*.gpkg", "**/*faf5*links*.*", "**/*faf5*links*.gpq"]
    for p in patterns:
        matches = list(base.glob(p))
        if matches:
            return matches[0]
    return None


def find_centroid_nodes(base: Path):
    patterns = ["**/*centroid_nodes*.*", "**/*centroid*nodes*.*"]
    for p in patterns:
        matches = list(base.glob(p))
        if matches:
            return matches[0]
    return None


def filter_links_by_state(links_gdf: gpd.GeoDataFrame, state_code: str):
    if "STATE" in links_gdf.columns:
        result = links_gdf[links_gdf["STATE"].astype(str).str.upper() == state_code.upper()].copy()
        return result
    else:
        print("  Warning: 'STATE' column not present on links; cannot filter by state.")
        return links_gdf.iloc[0:0].copy()


def filter_links_by_boundary(links_gdf: gpd.GeoDataFrame, boundary_gdf: gpd.GeoDataFrame):
    if links_gdf.crs != boundary_gdf.crs:
        boundary_gdf = boundary_gdf.to_crs(links_gdf.crs)
    boundary_union = boundary_gdf.unary_union
    return links_gdf[links_gdf.intersects(boundary_union)].copy()


def main():
    parser = argparse.ArgumentParser(description="Prepare VA workflow inputs (scripts 1-4)")
    parser.add_argument("--state", default="VA", help="Two-letter state code to filter (default: VA)")
    parser.add_argument("--boundary", help="Optional boundary file (GeoJSON/GPKG/SHAPE) to clip to")
    parser.add_argument("--dry-run", action="store_true", help="Only print actions; do not write outputs")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root)
    # support both top-level 'soge_clusters' and nested under 'paths'
    soge_val = cfg.get("soge_clusters") or cfg.get("paths", {}).get("soge_clusters")
    soge_root = Path(soge_val or "").expanduser()
    if not soge_root or not soge_root.exists():
        print("Could not find soge_clusters path from config.json. Please update 'soge_clusters' in config.json to point to your data folder (e.g., fairfax_soge_clusters_toy or a VA dataset).")
        return 1

    print(f"Using soge_clusters base: {soge_root}")

    faf5_links_path = find_faf5_links(soge_root)
    centroid_nodes_path = find_centroid_nodes(soge_root)

    print(f"Found FAF5 links: {faf5_links_path}")
    print(f"Found centroid nodes: {centroid_nodes_path}")

    if faf5_links_path is None:
        print("No FAF5 links file found under soge_clusters; please provide FAF5 link data (see data/README.md). Exiting.")
        return 1

    # Support nonstandard '.gpq' parquet-like files by trying read_parquet first
    try:
        if faf5_links_path.suffix.lower() in {'.gpq', '.parquet', '.pq'}:
            links = gpd.read_parquet(faf5_links_path)
        else:
            links = gpd.read_file(faf5_links_path)
    except Exception:
        # Fallback: try read_parquet then read_file to give better diagnostics
        try:
            links = gpd.read_parquet(faf5_links_path)
        except Exception as e_parq:
            print(f"Failed to read {faf5_links_path} as parquet: {e_parq}")
            links = gpd.read_file(faf5_links_path)

    print(f"Loaded {len(links)} links (CRS: {links.crs})")

    # Determine output base. Prefer configured output_path only if it exists and is a directory.
    configured_out = Path(cfg.get("paths", {}).get("output_path", "results"))
    configured_out = (repo_root / configured_out)
    if configured_out.exists() and configured_out.is_dir():
        out_dir = configured_out / "va_workflow"
    else:
        alt_base = repo_root / "results_va_workflow"
        out_dir = alt_base / "va_workflow"
        if configured_out.exists() and configured_out.is_file():
            print(f"Warning: configured output path '{configured_out}' exists but is not a directory. Using '{alt_base}' instead.")
    out_dir.mkdir(parents=True, exist_ok=True)

    filtered = links.iloc[0:0].copy()
    if args.boundary:
        bpath = Path(args.boundary)
        if not bpath.exists():
            print(f"Boundary file {bpath} not found. Exiting.")
            return 1
        boundary = gpd.read_file(bpath)
        print(f"Loaded boundary with {len(boundary)} polygon(s) (CRS: {boundary.crs})")
        filtered = filter_links_by_boundary(links, boundary)
    else:
        filtered = filter_links_by_state(links, args.state)

    print(f"Filtered links count: {len(filtered)}")

    if args.dry_run:
        print("Dry run requested; no outputs written.")
        return 0

    out_links_file = out_dir / "faf5_road_links_VA.gpkg"
    if len(filtered):
        filtered.to_file(out_links_file, driver="GPKG", layer="links")
        print(f"Wrote filtered links to {out_links_file}")
    else:
        print("No links after filtering; no link file written.")

    if centroid_nodes_path and centroid_nodes_path.exists():
        centroids = gpd.read_file(centroid_nodes_path)
        if args.boundary:
            centroids = centroids[centroids.intersects(boundary.unary_union)].copy()
        else:
            if "STATE" in centroids.columns:
                centroids = centroids[centroids["STATE"].astype(str).str.upper() == args.state.upper()].copy()
            else:
                print("Centroid nodes do not have a 'STATE' column; writing whole centroid file for manual inspection.")
        out_centroids_file = out_dir / "faf5_centroid_nodes_VA.gpkg"
        centroids.to_file(out_centroids_file, driver="GPKG", layer="centroids")
        print(f"Wrote centroid nodes subset to {out_centroids_file}")
    else:
        print("No centroid nodes file found; centroid/OD creation skipped.")

    print("VA workflow preparation complete. Next: run scripts 1-4 using outputs in results/va_workflow/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
