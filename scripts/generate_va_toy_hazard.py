"""Generate Virginia toy hazard rasters for Script 2.

This script rasterizes the Virginia state boundary and writes the toy hazard
GeoTIFFs that Script 2 expects in toy mode:

- va_hazard_class50_141node.tif
- va_hazard_class50_141node_base.tif
- va_hazard_class50_141node_low.tif
- va_hazard_class50_141node_high.tif

The output is Virginia-wide (141 centroids) rather than DMV-wide (17 nodes).
Depth values are synthetic and spatially smooth so the toy pipeline has a
stable, repeatable input. Original fairfax_hazard_class50_17node_* files are
preserved and unmodified.
"""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyproj
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.windows import Window


TARGET_CRS = "EPSG:2163"
DEFAULT_RESOLUTION_M = 1000.0
DEFAULT_BASE_DEPTH_MAX = 1.0
DEFAULT_BASE_DEPTH_MIN = 0.05
DEFAULT_LOW_SCALE = 0.7
DEFAULT_HIGH_SCALE = 1.5


def configure_proj_runtime() -> Path | None:
    candidate_dirs = []
    candidate_dirs.append(Path(rasterio.__file__).resolve().parent / "proj_data")
    try:
        proj_data_dir = pyproj.datadir.get_data_dir()
        if proj_data_dir:
            candidate_dirs.append(Path(proj_data_dir))
    except Exception:
        pass

    for key in ("PROJ_DATA", "PROJ_LIB"):
        val = os.environ.get(key)
        if val:
            candidate_dirs.append(Path(val))

    for cdir in candidate_dirs:
        try:
            if cdir.exists() and (cdir / "proj.db").exists():
                os.environ["PROJ_DATA"] = str(cdir)
                os.environ["PROJ_LIB"] = str(cdir)
                try:
                    pyproj.datadir.set_data_dir(str(cdir))
                except Exception:
                    pass
                return cdir
        except Exception:
            continue

    return None


configure_proj_runtime()


def find_shapefile(folder: Path) -> Path:
    if folder.is_file() and folder.suffix.lower() == ".shp":
        return folder
    if not folder.exists():
        raise FileNotFoundError(f"Boundary folder not found: {folder}")

    shapefiles = sorted(folder.glob("*.shp"))
    if not shapefiles:
        raise FileNotFoundError(f"No .shp file found in: {folder}")
    return shapefiles[0]


def load_virginia_boundary(state_path: Path) -> gpd.GeoDataFrame:
    shp_path = find_shapefile(state_path)
    states = gpd.read_file(shp_path)

    if "STATEFP" in states.columns:
        va = states[states["STATEFP"].astype(str).str.zfill(2) == "51"].copy()
    elif "STUSPS" in states.columns:
        va = states[states["STUSPS"].astype(str).str.upper() == "VA"].copy()
    elif "NAME" in states.columns:
        va = states[states["NAME"].astype(str).str.lower() == "virginia"].copy()
    else:
        raise ValueError("Could not identify Virginia polygon from the state shapefile")

    if va.empty:
        raise ValueError("Virginia polygon not found in the supplied boundary file")

    if va.crs is None:
        raise ValueError("The Virginia boundary shapefile has no CRS")

    return va.to_crs(TARGET_CRS)


def build_raster_spec(boundary: gpd.GeoDataFrame, resolution_m: float) -> tuple[float, float, float, float, int, int, rasterio.Affine]:
    minx, miny, maxx, maxy = boundary.total_bounds

    # Pad slightly so the raster extends beyond the state edge.
    pad = resolution_m * 10
    minx -= pad
    miny -= pad
    maxx += pad
    maxy += pad

    width = int(np.ceil((maxx - minx) / resolution_m))
    height = int(np.ceil((maxy - miny) / resolution_m))
    transform = from_origin(minx, maxy, resolution_m, resolution_m)
    return minx, miny, maxx, maxy, width, height, transform


