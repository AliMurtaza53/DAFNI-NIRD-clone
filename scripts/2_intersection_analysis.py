"""Script 2: intersection analysis for road links and flood rasters.

`depth_key` controls how flood depth is translated into disruption:

- depths below `depth_key` keep a positive speed, reduced by a quadratic penalty
- depths at or above `depth_key` reduce speed to zero

Example:
        - `depth_key=15` means a 10 cm flood still leaves some speed, but a 20 cm
            flood closes the link entirely.

`event_key` selects the hazard scenario variant (1=base, 2=low, 3=high).
Use `all` or a comma-separated list such as `2,3` to process multiple toy
events in one process. That allows the in-memory split cache to be reused when
the rasters share the same grid.
"""

import sys
import os
import time
from typing import Dict, Optional
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import geopandas as gpd
import numpy as np
import pandas as pd
from collections import defaultdict
import rasterio
from shapely.geometry import box

from snail import intersection
from nird.utils import get_results_variant, load_config
import warnings
import logging
import pyproj

warnings.filterwarnings("ignore")

base_path = Path(load_config()["paths"]["soge_clusters"])
raster_path = base_path / "hazards" / "completed"
TARGET_CRS = "EPSG:2163"  # US National Atlas Equal Area (use for USA networks)

# Optional performance controls (disabled by default)
SPLIT_SIMPLIFY_TOLERANCE_M = float(os.environ.get("NIRD_SPLIT_SIMPLIFY_TOLERANCE_M", "0"))
ENABLE_SPLIT_CACHE = os.environ.get("NIRD_ENABLE_SPLIT_CACHE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
}
_SPLIT_CACHE = {}


def configure_proj_runtime() -> Optional[Path]:
    """Ensure PROJ can find proj.db for CRS transforms (Rasterio/GDAL/PROJ)."""
    candidate_dirs = []

    # Prefer environment-local data first (avoid stale external PROJ_LIB overrides)
    candidate_dirs.append(Path(rasterio.__file__).resolve().parent / "proj_data")

    try:
        proj_data_dir = pyproj.datadir.get_data_dir()
        if proj_data_dir:
            candidate_dirs.append(Path(proj_data_dir))
    except Exception:
        pass

    # Consider explicit env vars after local defaults
    for key in ("PROJ_DATA", "PROJ_LIB"):
        val = os.environ.get(key)
        if val:
            candidate_dirs.append(Path(val))

    for cdir in candidate_dirs:
        try:
            if cdir.exists() and (cdir / "proj.db").exists():
                # Set both for compatibility across PROJ versions / GDAL builds
                os.environ["PROJ_DATA"] = str(cdir)
                os.environ["PROJ_LIB"] = str(cdir)
                try:
                    pyproj.datadir.set_data_dir(str(cdir))
                except Exception:
                    pass
                logging.info(f"Using PROJ data directory: {cdir}")
                return cdir
        except Exception:
            continue

    logging.warning(
        "Could not locate proj.db. Set PROJ_DATA (or PROJ_LIB) to a directory containing proj.db."
    )
    return None


configure_proj_runtime()


def first_existing(paths):
    """Return first existing path from a sequence, else None."""
    for path in paths:
        p = Path(path)
        if p.exists():
            return p
    return None


def validate_output(path: Path, gdf: gpd.GeoDataFrame, label: str) -> None:
    """Basic validation for outputs (non-empty + file exists)."""
    if gdf is None or gdf.empty:
        logging.warning(f"{label} is empty. Output not written: {path}")
        return
    if path.exists():
        size = os.path.getsize(path)
        if size == 0:
            logging.warning(f"{label} file is empty: {path}")
        else:
            logging.info(f"{label} saved: {path} (rows={len(gdf)}, bytes={size})")
    else:
        logging.warning(f"{label} file missing after save: {path}")


def log_summary(label: str, gdf: gpd.GeoDataFrame) -> None:
    """Log quick summary stats for outputs."""
    if gdf is None or gdf.empty:
        return

    # Flood depth summary
    if "flood_depth_max" in gdf.columns:
        depth = gdf["flood_depth_max"].astype(float)
        logging.info(
            f"{label} flood_depth_max: min={depth.min():.4f}, max={depth.max():.4f}, mean={depth.mean():.4f}"
        )

    # Damage level summary
    if "damage_level_max" in gdf.columns:
        counts = gdf["damage_level_max"].value_counts(dropna=False)
        logging.info(f"{label} damage_level_max counts: {counts.to_dict()}")


def _is_us_national_atlas_alias(crs) -> bool:
    """Return True for LOCAL_CS aliases of EPSG:2163 used by toy rasters."""
    if crs is None:
        return False
    crs_text = str(crs)
    return "US National Atlas Equal Area" in crs_text or "2163" in crs_text


def subset_features_to_raster_extent(
    features: gpd.GeoDataFrame,
    flood_path: str,
    padding_pixels: int = 2,
) -> gpd.GeoDataFrame:
    """Spatially prefilter features to the hazard raster footprint.

    This avoids sending an entire national network into snail's split/intersection
    routine when the hazard raster covers only a small test area.
    """
    if features.empty:
        return features

    with rasterio.Env(
        PROJ_DATA=os.environ.get("PROJ_DATA"),
        PROJ_LIB=os.environ.get("PROJ_LIB"),
        GTIFF_SRS_SOURCE="EPSG",
    ):
        with rasterio.open(flood_path) as dataset:
            bounds = dataset.bounds
            raster_crs = dataset.crs
            pad_x = abs(dataset.transform.a) * padding_pixels
            pad_y = abs(dataset.transform.e) * padding_pixels

    extent_geom = box(
        bounds.left - pad_x,
        bounds.bottom - pad_y,
        bounds.right + pad_x,
        bounds.top + pad_y,
    )

    if raster_crs is None:
        logging.warning(
            "Raster has no CRS; skipping raster-extent feature prefilter for %s",
            flood_path,
        )
        return features

    extent = gpd.GeoDataFrame({"source": [Path(flood_path).name]}, geometry=[extent_geom], crs=raster_crs)
    if features.crs is None:
        logging.warning(
            "Road links have no CRS; skipping raster-extent feature prefilter for %s",
            flood_path,
        )
        return features

    if extent.crs != features.crs:
        try:
            extent = extent.to_crs(features.crs)
        except Exception as exc:
            if _is_us_national_atlas_alias(raster_crs) and _is_us_national_atlas_alias(features.crs):
                logging.warning(
                    "Raster CRS is a US National Atlas alias; applying raster bounds in feature CRS "
                    "without reprojection."
                )
                extent = gpd.GeoDataFrame(
                    {"source": [Path(flood_path).name]},
                    geometry=[extent_geom],
                    crs=features.crs,
                )
            else:
                raise RuntimeError(
                    "Could not transform raster extent to road-link CRS for prefiltering. "
                    f"Raster={flood_path}; details: {exc}"
                ) from exc

    before = len(features)
    extent_polygon = extent.geometry.iloc[0]
    try:
        candidate_idx = features.sindex.query(extent_polygon, predicate="intersects")
        filtered = features.iloc[np.unique(candidate_idx)].copy()
    except Exception:
        filtered = features[features.intersects(extent_polygon)].copy()

    logging.info(
        "Raster extent prefilter for %s: %s -> %s road links",
        Path(flood_path).name,
        before,
        len(filtered),
    )
    if filtered.empty:
        logging.warning(
            "Raster extent prefilter found no road links for %s; downstream output may be empty.",
            flood_path,
        )
    return filtered


