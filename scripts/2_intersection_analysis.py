import sys
import os
from typing import Dict, Optional
from pathlib import Path

import geopandas as gpd
import numpy as np
from collections import defaultdict
import rasterio

from snail import io, intersection
from nird.utils import load_config
import warnings
import logging

warnings.filterwarnings("ignore")

base_path = Path(load_config()["paths"]["soge_clusters"])
raster_path = base_path / "hazards" / "completed"
TARGET_CRS = "EPSG:2163"  # US National Atlas Equal Area (use for USA networks)


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


def load_usa_boundary() -> gpd.GeoDataFrame:
    """Load a USA boundary polygon from hardcoded bounding boxes."""
    from shapely.geometry import box
    
    # Continental US, Alaska, and Hawaii bounding boxes
    continental = box(-125, 24, -66, 50)
    alaska = box(-170, 50, -130, 72)
    hawaii = box(-160, 18, -154, 23)
    
    # Merge all regions
    usa_geom = continental.union(alaska).union(hawaii)
    usa = gpd.GeoDataFrame(
        {"name": ["USA"]}, 
        geometry=[usa_geom],
        crs="EPSG:4326"
    )
    return usa


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

    # run the intersection analysis using a windowed raster read
    prepared = intersection.prepare_linestrings(features)

    with rasterio.open(raster_path) as dataset:
        grid_full = intersection.GridDefinition.from_rasterio_dataset(dataset)
        if prepared.crs != grid_full.crs:
            logging.info("Projecting Feature (clipped) CRS to Grid CRS...")
            prepared = prepared.to_crs(grid_full.crs)

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
            crs=dataset.crs,
            width=int(window.width),
            height=int(window.height),
            transform=tuple(window_transform)[:6],
        )

    intersections = intersection.split_linestrings(prepared, grid)
    intersections = intersection.apply_indices(intersections, grid)
    intersections[f"flood_depth_{flood_type}"] = (
        intersection.get_raster_values_for_splits(intersections, raster)
    )

    # reproject back
    intersections = intersections.to_crs(TARGET_CRS)
    intersections["length"] = intersections.geometry.length

    return intersections


