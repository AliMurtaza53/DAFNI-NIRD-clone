import hashlib
from pathlib import Path
import geopandas as gpd
import pandas as pd

base = Path(r"C:\Users\alimu\NIRD_Data\results\disruption_analysis\revision\30")
intersections_path = base / "intersections" / "intersections_1.pq"
road_links_path = base / "links" / "road_links_1.gpq"


def file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def content_md5_intersections(path: Path):
    df = pd.read_parquet(path)
    cols = [
        c
        for c in [
            "e_id",
            "index_i",
            "index_j",
            "flood_depth_surface",
            "flood_depth_river",
            "damage_level_surface",
            "damage_level_river",
        ]
        if c in df.columns
    ]
    d = df[cols].copy()
    for c in d.columns:
        d[c] = d[c].astype(str)
    d = d.sort_values(cols).reset_index(drop=True)
    s = "\n".join(
        "|".join(map(str, r)) for r in d.astype(str).itertuples(index=False, name=None)
    )
    return hashlib.md5(s.encode()).hexdigest(), len(d), len(cols)


def content_md5_links(path: Path):
    df = pd.read_parquet(path)
    cols = [
        c
        for c in ["e_id", "flood_depth_max", "damage_level_max", "max_speed", "min_speed"]
        if c in df.columns
    ]
    d = df[cols].copy()
    for c in d.columns:
        d[c] = d[c].astype(str)
    d = d.sort_values(cols).reset_index(drop=True)
    s = "\n".join(
        "|".join(map(str, r)) for r in d.astype(str).itertuples(index=False, name=None)
    )
    return hashlib.md5(s.encode()).hexdigest(), len(d), len(cols)


print(f"INTERSECTIONS_FILE={intersections_path}")
print(f"ROAD_LINKS_FILE={road_links_path}")
print(f"intersections_file_md5={file_md5(intersections_path)}")
cm, rows, ncols = content_md5_intersections(intersections_path)
print(f"intersections_content_md5={cm}")
print(f"intersections_rows={rows}, cols={ncols}")
print(f"road_links_file_md5={file_md5(road_links_path)}")
cm2, rows2, ncols2 = content_md5_links(road_links_path)
print(f"road_links_content_md5={cm2}")
print(f"road_links_rows={rows2}, cols={ncols2}")
