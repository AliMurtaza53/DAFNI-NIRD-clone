"""Generate Phase 0 disruption modules from Script 2."""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
src_text = (REPO / "scripts/2_intersection_analysis.py").read_text(encoding="utf-8")
lines = src_text.splitlines()
tree = ast.parse(src_text)


def get_func(name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise KeyError(name)


op_header = '''"""Flood operational fragility: intensity to max_speed."""

from __future__ import annotations

import numpy as np
import pandas as pd


'''
op_body = get_func("compute_maximum_speed_on_flooded_roads")
op_extra = '''

def apply_max_speed_to_links(
    road_links: pd.DataFrame,
    *,
    depth_key: int,
    depth_col: str = "flood_depth_max",
    free_flow_col: str = "free_flow_speeds",
    out_col: str = "max_speed",
) -> pd.DataFrame:
    """Vectorized speed cap using the Script 2 closure rule (depth_key in cm)."""
    out = road_links.copy()
    if depth_col not in out.columns:
        out[depth_col] = 0.0
    out[depth_col] = out[depth_col].fillna(0.0)
    if free_flow_col not in out.columns:
        out[free_flow_col] = 50.0
    out[free_flow_col] = out[free_flow_col].fillna(50.0)
    flood_depth_cm = pd.to_numeric(out[depth_col], errors="coerce") * 100.0
    free_flow_speed = pd.to_numeric(out[free_flow_col], errors="coerce")
    out[out_col] = np.where(
        flood_depth_cm < depth_key,
        free_flow_speed * ((flood_depth_cm / depth_key - 1) ** 2),
        0.0,
    )
    return out
'''
(REPO / "src/nird/fragility").mkdir(parents=True, exist_ok=True)
(REPO / "src/nird/fragility/__init__.py").write_text(
    '"""Fragility models map intensity to damage and capacity."""\n', encoding="utf-8"
)
(REPO / "src/nird/fragility/flood_operational.py").write_text(
    op_header + op_body + op_extra, encoding="utf-8"
)

cat_header = '''"""Flood categorical fragility: intensity to damage_level."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

'''
cat_body = get_func("compute_damage_level_on_flooded_roads") + "\n\n\n" + get_func(
    "compute_damage_levels_on_flooded_roads_vectorized"
)
(REPO / "src/nird/fragility/flood_categorical.py").write_text(cat_header + cat_body, encoding="utf-8")

exp_header = '''"""Raster-line exposure sampling via snail."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import box

from snail import intersection

from nird.geo_runtime import (
    CONUS_TARGET_CRS,
    align_extent_to_features_crs,
    build_snail_grid,
    rasterio_env,
)

TARGET_CRS = CONUS_TARGET_CRS

SPLIT_SIMPLIFY_TOLERANCE_M = float(os.environ.get("NIRD_SPLIT_SIMPLIFY_TOLERANCE_M", "0"))
ENABLE_SPLIT_CACHE = os.environ.get("NIRD_ENABLE_SPLIT_CACHE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
}
_SPLIT_CACHE: dict = {}


def first_existing(paths):
    """Return first existing path from a sequence, else None."""
    for path in paths:
        p = Path(path)
        if p.exists():
            return p
    return None


'''
exp_body = (
    get_func("subset_features_to_raster_extent")
    + "\n\n\n"
    + get_func("load_analysis_boundary")
    + "\n\n\n"
    + get_func("intersect_features_with_raster")
    + "\n\n\n"
    + get_func("clip_features")
)
(REPO / "src/nird/exposure").mkdir(parents=True, exist_ok=True)
(REPO / "src/nird/exposure/__init__.py").write_text(
    '"""Exposure sampling: hazard fields onto network links."""\n', encoding="utf-8"
)
(REPO / "src/nird/exposure/raster_line.py").write_text(exp_header + exp_body, encoding="utf-8")

flood_header = '''"""Flood disruption: exposure + fragility aggregation onto links."""

from __future__ import annotations

import logging
import sys
from typing import Dict, Optional

import geopandas as gpd
import numpy as np
import pandas as pd

from nird.exposure.raster_line import (
    clip_features,
    intersect_features_with_raster,
    subset_features_to_raster_extent,
)
from nird.fragility.flood_categorical import compute_damage_levels_on_flooded_roads_vectorized

DAMAGE_LEVEL_DICT: Dict[str, int] = {
    "no": 0,
    "minor": 1,
    "moderate": 2,
    "extensive": 3,
    "severe": 4,
}
DAMAGE_LEVEL_DICT_REVERSE: Dict[int, str] = {v: k for k, v in DAMAGE_LEVEL_DICT.items()}


'''
flood_body = get_func("intersections_with_damage") + "\n\n\n" + get_func("features_with_damage")
(REPO / "src/nird/disruption").mkdir(parents=True, exist_ok=True)
(REPO / "src/nird/disruption/__init__.py").write_text(
    '"""Disruption pipeline: link-level hazard outputs."""\n', encoding="utf-8"
)
(REPO / "src/nird/disruption/flood.py").write_text(flood_header + flood_body, encoding="utf-8")

print("Generated fragility, exposure, disruption/flood modules")