def load_analysis_boundary(base_path: Path) -> gpd.GeoDataFrame:
    """Load study-area boundary (preferred) or fallback to a broad USA polygon."""
    study_area_path = first_existing(
        [
            base_path / "study_area" / "fairfax_study_area.gpkg",
            base_path / "study_area" / "fairfax_study_area.geojson",
            base_path / "inputs" / "study_area" / "fairfax_study_area.gpkg",
            base_path / "inputs" / "study_area" / "fairfax_study_area.geojson",
        ]
    )
    if study_area_path is not None:
        return gpd.read_file(study_area_path)

    from shapely.geometry import box

    continental = box(-125, 24, -66, 50)
    alaska = box(-170, 50, -130, 72)
    hawaii = box(-160, 18, -154, 23)
    usa_geom = continental.union(alaska).union(hawaii)
    return gpd.GeoDataFrame({"name": ["USA"]}, geometry=[usa_geom], crs="EPSG:4326")


def intersect_features_with_raster(
    raster_path: str,
    raster_key: str,
    features: gpd.GeoDataFrame,
    flood_type: str,
) -> gpd.GeoDataFrame:
    """
    Intersects vector features with a raster dataset to compute flood depth for each
        feature.

    Parameters:
        raster_path (str): Path to the raster file containing flood data.
        raster_key (str): Identifier for the raster dataset.
        features (gpd.GeoDataFrame): GeoDataFrame containing vector features (e.g.,
            road links).
        flood_type (str): Type of flood (e.g., "surface" or "river").

    Returns:
        gpd.GeoDataFrame: GeoDataFrame of intersected features with flood depth values,
                          reprojected to TARGET_CRS.
    """

    logging.info(f"Intersecting features with raster {raster_key}...")

    # Keep only columns needed downstream to reduce split/copy overhead substantially
    required_cols = ["e_id", "road_classification", "trunk_road", "road_label", "geometry"]
    present_cols = [c for c in required_cols if c in features.columns]
    features_min = features[present_cols].copy()

    # Ensure expected optional columns exist for damage logic
    if "trunk_road" not in features_min.columns:
        features_min["trunk_road"] = None
    if "road_label" not in features_min.columns:
        features_min["road_label"] = None

    # Avoid pandas extension/Arrow string dtypes that can interact badly with
    # snail's row-wise splitting on large datasets.
    for col in [c for c in features_min.columns if c != "geometry"]:
        if str(features_min[col].dtype).startswith("string"):
            features_min[col] = features_min[col].astype(object)

    # run the intersection analysis using a windowed raster read
    prepared = intersection.prepare_linestrings(features_min)

    with rasterio.Env(
        PROJ_DATA=os.environ.get("PROJ_DATA"),
        PROJ_LIB=os.environ.get("PROJ_LIB"),
        GTIFF_SRS_SOURCE="EPSG",
    ):
        dataset = rasterio.open(raster_path)

    with dataset:
        grid_full = intersection.GridDefinition.from_rasterio_dataset(dataset)
        grid_crs = grid_full.crs
        if prepared.crs != grid_full.crs:
            logging.info("Projecting Feature (clipped) CRS to Grid CRS...")
            try:
                prepared = prepared.to_crs(grid_full.crs)
            except Exception as e:
                # Some toy rasters use LOCAL_CS naming for US National Atlas Equal Area.
                # If that happens, keep features in their CRS and align grid CRS to match.
                grid_crs_text = "" if grid_full.crs is None else str(grid_full.crs)
                if (
                    prepared.crs is not None
                    and "US National Atlas Equal Area" in grid_crs_text
                    and str(prepared.crs).find("2163") != -1
                ):
                    logging.warning(
                        "Raster CRS is LOCAL_CS alias of US National Atlas Equal Area; "
                        "using feature CRS for grid alignment without reprojection."
                    )
                    grid_crs = prepared.crs
                else:
                    raise RuntimeError(
                        "CRS transform to raster grid failed. "
                        "Aborting to avoid invalid mixed-CRS intersections. "
                        "Fix PROJ/CRS configuration first. "
                        f"Details: {e}"
                    )

        if prepared.empty:
            return prepared

        # Compute a raster window from feature bounds to avoid loading global raster
        minx, miny, maxx, maxy = prepared.total_bounds
        pad_x = abs(dataset.transform.a) * 2
        pad_y = abs(dataset.transform.e) * 2
        minx, miny, maxx, maxy = (
            minx - pad_x,
            miny - pad_y,
            maxx + pad_x,
            maxy + pad_y,
        )

        window = rasterio.windows.from_bounds(
            minx, miny, maxx, maxy, transform=dataset.transform
        )
        window = window.round_offsets().round_lengths()
        full_window = rasterio.windows.Window(0, 0, dataset.width, dataset.height)
        window = window.intersection(full_window)

        raster = dataset.read(1, window=window)
        window_transform = dataset.window_transform(window)
        grid = intersection.GridDefinition(
            crs=grid_crs,
            width=int(window.width),
            height=int(window.height),
            transform=tuple(window_transform)[:6],
        )

    if SPLIT_SIMPLIFY_TOLERANCE_M > 0:
        prepared = prepared.copy()
        prepared["geometry"] = prepared.geometry.simplify(
            SPLIT_SIMPLIFY_TOLERANCE_M,
            preserve_topology=True,
        )

    cache_key = None
    intersections = None
    if ENABLE_SPLIT_CACHE and "e_id" in prepared.columns:
        try:
            eids = prepared["e_id"].astype(str).tolist()
            cache_key = (
                tuple(sorted(eids)),
                grid.crs,
                grid.width,
                grid.height,
                tuple(grid.transform),
                round(float(SPLIT_SIMPLIFY_TOLERANCE_M), 6),
            )
            cached = _SPLIT_CACHE.get(cache_key)
            if cached is not None:
                intersections = cached.copy()
        except Exception:
            cache_key = None

    if intersections is None:
        intersections = intersection.split_linestrings(prepared, grid)
        intersections = intersection.apply_indices(intersections, grid)
        if cache_key is not None:
            _SPLIT_CACHE[cache_key] = intersections.copy()

    intersections[f"flood_depth_{flood_type}"] = (
        intersection.get_raster_values_for_splits(intersections, raster)
    )

    # reproject back
    try:
        intersections = intersections.to_crs(TARGET_CRS)
    except Exception as e:
        raise RuntimeError(
            f"Failed to reproject intersections to {TARGET_CRS}. "
            "Aborting to avoid CRS ambiguity in downstream damage calculations. "
            f"Details: {e}"
        )
    intersections["length"] = intersections.geometry.length

    return intersections