def build_depth_block(
    boundary: gpd.GeoDataFrame,
    resolution_m: float,
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    width: int,
    row_start: int,
    row_stop: int,
) -> tuple[int, np.ndarray]:
    block_height = row_stop - row_start
    block_transform = from_origin(minx, maxy - row_start * resolution_m, resolution_m, resolution_m)

    mask = rasterize(
        ((geom, 1) for geom in boundary.geometry),
        out_shape=(block_height, width),
        transform=block_transform,
        fill=0,
        default_value=1,
        dtype="uint8",
        all_touched=False,
    )

    cols = np.arange(width, dtype="float32")
    rows = np.arange(row_start, row_stop, dtype="float32")
    x_vals = minx + (cols + 0.5) * resolution_m
    y_vals = maxy - (rows + 0.5) * resolution_m

    x_norm = (x_vals - minx) / (maxx - minx)
    y_norm = (y_vals - miny) / (maxy - miny)

    # Smooth deterministic synthetic depth field. Values range from 0.05 to 1.0.
    base = DEFAULT_BASE_DEPTH_MIN + (DEFAULT_BASE_DEPTH_MAX - DEFAULT_BASE_DEPTH_MIN) * (
        0.65 * x_norm[None, :] + 0.35 * y_norm[:, None]
    )
    base = np.clip(base, DEFAULT_BASE_DEPTH_MIN, DEFAULT_BASE_DEPTH_MAX).astype("float32")
    base[mask == 0] = 0.0

    return row_start, base


def write_tif(
    path: Path,
    boundary: gpd.GeoDataFrame,
    resolution_m: float,
    scale: float,
    threads: int,
    block_rows: int,
    crs: str = TARGET_CRS,
) -> None:
    minx, miny, maxx, maxy, width, height, transform = build_raster_spec(boundary, resolution_m)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=0.0,
        compress="deflate",
        predictor=2,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dataset:
        row_starts = list(range(0, height, block_rows))

        def compute_block(row_start: int) -> tuple[int, np.ndarray]:
            row_stop = min(row_start + block_rows, height)
            block_row, block = build_depth_block(
                boundary=boundary,
                resolution_m=resolution_m,
                minx=minx,
                miny=miny,
                maxx=maxx,
                maxy=maxy,
                width=width,
                row_start=row_start,
                row_stop=row_stop,
            )
            return block_row, np.clip(block * scale, 0.0, None)

        if threads > 1:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                for row_start, block in executor.map(compute_block, row_starts):
                    dataset.write(block.astype("float32"), 1, window=Window(0, row_start, width, block.shape[0]))
        else:
            for row_start in row_starts:
                _, block = compute_block(row_start)
                dataset.write(block.astype("float32"), 1, window=Window(0, row_start, width, block.shape[0]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Virginia toy hazard rasters")
    parser.add_argument(
        "--state-folder",
        default=r"C:\Users\alimu\OneDrive - George Mason University - O365 Production\Research\NetworkModeling\state_va",
        help="Folder containing the Virginia state shapefile",
    )
    parser.add_argument(
        "--output-dir",
        default=r"C:\Users\alimu\NIRD_Data\va_soge_clusters_toy\inputs\test_141node",
        help="Directory where the toy hazard GeoTIFFs will be written",
    )
    parser.add_argument(
        "--resolution-m",
        type=float,
        default=DEFAULT_RESOLUTION_M,
        help="Raster cell size in metres",
    )
    parser.add_argument(
        "--variants",
        choices=("all", "base"),
        default="all",
        help="Which hazard variants to write",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, min(os.cpu_count() or 1, 8)),
        help="Number of worker threads to use for raster chunk generation",
    )
    parser.add_argument(
        "--block-rows",
        type=int,
        default=256,
        help="Number of raster rows to generate per chunk",
    )
    args = parser.parse_args()

    boundary = load_virginia_boundary(Path(args.state_folder))

    variants = {
        "va_hazard_class50_141node.tif": 1.0,
        "va_hazard_class50_141node_base.tif": 1.0,
        "va_hazard_class50_141node_low.tif": DEFAULT_LOW_SCALE,
        "va_hazard_class50_141node_high.tif": DEFAULT_HIGH_SCALE,
    }
    if args.variants == "base":
        variants = {"va_hazard_class50_141node_base.tif": 1.0}

    output_dir = Path(args.output_dir)
    for filename, scale in variants.items():
        out_path = output_dir / filename
        print(f"Generating {out_path} with {args.threads} thread(s) at {args.resolution_m:.0f} m resolution...", flush=True)
        write_tif(
            out_path,
            boundary,
            args.resolution_m,
            scale,
            threads=args.threads,
            block_rows=args.block_rows,
        )
        print(f"Wrote {out_path}")

    print(
        f"Virginia toy hazards created at {output_dir} "
        f"(resolution={args.resolution_m:.0f}m, CRS={TARGET_CRS})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())