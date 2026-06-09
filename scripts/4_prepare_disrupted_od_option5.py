"""Option 5 candidate: materialize only event-disrupted baseline OD paths.

The current Script 4 can consume:

    results/disruption_analysis/<variant>/od/odpfc_<depth>_<event>.pq

When that file is absent, Script 4 falls back to the full baseline
``base_scenario/<variant>/odpfc.pq``. This candidate creates the event-specific
file directly by:

1. loading damaged edge ids from Script 2's ``road_links_<event>.gpq``;
2. solving baseline shortest paths from the OD matrix;
3. keeping only OD paths that touch damaged edges; and
4. writing the small disrupted-candidate Parquet for Script 4.

It is intentionally an experiment: it uses current least-cost paths on the
baseline network and does not reproduce the full iterative capacity-feedback
baseline path database.
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import math
import os
import pickle
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import geopandas as gpd
import pandas as pd

import nird.road_revised as func
from nird.utils import get_results_variant, load_config


base_path = Path(load_config()["paths"]["soge_clusters"])


def first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def load_damaged_edge_ids(
    depth_key: int,
    event_key: int,
    damaged_edge_csv: Path | None,
    damaged_edge_sample: int,
) -> set[str]:
    if damaged_edge_csv is not None:
        df = pd.read_csv(damaged_edge_csv)
        if "e_id" not in df.columns:
            raise ValueError(f"{damaged_edge_csv} must contain an e_id column")
        edges = set(df["e_id"].astype(str))
        logging.info("Loaded %s damaged edges from %s", len(edges), damaged_edge_csv)
        return edges

    results_variant = get_results_variant()
    road_links_path = (
        base_path.parent
        / "results"
        / "disruption_analysis"
        / results_variant
        / str(depth_key)
        / "links"
        / f"road_links_{event_key}.gpq"
    )
    if road_links_path.exists():
        road_links = gpd.read_parquet(road_links_path)
        road_links["e_id"] = road_links["e_id"].astype(str)
        if "damage_level_max" in road_links.columns:
            mask = road_links["damage_level_max"].astype(str).str.lower() != "no"
        elif "flood_depth_max" in road_links.columns:
            mask = pd.to_numeric(road_links["flood_depth_max"], errors="coerce").fillna(0) > 0
        else:
            raise ValueError(
                f"{road_links_path} has neither damage_level_max nor flood_depth_max"
            )
        edges = set(road_links.loc[mask, "e_id"])
        logging.info("Loaded %s damaged edges from %s", len(edges), road_links_path)
        return edges

    if damaged_edge_sample <= 0:
        raise FileNotFoundError(
            f"Missing {road_links_path}. Run Script 2 first, pass --damaged-edge-csv, "
            "or pass --damaged-edge-sample for a synthetic profiling mask."
        )

    road_links_path = first_existing(
        [
            base_path / "networks" / "faf5" / "faf5_road_links.gpq",
            base_path / "inputs" / "networks" / "faf5" / "faf5_road_links.gpq",
        ]
    )
    if road_links_path is None:
        raise FileNotFoundError("Could not find faf5_road_links.gpq")
    road_links = gpd.read_parquet(road_links_path, columns=["e_id"])
    edges = set(road_links["e_id"].astype(str).head(damaged_edge_sample))
    logging.warning(
        "Using %s synthetic damaged edges from %s for profiling only.",
        len(edges),
        road_links_path,
    )
    return edges


def load_baseline_inputs(sample_stride: int) -> tuple[gpd.GeoDataFrame, pd.DataFrame, dict]:
    params_root = first_existing(
        [
            base_path / "parameters",
            base_path / "inputs" / "parameters",
        ]
    )
    if params_root is None:
        raise FileNotFoundError("Could not find parameter folder")

    with open(params_root / "flow_breakpoint_dict.json", "r") as f:
        flow_breakpoint_dict = json.load(f)
    with open(params_root / "flow_cap_plph_dict.json", "r") as f:
        flow_capacity_dict = json.load(f)
    with open(params_root / "free_flow_speed_dict.json", "r") as f:
        free_flow_speed_dict = json.load(f)
    with open(params_root / "min_speed_cap.json", "r") as f:
        min_speed_dict = json.load(f)
    with open(params_root / "urban_speed_cap.json", "r") as f:
        urban_speed_dict = json.load(f)

    road_links_path = first_existing(
        [
            base_path / "networks" / "faf5" / "faf5_road_links.gpq",
            base_path / "inputs" / "networks" / "faf5" / "faf5_road_links.gpq",
        ]
    )
    if road_links_path is None:
        raise FileNotFoundError("Could not find faf5_road_links.gpq")
    road_links = gpd.read_parquet(road_links_path)

    od_path = first_existing(
        [
            base_path / "census_datasets" / "faf5_od_matrix.pq",
            base_path / "inputs" / "census_datasets" / "faf5_od_matrix.pq",
            base_path / "inputs" / "test_17node" / "faf5_od_matrix_17x17_test.pq",
        ]
    )
    if od_path is None:
        raise FileNotFoundError("Could not find FAF5 OD matrix")
    od = pd.read_parquet(od_path)
    if sample_stride > 1:
        od = od.iloc[::sample_stride].copy()

    flow_col = "Car21" if "Car21" in od.columns else "flow"
    od[flow_col] = pd.to_numeric(od[flow_col], errors="coerce").fillna(0.0)
    if flow_col != "Car21":
        od = od.rename(columns={flow_col: "Car21"})

    node_dtype = road_links["from_id"].dtype
    if pd.api.types.is_integer_dtype(node_dtype):
        od["origin_node"] = pd.to_numeric(od["origin_node"], errors="raise").astype(node_dtype)
        od["destination_node"] = pd.to_numeric(od["destination_node"], errors="raise").astype(node_dtype)
    else:
        od["origin_node"] = od["origin_node"].astype(node_dtype)
        od["destination_node"] = od["destination_node"].astype(node_dtype)

    road_links = func.edge_init(
        road_links,
        flow_breakpoint_dict,
        flow_capacity_dict,
        free_flow_speed_dict,
        urban_speed_dict,
        min_speed_dict,
        max_flow_speed_dict=None,
    )
    return road_links, od[["origin_node", "destination_node", "Car21"]], flow_breakpoint_dict


def build_args(od: pd.DataFrame, max_origins: int) -> list[tuple]:
    args_df = (
        od.groupby("origin_node", as_index=False)
        .agg(
            destination_node=("destination_node", list),
            Car21=("Car21", list),
        )
        .sort_values("origin_node")
    )
    if max_origins > 0:
        args_df = args_df.head(max_origins)
    return [
        (row.origin_node, list(row.destination_node), list(row.Car21))
        for row in args_df.itertuples(index=False)
    ]


def filter_paths(shortest_path, edge_eids, damaged_edge_idxs: set[int]) -> tuple[list[dict], int, int]:
    origin_node, destinations, paths, flows = shortest_path
    kept: list[dict] = []
    no_path_count = 0
    scanned = 0
    for dest, path, flow in zip(destinations, paths, flows):
        scanned += 1
        if not path:
            no_path_count += 1
            continue
        flood_edge_idxs = [idx for idx in path if idx in damaged_edge_idxs]
        if not flood_edge_idxs:
            continue
        e_id_path = [edge_eids[idx] for idx in path]
        kept.append(
            {
                "origin_node": str(origin_node),
                "destination_node": str(dest),
                "path": e_id_path,
                "flow": float(flow) if flow is not None else 0.0,
                "flood_links": [edge_eids[idx] for idx in flood_edge_idxs],
            }
        )
    return kept, scanned, no_path_count


def add_path_costs(rows: list[dict], edge_costs: dict[str, tuple[float, float, float]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "origin_node",
                "destination_node",
                "path",
                "flow",
                "operating_cost_per_flow",
                "time_cost_per_flow",
                "toll_cost_per_flow",
                "flood_links",
            ]
        )

    for row in rows:
        fuel = time_cost = toll = 0.0
        for e_id in row["path"]:
            edge_fuel, edge_time, edge_toll = edge_costs.get(str(e_id), (0.0, 0.0, 0.0))
            fuel += edge_fuel
            time_cost += edge_time
            toll += edge_toll
        row["operating_cost_per_flow"] = fuel
        row["time_cost_per_flow"] = time_cost
        row["toll_cost_per_flow"] = toll
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("depth_key", type=int)
    parser.add_argument("event_key", type=int)
    parser.add_argument("--num-cpu", type=int, default=1)
    parser.add_argument("--sample-stride", type=int, default=1)
    parser.add_argument("--max-origins", type=int, default=0)
    parser.add_argument("--damaged-edge-csv", type=Path, default=None)
    parser.add_argument("--damaged-edge-sample", type=int, default=0)
    parser.add_argument("--out-path", type=Path, default=None)
    args = parser.parse_args()

    start = time.time()
    damaged_edges = load_damaged_edge_ids(
        args.depth_key,
        args.event_key,
        args.damaged_edge_csv,
        args.damaged_edge_sample,
    )
    if not damaged_edges:
        logging.info("No damaged edges found; writing empty disrupted OD file.")

    road_links, od, _ = load_baseline_inputs(args.sample_stride)
    network, road_links = func.create_igraph_network(road_links, vehicle_type="car")
    edge_eids = [str(eid) for eid in network.es["e_id"]]
    damaged_edge_idxs = {idx for idx, eid in enumerate(edge_eids) if eid in damaged_edges}
    edge_costs = {
        str(row.e_id): (
            float(row.operating_cost),
            float(row.time_cost),
            float(row.average_toll_cost),
        )
        for row in road_links[["e_id", "operating_cost", "time_cost", "average_toll_cost"]].itertuples(index=False)
    }

    path_args = build_args(od, args.max_origins)
    logging.info(
        "Option 5 prefilter: origins=%s, od_rows=%s, damaged_edges=%s, damaged_edge_idxs=%s",
        len(path_args),
        sum(len(a[1]) for a in path_args),
        len(damaged_edges),
        len(damaged_edge_idxs),
    )

    rows: list[dict] = []
    scanned = 0
    no_path_count = 0
    shared_network_pkl = pickle.dumps(network)
    path_start = time.time()
    if args.num_cpu > 1:
        with Pool(
            processes=args.num_cpu,
            initializer=func.worker_init_path,
            initargs=(shared_network_pkl,),
        ) as pool:
            for i, shortest_path in enumerate(pool.imap_unordered(func.find_least_cost_path, path_args), start=1):
                kept, chunk_scanned, chunk_no_path = filter_paths(
                    shortest_path, edge_eids, damaged_edge_idxs
                )
                rows.extend(kept)
                scanned += chunk_scanned
                no_path_count += chunk_no_path
                if i == 1 or i % 10 == 0 or i == len(path_args):
                    logging.info("Completed %s of %s origins; kept=%s", i, len(path_args), len(rows))
    else:
        func.shared_network = network
        for i, path_arg in enumerate(path_args, start=1):
            kept, chunk_scanned, chunk_no_path = filter_paths(
                func.find_least_cost_path(path_arg), edge_eids, damaged_edge_idxs
            )
            rows.extend(kept)
            scanned += chunk_scanned
            no_path_count += chunk_no_path
            if i == 1 or i % 10 == 0 or i == len(path_args):
                logging.info("Completed %s of %s origins; kept=%s", i, len(path_args), len(rows))

    logging.info("Shortest-path filtering time: %.3fs", time.time() - path_start)
    out_df = add_path_costs(rows, edge_costs)
    out_df = out_df[out_df["flow"] > 0].reset_index(drop=True)

    if args.out_path is None:
        args.out_path = (
            base_path.parent
            / "results"
            / "disruption_analysis"
            / get_results_variant()
            / "od"
            / f"odpfc_{args.depth_key}_{args.event_key}.pq"
        )
    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(args.out_path, index=False)
    logging.info(
        "Option 5 wrote %s rows to %s; scanned_od=%s, no_path=%s, total_time=%.3fs",
        len(out_df),
        args.out_path,
        scanned,
        no_path_count,
        time.time() - start,
    )
    gc.collect()


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(process)d %(filename)s %(levelname)s %(message)s",
        level=logging.INFO,
    )
    main()
