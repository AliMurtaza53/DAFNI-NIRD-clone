"""Create synthetic damaged-edge files for Patch 4 validation/smoke runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import duckdb
import geopandas as gpd
import pandas as pd

from nird.utils import load_config


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def first_existing(paths):
    for path in paths:
        p = Path(path)
        if p.exists():
            return p
    return None


def edges_from_legacy(legacy_odpfc: Path, count: int) -> pd.Series:
    con = duckdb.connect()
    try:
        return con.execute(
            f"""
            SELECT DISTINCT CAST(e AS VARCHAR) AS e_id
            FROM read_parquet('{sql_path(legacy_odpfc)}'), UNNEST(path) AS u(e)
            LIMIT {int(count)}
            """
        ).fetchdf()["e_id"]
    finally:
        con.close()


def edges_from_network(count: int) -> pd.Series:
    base_path = Path(load_config()["paths"]["soge_clusters"])
    road_links_path = first_existing(
        [
            base_path / "networks" / "faf5" / "faf5_road_links.gpq",
            base_path / "inputs" / "networks" / "faf5" / "faf5_road_links.gpq",
        ]
    )
    if road_links_path is None:
        raise FileNotFoundError("Could not find faf5_road_links.gpq")
    road_links = gpd.read_parquet(road_links_path)
    edge_col = "e_id" if "e_id" in road_links.columns else "id"
    return road_links[edge_col].astype(str).drop_duplicates().head(count)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event-id", default="synthetic_20k")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--legacy-odpfc", type=Path)
    parser.add_argument(
        "--source",
        choices=["legacy", "network"],
        default="legacy",
    )
    args = parser.parse_args()

    if args.source == "legacy":
        if args.legacy_odpfc is None:
            raise ValueError("--legacy-odpfc is required when --source legacy")
        edge_ids = edges_from_legacy(args.legacy_odpfc, args.count)
    else:
        edge_ids = edges_from_network(args.count)

    damaged = pd.DataFrame(
        {
            "event_id": args.event_id,
            "e_id": edge_ids.astype(str),
            "damage_level": "synthetic",
            "road_label": "road",
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    damaged.to_parquet(args.output, index=False)
    print(
        f"Wrote {len(damaged)} synthetic damaged edges for event_id={args.event_id} "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()
