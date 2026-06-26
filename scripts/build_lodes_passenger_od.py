"""Build county-to-county LODES passenger OD and map to network assignment nodes.

Pipeline:
  1. LODES block OD (main + aux per state) + geographic crosswalk -> county OD
  2. County OD -> nearest network nodes via county shapefile centroids
  3. Collapsed assignment OD for Script 1 (vehicle_type=car)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from nird.geo_runtime import configure_geo_runtime
from nird.lodes_county_od import county_od_to_assignment_schema, run_lodes_county_od
from nird.lodes_paths import resolve_lodes_data_root
from nird.utils import load_config
from preprocess.map_bts_od_to_network_centroids import map_county_od_via_county_shp

LOGGER = logging.getLogger(__name__)


def collapse_passenger_assignment_od(centroid_od: pd.DataFrame) -> pd.DataFrame:
    """Sum county-mapped passenger flows to Script 1 assignment schema."""
    flow_col = "Car21" if "Car21" in centroid_od.columns else "daily_truck_trips"
    grouped = (
        centroid_od.groupby(["origin_node", "destination_node"], as_index=False)[flow_col]
        .sum()
        .rename(columns={flow_col: "Car21"})
    )
    grouped["Car21"] = pd.to_numeric(grouped["Car21"], errors="coerce").fillna(0.0)
    return grouped[grouped["Car21"] > 0].reset_index(drop=True)


def build_lodes_passenger_od(
    base_path: Path,
    *,
    year: int = 2022,
    job_type: str = "JT00",
    states: list[str] | None = None,
    force_county: bool = False,
    force_centroid: bool = False,
    skip_centroid: bool = False,
    county_shp_path: str | None = None,
    network_nodes_path: str | None = None,
) -> dict[str, str]:
    lodes_root = resolve_lodes_data_root(base_path, REPO_ROOT)
    processed = (lodes_root or (base_path.parent / "lodes_data")) / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    county_od_path = processed / f"lodes_county_od_{job_type.lower()}_{year}.parquet"
    centroid_od_path = processed / f"lodes_passenger_centroid_od_{job_type.lower()}_{year}.parquet"
    assignment_od_path = processed / f"lodes_passenger_assignment_od_{job_type.lower()}_{year}.parquet"

    if force_county or not county_od_path.exists():
        LOGGER.info("Building LODES county OD -> %s", county_od_path)
        run_lodes_county_od(
            county_od_path,
            states=states,
            job_type=job_type,
            year=year,
            base_path=base_path,
            repo_root=REPO_ROOT,
            summary_json_path=processed / f"lodes_county_od_{job_type.lower()}_{year}_summary.json",
        )
    else:
        LOGGER.info("Reusing existing county OD: %s", county_od_path)

    outputs = {
        "county_od": str(county_od_path),
        "centroid_od": str(centroid_od_path),
        "assignment_od": str(assignment_od_path),
    }

    if skip_centroid:
        return outputs

    if force_centroid or not centroid_od_path.exists():
        county_od = pd.read_parquet(county_od_path)
        mapper_od = county_od_to_assignment_schema(county_od)

        shp = county_shp_path or str(base_path / "inputs" / "census_datasets" / "tl_2024_us_county.shp")
        nodes = network_nodes_path
        if nodes is None:
            gdb_candidates = [
                base_path.parent / "faf5_data" / "FAF5Network.gdb",
                Path.home() / "Desktop" / "data" / "faf5_data" / "FAF5Network.gdb",
            ]
            for gdb in gdb_candidates:
                node_candidate = gdb / "nodes"
                if node_candidate.exists():
                    nodes = str(node_candidate)
                    break
        if nodes is None:
            raise FileNotFoundError("Could not resolve network nodes layer for county-to-node mapping.")

        LOGGER.info("Mapping county passenger OD via %s -> %s", shp, nodes)
        centroid_od, _node_map, summary = map_county_od_via_county_shp(
            mapper_od,
            shp,
            nodes,
        )
        centroid_od.to_parquet(centroid_od_path, index=False)
        summary_path = processed / f"lodes_passenger_centroid_map_{job_type.lower()}_{year}_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        outputs["centroid_map_summary"] = str(summary_path)
    else:
        LOGGER.info("Reusing existing centroid OD: %s", centroid_od_path)
        centroid_od = pd.read_parquet(centroid_od_path)

    assignment_od = collapse_passenger_assignment_od(centroid_od)
    assignment_od.to_parquet(assignment_od_path, index=False)
    outputs["assignment_od"] = str(assignment_od_path)
    outputs["assignment_rows"] = str(len(assignment_od))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build LODES county-to-county passenger OD.")
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--job-type", default="JT00", help="LODES job type (JT00=all jobs, JT01=primary)")
    parser.add_argument(
        "--states",
        nargs="*",
        default=None,
        help="Optional state abbreviations (e.g. va md). Default: all CONUS states.",
    )
    parser.add_argument("--force-county", action="store_true")
    parser.add_argument("--force-centroid", action="store_true")
    parser.add_argument("--skip-centroid", action="store_true", help="Only build county OD; skip network mapping.")
    parser.add_argument("--county-shp", default=None)
    parser.add_argument("--network-nodes", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    configure_geo_runtime()
    config = load_config()
    base_path = Path(config["paths"]["soge_clusters"])

    outputs = build_lodes_passenger_od(
        base_path,
        year=args.year,
        job_type=args.job_type,
        states=args.states,
        force_county=args.force_county,
        force_centroid=args.force_centroid,
        skip_centroid=args.skip_centroid,
        county_shp_path=args.county_shp,
        network_nodes_path=args.network_nodes,
    )
    for key, value in outputs.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