def clip_features(
    features: gpd.GeoDataFrame,
    clip_path: str,
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
    clips = gpd.read_file(clip_path, engine="pyogrio")  # grid's extent (vector)
    clips = clips.reset_index(drop=True)  # Ensure no 'index_right' column conflicts
    skip_vector_clip = False

    # Temporary QA guard: some Aqueduct vector masks are global extent polygons
    # ([-180, -90, 180, 90] in EPSG:4326). Reprojecting this footprint to EPSG:2163
    # can collapse around the antimeridian and unintentionally clip out most links.
    if clips.crs is not None and str(clips.crs).upper().endswith("4326"):
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
    if (not skip_vector_clip) and clips.crs != features.crs:
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


def intersections_with_damage(
    road_links: gpd.GeoDataFrame,
    flood_key: str,
    flood_type: str,
    flood_path: str,
    clip_path: str,
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

    # Clip road links with features in the provided vector file
    clipped_features = clip_features(road_links, clip_path, flood_key, boundary_gdf)
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
        intersections.loc[is_major_road, "flood_depth_river"] = (
            intersections.loc[is_major_road, "flood_depth_river"] - 200
        ).clip(lower=0)

    # Compute damage levels for flooded road segments
    intersections[f"damage_level_{flood_type}"] = intersections.apply(
        lambda row: compute_damage_level_on_flooded_roads(
            flood_type,
            row["road_classification"],
            row.get("trunk_road"),  # Will be None for FAF data
            row.get("road_label"),  # Will be None for FAF data
            row[f"flood_depth_{flood_type}"],
        ),
        axis=1,
    )

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
    intersections_gp["damage_level_max"] = intersections_gp.damage_level_max.astype(
        int
    ).map(damage_level_dict_reverse)

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

    Parameters:
        depth_thres (int): Flood depth threshold in centimeters for road closure.

    Returns:
        None: Outputs are saved to files.
    """
    # base scenario simulation results
    base_scenario_links = gpd.read_parquet(
        base_path.parent / "results" / "base_scenario" / "revision" / "edge_flows.gpq"
    )
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

    # load USA boundary for clipping global rasters
    usa_boundary = load_usa_boundary()

    # flood event classification into surface/river flood
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
    for flood_key, v in event_dict.items():
        if flood_key != event_key:
            continue
        print(f"Starting intersection for event {flood_key}...")
        # load road links (SUBNETWORK)
        road_links = gpd.read_parquet(
            base_path / "networks" / "faf5" / "faf5_road_links.gpq"
        )

        # out path
        out_path = (
            base_path.parent
            / "results"
            / "disruption_analysis"
            / "revision"
            / str(depth_key)
        )
        
        # Load road links once outside the loop for efficiency
        road_links_base = gpd.read_parquet(
            base_path / "networks" / "faf5" / "faf5_road_links.gpq"
        )

        intersections = gpd.GeoDataFrame(
            columns=["e_id", "length", "index_i", "index_j"]
        )

        for flood_type, flood_paths in v.items():
            # Use a fresh copy for each flood type to avoid accumulated columns
            road_links_fresh = road_links_base.copy()
            
            for flood_path in flood_paths:
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
                    logging.info(f"Cannot find vector file for: {flood_path}")
                    continue  # Skip further processing for this file

                # intersections
                temp_file = intersections_with_damage(
                    road_links_fresh,
                    flood_key,
                    flood_type,
                    flood_path,
                    clip_path,
                    usa_boundary,
                )
                if temp_file is None:
                    continue
                intersections = intersections.merge(
                    temp_file[
                        [
                            "e_id",
                            "length",
                            "index_i",
                            "index_j",
                            f"flood_depth_{flood_type}",
                            f"damage_level_{flood_type}",
                        ]
                    ],
                    on=["e_id", "length", "index_i", "index_j"],
                    how="outer",
                )

        # save intersectiosn for damage analysis
        if intersections.empty:
            logging.info("Warning: intersections result is empty!")
            continue

        (out_path / "intersections").mkdir(parents=True, exist_ok=True)
        intersections_path = out_path / "intersections" / f"intersections_{flood_key}.pq"
        intersections.to_parquet(intersections_path)
        validate_output(intersections_path, intersections, "intersections")
        log_summary("intersections", intersections)

        # road integrations - reload fresh copy
        road_links = gpd.read_parquet(
            base_path / "networks" / "faf5" / "faf5_road_links.gpq"
        )
        road_links = features_with_damage(
            road_links,
            intersections,
            damage_level_dict,
            damage_level_dict_reverse,
        )

        # max_speed estimation
        """
        Uncertainties of flood depth threshold for road closure (cm): 15, 30, 60
        """
        # attach capacity and speed info on D-0
        # Drop duplicate columns if they exist (from previous iterations)
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

        # compute maximum speed restriction on individual road links
        road_links["max_speed"] = road_links.apply(
            lambda row: compute_maximum_speed_on_flooded_roads(
                row["flood_depth_max"],
                row["free_flow_speeds"],
                threshold=depth_key,
            ),
            axis=1,
        )
        (out_path / "links").mkdir(parents=True, exist_ok=True)
        links_path = out_path / "links" / f"road_links_{flood_key}.gpq"
        road_links.to_parquet(links_path)
        validate_output(links_path, road_links, "road_links")
        log_summary("road_links", road_links)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(process)d %(filename)s %(message)s",
        level=logging.INFO,
    )
    try:  # in bash inputs will be str by default
        depth_key = sys.argv[1]
        event_key = sys.argv[2]
        main(int(depth_key), str(event_key))
    except IndexError or NameError:
        logging.info("Please enter depth_key and event_key!")
