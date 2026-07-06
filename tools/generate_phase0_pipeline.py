"""Extract run_flood_disruption (main) into pipeline module."""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
src_text = (REPO / "scripts/2_intersection_analysis.py").read_text(encoding="utf-8")
lines = src_text.splitlines()
tree = ast.parse(src_text)

main_src = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "main":
        main_src = "\n".join(lines[node.lineno - 1 : node.end_lineno])
        break

if main_src is None:
    raise RuntimeError("main() not found")

main_src = main_src.replace("def main(depth_key, event_key):", "def run_flood_disruption(depth_key, event_key, *, base_path=None):")

header = '''"""Flood disruption pipeline orchestration (Script 2 logic)."""

from __future__ import annotations

import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd

from nird.disruption.flood import (
    DAMAGE_LEVEL_DICT,
    DAMAGE_LEVEL_DICT_REVERSE,
    features_with_damage,
    intersections_with_damage,
)
from nird.disruption.io import first_existing, log_summary, validate_output
from nird.disruption.link_record import apply_legacy_flood_columns
from nird.exposure.raster_line import load_analysis_boundary
from nird.fragility.flood_operational import apply_max_speed_to_links
from nird.utils import get_results_variant, load_config

'''

# Inject base_path resolution at start of function body
inject = '''
    if base_path is None:
        base_path = Path(load_config()["paths"]["soge_clusters"])
    raster_path = base_path / "hazards" / "completed"
'''
main_src = main_src.replace(
    '    """\n    Main function to perform disruption analysis',
    inject + '\n    """\n    Run flood disruption analysis',
)
# Remove module-level base_path/raster_path references - they're now local
# Replace damage_level_dict assignments with imported constants
main_src = main_src.replace(
    """    # damage level dicts
    damage_level_dict = {
        "no": 0,
        "minor": 1,
        "moderate": 2,
        "extensive": 3,
        "severe": 4,
    }
    damage_level_dict_reverse = {i: k for k, i in damage_level_dict.items()}
""",
    """    damage_level_dict = DAMAGE_LEVEL_DICT
    damage_level_dict_reverse = DAMAGE_LEVEL_DICT_REVERSE
""",
)

# Replace max_speed block with apply_max_speed_to_links
old_speed = '''        # `depth_key` is the closure threshold in centimeters.
        # Example: with `depth_key=15`, a 10 cm flood still allows reduced speed,
        # while a 20 cm flood sets `max_speed` to 0 for that link.
        flood_depth_cm = pd.to_numeric(road_links["flood_depth_max"], errors="coerce") * 100.0
        free_flow_speed = pd.to_numeric(road_links["free_flow_speeds"], errors="coerce")
        road_links["max_speed"] = np.where(
            flood_depth_cm < depth_key,
            free_flow_speed * ((flood_depth_cm / depth_key - 1) ** 2),
            0.0,
        )'''

new_speed = """        road_links = apply_max_speed_to_links(road_links, depth_key=depth_key)
        road_links = apply_legacy_flood_columns(
            road_links, depth_key=depth_key, event_id=flood_key
        )"""

if old_speed not in main_src:
    raise RuntimeError("max_speed block not found for replacement")
main_src = main_src.replace(old_speed, new_speed)

# Remove duplicate import re inside loop - we import at top
main_src = main_src.replace("                    import re\n\n", "")

out_path = REPO / "src/nird/disruption/pipeline.py"
out_path.write_text(header + main_src + "\n", encoding="utf-8")
print(f"Wrote {out_path}")