def clip_features(
    features: gpd.GeoDataFrame,
    clip_path: Optional[str],
    raster_key: str,
    boundary_gdf: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """
    Clips spatial features to the extent of a specified vector layer.

    Parameters:
        features (gpd.GeoDataFrame): GeoDataFrame containing the spatial features to be
            clipped.
        clip_path (str): Path to the vector file used for clipping.
        raster_key (str): Identifier for the raster dataset.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame of features clipped to the extent of the clip
            layer.
    """

    logging.info(f"Clipping features based on {raster_key}...")
    skip_vector_clip = False
    clips = None
    if clip_path is None:
        skip_vector_clip = True
        logging.warning(
            "No clip vector provided; proceeding with boundary-only clipping."
        )
    else:
        clips = gpd.read_file(clip_path, engine="pyogrio")  # grid's extent (vector)
        clips = clips.reset_index(drop=True)  # Ensure no 'index_right' column conflicts

    # Temporary QA guard: some Aqueduct vector masks are global extent polygons
    # ([-180, -90, 180, 90] in EPSG:4326). Reprojecting this footprint to EPSG:2163
    # can collapse around the antimeridian and unintentionally clip out most links.
    if clips is not None and clips.crs is not None and str(clips.crs).upper().endswith("4326"):
        minx, miny, maxx, maxy = clips.total_bounds
        if (
            abs(minx + 180) < 1e-6
            and abs(miny + 90) < 1e-6
            and abs(maxx - 180) < 1e-6
            and abs(maxy - 90) < 1e-6
        ):
            skip_vector_clip = True
            logging.warning(
                "Global vector extent detected; skipping vector clipping for QA run."
            )
    
    # Store original columns to preserve
    original_columns = features.columns.tolist()
    
    # Reproject the clip shapefile only when it will be used for spatial clipping
    if (not skip_vector_clip) and clips is not None and clips.crs != features.crs:
        logging.info("Projecting Shapefile CRS to match Feature CRS...")
        clips = clips.to_crs(features.crs)

    if boundary_gdf is not None:
        if boundary_gdf.crs != features.crs:
            boundary_gdf = boundary_gdf.to_crs(features.crs)
        boundary_gdf = boundary_gdf.reset_index(drop=True)
        features = gpd.sjoin(features, boundary_gdf, how="inner", predicate="intersects")
        # Keep only original columns from features
        features = features[[col for col in original_columns if col in features.columns]]

    if skip_vector_clip:
        clipped_features = features.copy()
    else:
        clipped_features = gpd.sjoin(features, clips, how="inner", predicate="intersects")
    # Keep only original columns from features
    clipped_features = clipped_features[[col for col in original_columns if col in clipped_features.columns]]
    clipped_features.reset_index(drop=True, inplace=True)
    return clipped_features


def compute_maximum_speed_on_flooded_roads(
    depth: float,
    free_flow_speed: float,
    threshold=30,
) -> float:
    """
    Calculates the maximum allowable speed on flooded roads based on flood depth.

    Parameters:
        depth (float): Flood depth in meters.
        free_flow_speed (float): Free-flow speed under normal conditions (mph).
        threshold (float, optional): Depth threshold in centimeters for road closure
            (default is 30 cm).

    Returns:
        float: Maximum speed on the flooded road in miles per hour (mph).
    """

    depth = depth * 100  # m to cm
    if depth < threshold:  # cm
        value = free_flow_speed * (depth / threshold - 1) ** 2  # mph
        return value  # mph
    else:
        return 0.0  # mph


def compute_damage_level_on_flooded_roads(
    fldType: str,
    road_classification: str,
    trunk_road: str,
    road_label: str,
    fldDepth: float,
) -> str:
    """
    Determines the damage level of roads based on flood type, road classification,
        and flood depth.

    Parameters:
        fldType (str): Type of flood ("surface" or "river").
        road_classification (str): Classification of road (e.g., "Motorway", "A Road").
        trunk_road (bool): Indicates if the road is a trunk road (True/False).
        road_label (str): Label of the road (e.g., "road", "tunnel", "bridge").
        fldDepth (float): Flood depth in meters.

    Returns:
        str: Damage level categorized as "no", "minor", "moderate", "extensive",
            or "severe"
    """

    if fldType == "flood":
        fldType = "river"
    depth = fldDepth * 100  # convert from m to cm
    rc = ("" if road_classification is None else str(road_classification)).strip()
    rc_lower = rc.lower()
    trunk_flag = bool(trunk_road) if trunk_road is not None else False
    road_label = "" if road_label is None else road_label

    # FAF/US classifications
    if rc_lower in {"motorway", "motorway_link", "trunk", "primary", "secondary", "tertiary", "service", "unclassified"}:
        major = rc_lower in {"motorway", "motorway_link", "trunk", "primary", "secondary"}
        if fldType == "surface":
            if major:
                if depth < 50:
                    return "no"
                elif 50 <= depth < 200:
                    return "no"
                elif 200 <= depth < 600:
                    return "minor"
                elif depth >= 600:
                    return "moderate"
            else:
                if depth < 50:
                    return "no"
                elif 50 <= depth < 200:
                    return "minor"
                elif 200 <= depth < 600:
                    return "minor"
                elif depth >= 600:
                    return "moderate"
        elif fldType == "river":
            if major:
                if depth < 50:
                    return "no"
                elif 50 <= depth < 100:
                    return "minor"
                elif 100 <= depth < 200:
                    return "moderate"
                elif 200 <= depth < 600:
                    return "extensive"
                elif depth >= 600:
                    return "severe"
            else:
                if depth <= 0:
                    return "no"
                elif 0 < depth < 50:
                    return "minor"
                elif 50 <= depth < 200:
                    return "moderate"
                elif 200 <= depth < 600:
                    return "extensive"
                elif depth >= 600:
                    return "severe"

        return np.nan

    # UK classifications (legacy)
    if fldType == "surface":
        if road_label == "tunnel" and (
            road_classification == "Motorway"
            or (road_classification == "A Road" and trunk_flag)
        ):
            if depth < 50:
                return "no"
            elif 50 <= depth < 100:
                return "minor"
            elif 100 <= depth < 200:
                return "moderate"
            elif 200 <= depth < 600:
                return "extensive"
            elif depth >= 600:
                return "severe"
            else:
                return np.nan
        elif road_label != "tunnel" and (
            road_classification == "Motorway"
            or (road_classification == "A Road" and trunk_flag)
        ):
            if depth < 50:
                return "no"
            elif 50 <= depth < 100:
                return "no"
            elif 100 <= depth < 200:
                return "no"
            elif 200 <= depth < 600:
                return "minor"
            elif depth >= 600:
                return "moderate"
            else:
                return np.nan
        else:
            if depth < 50:
                return "no"
            elif 50 <= depth < 100:
                return "no"
            elif 100 <= depth < 200:
                return "minor"
            elif 200 <= depth < 600:
                return "minor"
            elif depth >= 600:
                return "moderate"
            else:
                return np.nan

    elif fldType == "river":
        if road_label == "tunnel" and (
            road_classification == "Motorway"
            or (road_classification == "A Road" and trunk_flag)
        ):
            if depth < 50:
                return "no"
            elif 50 <= depth < 100:
                return "minor"
            elif 100 <= depth < 200:
                return "minor"
            elif 200 <= depth < 600:
                return "moderate"
            elif depth >= 600:
                return "extensive"
            else:
                return np.nan
        elif road_label != "tunnel" and (
            road_classification == "Motorway"
            or (road_classification == "A Road" and trunk_flag)
        ):
            if depth < 50:
                return "no"
            elif 50 <= depth < 100:
                return "minor"
            elif 100 <= depth < 200:
                return "moderate"
            elif 200 <= depth < 600:
                return "extensive"
            elif depth >= 600:
                return "severe"
            else:
                return np.nan
        else:
            if depth <= 0:
                return "no"
            elif 0 < depth < 50:
                return "minor"
            elif 50 <= depth < 100:
                return "moderate"
            elif 100 <= depth < 200:
                return "moderate"
            elif 200 <= depth < 600:
                return "extensive"
            elif depth >= 600:
                return "severe"
            else:
                return np.nan
    else:
        logging.info("Please enter the type of flood!")


def compute_damage_levels_on_flooded_roads_vectorized(
    fldType: str,
    road_classification: pd.Series,
    trunk_road: pd.Series,
    road_label: pd.Series,
    fldDepth: pd.Series,
) -> pd.Series:
    """Vectorized equivalent of compute_damage_level_on_flooded_roads()."""

    if fldType == "flood":
        fldType = "river"
    depth_cm = pd.to_numeric(fldDepth, errors="coerce") * 100.0
    rc_raw = road_classification.fillna("").astype(str).str.strip()
    rc_lower = rc_raw.str.lower()
    trunk_flag = (
        pd.Series(trunk_road, index=rc_raw.index)
        .fillna(False)
        .astype(str)
        .str.lower()
        .isin({"true", "1", "yes"})
    )
    road_label = pd.Series(road_label, index=rc_raw.index).fillna("").astype(str)

    faf_us_classes = {
        "motorway",
        "motorway_link",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "service",
        "unclassified",
    }
    major_faf = rc_lower.isin({"motorway", "motorway_link", "trunk", "primary", "secondary"})
    faf_mask = rc_lower.isin(faf_us_classes)
    uk_major = rc_raw.eq("Motorway") | (rc_raw.eq("A Road") & trunk_flag)
    tunnel_mask = road_label.eq("tunnel")

    result = pd.Series(np.nan, index=rc_raw.index, dtype=object)

    if fldType == "surface":
        # FAF/US classifications
        faf_major_mask = faf_mask & major_faf
        faf_minor_mask = faf_mask & ~major_faf
        result.loc[faf_major_mask & (depth_cm < 200)] = "no"
        result.loc[faf_major_mask & (depth_cm >= 200) & (depth_cm < 600)] = "minor"
        result.loc[faf_major_mask & (depth_cm >= 600)] = "moderate"

        result.loc[faf_minor_mask & (depth_cm < 50)] = "no"
        result.loc[faf_minor_mask & (depth_cm >= 50) & (depth_cm < 600)] = "minor"
        result.loc[faf_minor_mask & (depth_cm >= 600)] = "moderate"

        # UK legacy classifications
        uk_tunnel = ~faf_mask & uk_major & tunnel_mask
        uk_major_notunnel = ~faf_mask & uk_major & ~tunnel_mask
        uk_other = ~faf_mask & ~uk_major

        result.loc[uk_tunnel & (depth_cm < 50)] = "no"
        result.loc[uk_tunnel & (depth_cm >= 50) & (depth_cm < 100)] = "minor"
        result.loc[uk_tunnel & (depth_cm >= 100) & (depth_cm < 200)] = "moderate"
        result.loc[uk_tunnel & (depth_cm >= 200) & (depth_cm < 600)] = "extensive"
        result.loc[uk_tunnel & (depth_cm >= 600)] = "severe"

        result.loc[uk_major_notunnel & (depth_cm < 50)] = "no"
        result.loc[uk_major_notunnel & (depth_cm >= 50) & (depth_cm < 100)] = "no"
        result.loc[uk_major_notunnel & (depth_cm >= 100) & (depth_cm < 200)] = "no"
        result.loc[uk_major_notunnel & (depth_cm >= 200) & (depth_cm < 600)] = "minor"
        result.loc[uk_major_notunnel & (depth_cm >= 600)] = "moderate"

        result.loc[uk_other & (depth_cm < 50)] = "no"
        result.loc[uk_other & (depth_cm >= 50) & (depth_cm < 100)] = "no"
        result.loc[uk_other & (depth_cm >= 100) & (depth_cm < 200)] = "minor"
        result.loc[uk_other & (depth_cm >= 200) & (depth_cm < 600)] = "minor"
        result.loc[uk_other & (depth_cm >= 600)] = "moderate"

    elif fldType == "river":
        faf_major_mask = faf_mask & major_faf
        faf_minor_mask = faf_mask & ~major_faf

        result.loc[faf_major_mask & (depth_cm < 50)] = "no"
        result.loc[faf_major_mask & (depth_cm >= 50) & (depth_cm < 100)] = "minor"
        result.loc[faf_major_mask & (depth_cm >= 100) & (depth_cm < 200)] = "moderate"
        result.loc[faf_major_mask & (depth_cm >= 200) & (depth_cm < 600)] = "extensive"
        result.loc[faf_major_mask & (depth_cm >= 600)] = "severe"

        result.loc[faf_minor_mask & (depth_cm <= 0)] = "no"
        result.loc[faf_minor_mask & (depth_cm > 0) & (depth_cm < 50)] = "minor"
        result.loc[faf_minor_mask & (depth_cm >= 50) & (depth_cm < 200)] = "moderate"
        result.loc[faf_minor_mask & (depth_cm >= 200) & (depth_cm < 600)] = "extensive"
        result.loc[faf_minor_mask & (depth_cm >= 600)] = "severe"

        uk_tunnel = ~faf_mask & uk_major & tunnel_mask
        uk_major_notunnel = ~faf_mask & uk_major & ~tunnel_mask
        uk_other = ~faf_mask & ~uk_major

        result.loc[uk_tunnel & (depth_cm < 50)] = "no"
        result.loc[uk_tunnel & (depth_cm >= 50) & (depth_cm < 100)] = "minor"
        result.loc[uk_tunnel & (depth_cm >= 100) & (depth_cm < 200)] = "minor"
        result.loc[uk_tunnel & (depth_cm >= 200) & (depth_cm < 600)] = "moderate"
        result.loc[uk_tunnel & (depth_cm >= 600)] = "extensive"

        result.loc[uk_major_notunnel & (depth_cm < 50)] = "no"
        result.loc[uk_major_notunnel & (depth_cm >= 50) & (depth_cm < 100)] = "minor"
        result.loc[uk_major_notunnel & (depth_cm >= 100) & (depth_cm < 200)] = "moderate"
        result.loc[uk_major_notunnel & (depth_cm >= 200) & (depth_cm < 600)] = "extensive"
        result.loc[uk_major_notunnel & (depth_cm >= 600)] = "severe"

        result.loc[uk_other & (depth_cm <= 0)] = "no"
        result.loc[uk_other & (depth_cm > 0) & (depth_cm < 50)] = "minor"
        result.loc[uk_other & (depth_cm >= 50) & (depth_cm < 200)] = "moderate"
        result.loc[uk_other & (depth_cm >= 200) & (depth_cm < 600)] = "extensive"
        result.loc[uk_other & (depth_cm >= 600)] = "severe"
    else:
        logging.info("Please enter the type of flood!")

    return result


def intersections_with_damage(
    road_links: gpd.GeoDataFrame,
    flood_key: str,
    flood_type: str,
    flood_path: str,
    clip_path: Optional[str],
    boundary_gdf: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """
    Computes flood depth and damage levels for road segments by intersecting them with
        flood data.

    Parameters:
        road_links (gpd.GeoDataFrame): GeoDataFrame of road links with geometries and
            classifications.
        flood_key (str): Identifier for the flood dataset.
        flood_type (str): Type of flood ("surface" or "river").
        flood_path (str): Path to the flood raster file.
        clip_path (str): Path to the vector file used for clipping.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame of intersections with calculated flood depths
            and damage levels.
    """

    # First restrict to the raster footprint so national-scale networks do not
    # enter the expensive line-splitting/intersection path for a local hazard.
    candidate_links = subset_features_to_raster_extent(road_links, flood_path)

    # Clip road links with features in the provided vector file/boundary.
    clipped_features = clip_features(candidate_links, clip_path, flood_key, boundary_gdf)
    if clipped_features.empty:
        logging.info("Warning: Clip features is None!")
        return None
    # Perform intersection analysis with the flood raster
    intersections = intersect_features_with_raster(
        flood_path,
        flood_key,
        clipped_features,
        flood_type,
    )
    intersections.reset_index(drop=True, inplace=True)
    # Adjust flood depths for embankment heights based on road classification
    """
    embankment against surface flood: 100 cm (motorways/major roads)
    embankment against river flood: 200 cm (motorways/major roads)
    """
    # Determine major roads for embankment adjustment (works for both UK and FAF classifications)
    is_major_road = intersections['road_classification'].isin(['Motorway', 'A Road', 'motorway', 'motorway_link', 'trunk', 'primary', 'secondary'])
    
    if flood_type == "surface":
        intersections.loc[is_major_road, "flood_depth_surface"] = (
            intersections.loc[is_major_road, "flood_depth_surface"] - 100
        ).clip(lower=0)
    else:
        flood_depth_col = f"flood_depth_{flood_type}"
        intersections.loc[is_major_road, flood_depth_col] = (
            intersections.loc[is_major_road, flood_depth_col] - 200
        ).clip(lower=0)

    # Compute damage levels for flooded road segments
    intersections[f"damage_level_{flood_type}"] = compute_damage_levels_on_flooded_roads_vectorized(
        flood_type,
        intersections["road_classification"],
        intersections["trunk_road"] if "trunk_road" in intersections.columns else pd.Series(False, index=intersections.index),
        intersections["road_label"] if "road_label" in intersections.columns else pd.Series("", index=intersections.index),
        intersections[f"flood_depth_{flood_type}"],
    )
    if flood_type == "flood":
        # Keep a clear generic flood label in Script 2 outputs while mirroring to
        # river_* for Script 3/4, which still consume the historical schema.
        intersections["flood_depth_river"] = intersections["flood_depth_flood"]
        intersections["damage_level_river"] = intersections["damage_level_flood"]

    return intersections


def features_with_damage(
    features: gpd.GeoDataFrame,
    intersections: gpd.GeoDataFrame,
    damage_level_dict: Dict,
    damage_level_dict_reverse: Dict,
) -> gpd.GeoDataFrame:
    """
    Aggregates flood depth and damage levels for road links based on intersection data.

    Parameters:
        features (gpd.GeoDataFrame): GeoDataFrame of road links.
        intersections (gpd.GeoDataFrame): GeoDataFrame of intersections with flood data.
        damage_level_dict (Dict): Mapping of damage levels to numerical values.
        damage_level_dict_reverse (Dict): Reverse mapping of numerical values to damage
            levels.

    Returns:
        gpd.GeoDataFrame: Updated GeoDataFrame of road links with maximum flood depth
            and damage levels.
    """

    # Flood depth
    if (
        "flood_depth_surface" in intersections.columns
        and "flood_depth_river" in intersections.columns
    ):
        intersections["flood_depth_max"] = intersections[
            ["flood_depth_surface", "flood_depth_river"]
        ].max(axis=1)
    elif "flood_depth_surface" in intersections.columns:
        intersections["flood_depth_max"] = intersections.flood_depth_surface
    elif "flood_depth_flood" in intersections.columns:
        intersections["flood_depth_max"] = intersections.flood_depth_flood
    elif "flood_depth_river" in intersections.columns:
        intersections["flood_depth_max"] = intersections.flood_depth_river
    else:
        logging.info("Error: flood depth columns are missing!")
        sys.exit()

    # Damage level
    if (
        "damage_level_surface" in intersections.columns
        and "damage_level_river" in intersections.columns
    ):
        intersections["damage_level_surface"] = intersections[
            "damage_level_surface"
        ].map(damage_level_dict)
        intersections["damage_level_river"] = intersections["damage_level_river"].map(
            damage_level_dict
        )
        intersections["damage_level_max"] = intersections[
            ["damage_level_surface", "damage_level_river"]
        ].max(axis=1)
    elif "damage_level_surface" in intersections.columns:
        intersections["damage_level_surface"] = intersections[
            "damage_level_surface"
        ].map(damage_level_dict)
        intersections["damage_level_max"] = intersections.damage_level_surface
    elif "damage_level_flood" in intersections.columns:
        intersections["damage_level_flood"] = intersections[
            "damage_level_flood"
        ].map(damage_level_dict)
        intersections["damage_level_max"] = intersections.damage_level_flood
    elif "damage_level_river" in intersections.columns:
        intersections["damage_level_river"] = intersections["damage_level_river"].map(
            damage_level_dict
        )
        intersections["damage_level_max"] = intersections.damage_level_river
    else:
        logging.info("Error: damage level columns are missing!")

    intersections_gp = intersections.groupby("e_id", as_index=False).agg(
        {
            "flood_depth_max": "max",
            "damage_level_max": "max",
        }
    )
    intersections_gp["damage_level_max"] = (
        pd.to_numeric(intersections_gp["damage_level_max"], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
        .astype(int)
        .map(damage_level_dict_reverse)
    )

    features = features.merge(
        intersections_gp[["e_id", "flood_depth_max", "damage_level_max"]],
        how="left",
        on="e_id",
    )
    features["flood_depth_max"] = features["flood_depth_max"].fillna(0.0)
    features["damage_level_max"] = features["damage_level_max"].fillna("no")

    return features


def main(depth_key, event_key):
    """
    Main function to perform disruption analysis on road networks under flood scenarios.

    Parameters:
        depth_key (int): Flood depth threshold in centimeters for road closure.
                        Determines when roads become impassable. Common values: 15, 30, 60 cm.
                        Controls the speed reduction curve for flooded roads.
        event_key (str): Scenario identifier for flood event.
                For the Fairfax toy dataset use:
                - '1' = base
                - '2' = low
                - '3' = high
                Used to locate hazard rasters and organize outputs.

    Model Inputs:
        - edge_flows_32p.gpq:
            Base scenario output containing road network simulation results.
        - GB_road_links_with_bridges.gpq:
            GeoDataFrame of road network elements with attributes.
        - JBA Flood Map (RASTER):
            Raster data representing flood scenarios.
        - JBA Flood Map (Vector):
            Vector data used for clipping road links to flood extents.

    Model Outputs:
        - intersections_x.pq:
            GeoDataFrame of feature intersections with flood depth and damage levels.
        - road_links_x.gpq:
            GeoDataFrame of road links with aggregated maximum flood depth and
                damage levels.

    Returns:
        None: Outputs are saved to files.
    """
    # Normalize event key so calls from CLI and direct Python are consistent
    event_key = str(event_key).strip()
    logging.info(f"[MAIN START] depth_key={depth_key} cm, event_key={event_key}")

    # base scenario simulation results
    base_scenario_path = (
        base_path.parent
        / "results"
        / "base_scenario"
        / get_results_variant()
        / "edge_flows.gpq"
    )
    logging.info(f"[LOAD] Loading base scenario from {base_scenario_path}")
    print(f"DEBUG: Loading {base_scenario_path} (exists={base_scenario_path.exists()})")
    base_scenario_links = gpd.read_parquet(base_scenario_path)
    logging.info(f"[LOAD] Base scenario loaded: {len(base_scenario_links)} rows")
    print(f"DEBUG: Base scenario shape={base_scenario_links.shape}")
    
    # Remove duplicate columns if they exist
    base_scenario_links = base_scenario_links.loc[:, ~base_scenario_links.columns.duplicated()]

    # If both acc_* and current_* exist, prefer current_* and drop acc_*
    for acc_col, cur_col in (
        ("acc_capacity", "current_capacity"),
        ("acc_speed", "current_speed"),
        ("acc_flow", "current_flow"),
    ):
        if acc_col in base_scenario_links.columns and cur_col in base_scenario_links.columns:
            base_scenario_links = base_scenario_links.drop(columns=[acc_col])

    base_scenario_links.rename(
        columns={
            "acc_capacity": "current_capacity",
            "acc_speed": "current_speed",
            "acc_flow": "current_flow",
        },
        inplace=True,
    )
    base_scenario_links = base_scenario_links.loc[:, ~base_scenario_links.columns.duplicated()]

    # damage level dicts
    damage_level_dict = {
        "no": 0,
        "minor": 1,
        "moderate": 2,
        "extensive": 3,
        "severe": 4,
    }
    damage_level_dict_reverse = {i: k for k, i in damage_level_dict.items()}

    # load analysis boundary (DMV study area preferred)
    analysis_boundary = load_analysis_boundary(base_path)

    road_links_path = first_existing(
        [
            base_path / "networks" / "faf5" / "faf5_road_links.gpq",
            base_path / "inputs" / "networks" / "faf5" / "faf5_road_links.gpq",
        ]
    )
    if road_links_path is None:
        raise FileNotFoundError(
            "Could not find faf5_road_links.gpq in standard or toy input paths"
        )

    toy_hazard_dir = base_path / "inputs" / "test_17node"
    toy_hazard_50m_dir = base_path / "inputs" / "test_141node_50m"
    toy_hazard_candidates = [
        # Prefer higher-resolution 50 m VA rasters if available
        toy_hazard_50m_dir / "va_hazard_class50_141node_base.tif",
        toy_hazard_50m_dir / "va_hazard_class50_141node_low.tif",
        toy_hazard_50m_dir / "va_hazard_class50_141node_high.tif",
        toy_hazard_50m_dir / "va_hazard_class50_141node.tif",
        # Fall back to 1 km VA rasters
        base_path / "inputs" / "test_141node" / "va_hazard_class50_141node_base.tif",
        base_path / "inputs" / "test_141node" / "va_hazard_class50_141node_low.tif",
        base_path / "inputs" / "test_141node" / "va_hazard_class50_141node_high.tif",
        base_path / "inputs" / "test_141node" / "va_hazard_class50_141node.tif",
        # Fall back to Fairfax test rasters
        toy_hazard_dir / "fairfax_hazard_class50_17node_base.tif",
        toy_hazard_dir / "fairfax_hazard_class50_17node_low.tif",
        toy_hazard_dir / "fairfax_hazard_class50_17node_high.tif",
        toy_hazard_dir / "fairfax_hazard_class50_17node.tif",
    ]
    toy_hazard_path = first_existing(toy_hazard_candidates)

    if toy_hazard_path is not None:
        toy_clip_path = first_existing(
            [
                base_path / "study_area" / "fairfax_study_area.gpkg",
                base_path / "study_area" / "fairfax_study_area.geojson",
                base_path / "study_area" / "va_study_area.gpkg",
                base_path / "study_area" / "va_study_area.geojson",
            ]
        )
        if toy_clip_path is None:
            logging.warning(
                "No toy study-area clip file found; falling back to analysis boundary clipping only."
            )

        toy_variant_map = {1: "base", 2: "low", 3: "high"}
        if event_key.lower() == "all":
            toy_event_keys = sorted(toy_variant_map)
        else:
            try:
                toy_event_keys = [int(part.strip()) for part in event_key.split(",") if part.strip()]
            except (TypeError, ValueError):
                raise ValueError(
                    "In toy mode, event_key must be one of: 1, 2, 3, all, or a comma-separated list like 2,3"
                )
        invalid_event_keys = [key for key in toy_event_keys if key not in toy_variant_map]
        if invalid_event_keys:
            raise ValueError(
                f"Invalid toy-mode event_key(s)={invalid_event_keys}. Use 1=base, 2=low, 3=high, all, or e.g. 2,3."
            )

        # In toy mode these scenario rasters represent the available flood hazard,
        # not a separate surface/river pair. Use the generic "flood" label for
        # clarity; intersections_with_damage mirrors flood_* to river_* for
        # Script 3/4 compatibility. Set NIRD_TOY_FLOOD_TYPES=surface,river only
        # for legacy comparison runs.
        toy_flood_types_raw = os.environ.get("NIRD_TOY_FLOOD_TYPES", "flood")
        toy_flood_types = [
            flood_type.strip().lower()
            for flood_type in toy_flood_types_raw.split(",")
            if flood_type.strip()
        ]
        valid_toy_flood_types = {"surface", "river", "flood"}
        invalid_toy_flood_types = [
            flood_type
            for flood_type in toy_flood_types
            if flood_type not in valid_toy_flood_types
        ]
        if invalid_toy_flood_types:
            raise ValueError(
                "NIRD_TOY_FLOOD_TYPES may only contain 'surface', 'river', and/or 'flood'. "
                f"Got: {invalid_toy_flood_types}"
            )
        if not toy_flood_types:
            raise ValueError("NIRD_TOY_FLOOD_TYPES resolved to no flood types.")
        event_files_by_key = {}
        for event_key_num in toy_event_keys:
            toy_variant = toy_variant_map[event_key_num]
            selected_tif = first_existing(
                [
                    # Prefer 50 m rasters
                    toy_hazard_50m_dir / f"va_hazard_class50_141node_{toy_variant}.tif",
                    # Fall back to 1 km VA rasters
                    base_path / "inputs" / "test_141node" / f"va_hazard_class50_141node_{toy_variant}.tif",
                    # Fall back to Fairfax 17-node rasters
                    toy_hazard_dir / f"fairfax_hazard_class50_17node_{toy_variant}.tif",
                    toy_hazard_path,
                ]
            )
            logging.info(
                f"Toy hazard raster mode enabled: event_key={event_key_num} ({toy_variant}) -> {selected_tif}"
            )
            event_files_by_key[str(event_key_num)] = {
                flood_type: [str(selected_tif)]
                for flood_type in toy_flood_types
            }
        logging.info(f"Toy flood types enabled: {toy_flood_types}")
    else:
        event_files = {flood_type: [] for flood_type in ["surface", "river"]}

    # flood event classification into surface/river flood (non-toy mode only)
    if toy_hazard_path is None:
        flood_types = ["surface", "river", "both"]
        event_files = {flood_type: [] for flood_type in ["surface", "river"]}
        # Iterate through flood types and process files
        for flood_type in flood_types:
            folder_path = raster_path / flood_type
            if folder_path.exists():
                for raster_dir in folder_path.rglob(
                    "Raster"
                ):  # Search for "Raster" directories
                    for tif_file in raster_dir.rglob(
                        "*.tif"
                    ):  # Find .tif files recursively
                        # Filter files with "RD" in the name and exclude those with "IE"
                        if "RD" in tif_file.name and "IE" not in tif_file.name:
                            if flood_type == "both":
                                if "FLSW" in tif_file.name:
                                    target_flood_type = "surface"
                                elif "FLRF" in tif_file.name:
                                    target_flood_type = "river"
                                else:
                                    continue
                            else:
                                target_flood_type = flood_type

                            # Append the file path to the appropriate flood_type list
                            event_files[target_flood_type].append(str(tif_file))

    event_dict = defaultdict(lambda: defaultdict(list))
    if toy_hazard_path is not None:
        for toy_key, toy_event_files in event_files_by_key.items():
            event_dict[toy_key] = defaultdict(list, toy_event_files)
    else:
        for flood_type, list_of_events in event_files.items():
            for event_path in list_of_events:
                # Extract event from path structure
                # Case 1: surface/EventName/Raster/file.tif → parts[-3]="EventName"
                # Case 2: surface/Raster/file.tif → parts[-3]="surface" → extract from filename
                path_parts = Path(event_path).parts
                potential_event_folder = path_parts[-3] if len(path_parts) >= 3 else None
                
                if potential_event_folder not in ["surface", "river", "both", "Raster"]:
                    # It's a meaningful event folder name
                    event = potential_event_folder
                else:
                    # Extract from filename - look for numeric identifiers (year, scenario code, etc.)
                    filename = Path(event_path).stem  # filename without extension
                    import re
                    
                    # Find all numeric sequences in the filename
                    numbers = re.findall(r'\d+', filename)
                    event = None
                    
                    # Use first numeric sequence found (typically scenario/year)
                    if numbers:
                        for num in numbers:
                            # Prefer longer numeric sequences (more likely to be a year or meaningful ID)
                            if len(num) >= 3:  # Changed from hardcoded year check
                                event = num
                                break
                        if not event:
                            event = numbers[0] if numbers else "default"
                    else:
                        # Fallback: use first word-like part of filename
                        event = filename.split("_")[0]
                
                if event:
                    event_dict[event][flood_type].append(event_path)

    # analysis
    logging.info(f"[ANALYSIS] Found {len(event_dict)} flood events, filtering for event_key={event_key}")
    print(f"DEBUG: event_dict keys={list(event_dict.keys())}")
    
    processed_event = False
    for flood_key, v in event_dict.items():
        if toy_hazard_path is None and flood_key != event_key:
            logging.info(f"[SKIP] Skipping flood_key={flood_key} (not matching event_key={event_key})")
            continue
        processed_event = True
        logging.info(f"[PROCESS] Starting intersection analysis for flood_key={flood_key}")
        print(f"DEBUG: Starting intersection for event {flood_key}...")
        # out path
        out_path = (
            base_path.parent
            / "results"
            / "disruption_analysis"
            / get_results_variant()
            / str(depth_key)
        )
        logging.info(f"[PATHS] Output directory: {out_path}")
        print(f"DEBUG: Output path={out_path}")
        
        # Load road links once outside the loop for efficiency
        # load road links (SUBNETWORK)
        road_links = gpd.read_parquet(road_links_path)
        logging.info(f"[LOAD] Road links loaded for event {flood_key}: {len(road_links)} rows")

        intersections = gpd.GeoDataFrame(
            columns=["e_id", "length", "index_i", "index_j"]
        )

        for flood_type, flood_paths in v.items():
            logging.info(f"[FLOOD_TYPE] Processing flood_type={flood_type} with {len(flood_paths)} files")
            print(f"DEBUG: Processing {flood_type} with {len(flood_paths)} rasters")
            # Use a fresh copy for each flood type to avoid accumulated columns
            road_links_fresh = road_links.copy()
            
            for flood_path in flood_paths:
                logging.info(f"[RASTER] Processing raster: {flood_path}")
                print(f"DEBUG: Processing raster {Path(flood_path).name}")
                
                if toy_hazard_path is not None:
                    clip_path = toy_clip_path
                else:
                    # clip path
                    clip_path = Path(
                        flood_path.replace("Raster", "Vector").replace(".tif", ".shp")
                    )
                    clip_path1 = clip_path.with_name(clip_path.name.replace("_RD_", "_VE_"))
                    clip_path2 = clip_path.with_name(clip_path.name.replace("_RD_", "_PR_"))
                    if clip_path1.exists():
                        clip_path = clip_path1
                    elif clip_path2.exists():
                        clip_path = clip_path2
                    else:
                        logging.info(f"[SKIP] Cannot find vector file for: {flood_path}")
                        print(f"DEBUG: Missing vector clip file")
                        continue  # Skip further processing for this file

                # intersections
                logging.info(f"[INTERSECT] Computing intersections for {flood_type}...")
                raster_start = time.perf_counter()
                temp_file = intersections_with_damage(
                    road_links_fresh,
                    flood_key,
                    flood_type,
                    flood_path,
                    clip_path,
                    analysis_boundary,
                )
                if temp_file is None:
                    logging.warning(f"[INTERSECT_FAIL] No results from intersections_with_damage")
                    continue
                raster_elapsed = time.perf_counter() - raster_start
                logging.info(
                    f"[INTERSECT_OK] Got {len(temp_file)} intersection results in {raster_elapsed:.2f}s"
                )
                merge_columns = [
                    "e_id",
                    "length",
                    "index_i",
                    "index_j",
                    f"flood_depth_{flood_type}",
                    f"damage_level_{flood_type}",
                ]
                if flood_type == "flood":
                    # Preserve compatibility mirror columns for Script 3/4.
                    merge_columns.extend(["flood_depth_river", "damage_level_river"])
                intersections = intersections.merge(
                    temp_file[merge_columns],
                    on=["e_id", "length", "index_i", "index_j"],
                    how="outer",
                )

        # save intersectiosn for damage analysis
        if intersections.empty:
            logging.warning("[EMPTY] Intersections result is empty! Skipping output.")
            print("DEBUG: Intersections are empty!")
            continue

        logging.info(f"[SAVE_INTERSECT] Saving {len(intersections)} intersection rows")
        (out_path / "intersections").mkdir(parents=True, exist_ok=True)
        intersections_path = out_path / "intersections" / f"intersections_{flood_key}.pq"
        intersections.to_parquet(intersections_path)
        validate_output(intersections_path, intersections, "intersections")
        log_summary("intersections", intersections)
        print(f"DEBUG: Saved intersections to {intersections_path}")

        # road integrations - reload fresh copy
        logging.info(f"[FEATURES] Computing features_with_damage...")
        road_links = features_with_damage(
            road_links,
            intersections,
            damage_level_dict,
            damage_level_dict_reverse,
        )
        logging.info(f"[FEATURES_OK] Features computed, {len(road_links)} road links")

        # max_speed estimation
        """
        Uncertainties of flood depth threshold for road closure (cm): 15, 30, 60
        """
        # attach capacity and speed info on D-0
        # Drop duplicate columns if they exist (from previous iterations)
        logging.info(f"[SPEED] Computing speed restrictions...")
        cols_to_drop = ["combined_label", "free_flow_speeds", "initial_flow_speeds", 
                        "min_flow_speeds", "current_capacity", "current_speed", "current_flow"]
        cols_to_drop = [c for c in cols_to_drop if c in road_links.columns]
        if cols_to_drop:
            road_links = road_links.drop(columns=cols_to_drop)
        
        road_links = road_links.merge(
            base_scenario_links[
                [
                    "e_id",
                    "combined_label",
                    "free_flow_speeds",
                    "initial_flow_speeds",
                    "min_flow_speeds",
                    "current_capacity",
                    "current_speed",
                    "current_flow",
                ]
            ],
            how="left",
            on="e_id",
        )

        # Ensure no duplicate columns after merge
        road_links = road_links.loc[:, ~road_links.columns.duplicated()]

        # Ensure flood depth and speed columns exist and are numeric
        if "flood_depth_max" not in road_links.columns:
            road_links["flood_depth_max"] = 0.0
        road_links["flood_depth_max"] = road_links["flood_depth_max"].fillna(0.0)
        road_links["free_flow_speeds"] = road_links["free_flow_speeds"].fillna(50.0)

        # `depth_key` is the closure threshold in centimeters.
        # Example: with `depth_key=15`, a 10 cm flood still allows reduced speed,
        # while a 20 cm flood sets `max_speed` to 0 for that link.
        flood_depth_cm = pd.to_numeric(road_links["flood_depth_max"], errors="coerce") * 100.0
        free_flow_speed = pd.to_numeric(road_links["free_flow_speeds"], errors="coerce")
        road_links["max_speed"] = np.where(
            flood_depth_cm < depth_key,
            free_flow_speed * ((flood_depth_cm / depth_key - 1) ** 2),
            0.0,
        )
        (out_path / "links").mkdir(parents=True, exist_ok=True)
        links_path = out_path / "links" / f"road_links_{flood_key}.gpq"
        logging.info(f"[SAVE_LINKS] Saving {len(road_links)} road links to {links_path}")
        road_links.to_parquet(links_path)
        validate_output(links_path, road_links, "road_links")
        log_summary("road_links", road_links)
        logging.info(f"[COMPLETE] Script 2 completed successfully for event_key={event_key}, depth_key={depth_key}")
        print(f"DEBUG: Script 2 COMPLETE! Outputs saved to {out_path}")

    if not processed_event:
        logging.warning(
            f"[NO_MATCH] event_key={event_key} not found in discovered events: {list(event_dict.keys())}"
        )
        print(f"DEBUG: No matching event_key={event_key}. Available events: {list(event_dict.keys())}")


if __name__ == "__main__":
    import time
    start_time = time.time()
    logging.basicConfig(
        format="%(asctime)s %(process)d %(filename)s %(levelname)s %(message)s",
        level=logging.INFO,
    )
    print("="*60)
    print("SCRIPT 2: Intersection Analysis - STARTING")
    print("="*60)
    try:  # in bash inputs will be str by default
        depth_key = sys.argv[1]
        event_key = sys.argv[2]
        print(f"CLI Args: depth_key={depth_key}, event_key={event_key}")
        logging.info(f"Script 2 starting with depth_key={depth_key}, event_key={event_key}")
        main(int(depth_key), str(event_key))
        elapsed = time.time() - start_time
        print("="*60)
        print(f"SCRIPT 2: COMPLETED SUCCESSFULLY in {elapsed:.2f} seconds")
        print("="*60)
        logging.info(f"Script 2 completed in {elapsed:.2f} seconds")
    except IndexError or NameError as e:
        elapsed = time.time() - start_time
        error_msg = "Please enter depth_key and event_key!"
        logging.error(error_msg)
        print(f"ERROR: {error_msg}")
        print(f"Usage: python {sys.argv[0]} <depth_key> <event_key>")
        print(f"  depth_key: flood depth threshold in cm (e.g., 15, 30, 60)")
        print(f"  event_key (toy dataset): 1=base, 2=low, 3=high")
        sys.exit(1)
    except Exception as e:
        elapsed = time.time() - start_time
        logging.exception(f"Unexpected error in script 2 after {elapsed:.2f}s")
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
