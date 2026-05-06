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
    soge_root = Path(cfg.get("soge_clusters", "")).expanduser()
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

    links = gpd.read_file(faf5_links_path)
    print(f"Loaded {len(links)} links (CRS: {links.crs})")

    out_dir = repo_root / "results" / "va_workflow"
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
