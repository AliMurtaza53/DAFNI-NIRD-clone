"""Compare legacy vs streaming path realization on controlled OD samples.

This is a development harness. It does not run the full assignment loop; it
builds the same compact ``temp_flow_matrix_input`` table used inside one
assignment iteration, realizes paths with one strategy, and writes comparable
Parquet outputs. Use ``--compare`` after running legacy and streaming samples.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import duckdb
import geopandas as gpd
import pandas as pd

import nird.road_revised as func
from nird.utils import load_config


base_path = Path(load_config()["paths"]["soge_clusters"])
ABS_TOL = 1e-4
REL_TOL = 1e-8


def first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def sql_path(path: Path) -> str:
    """Return a DuckDB-safe single-quoted path body."""
    return path.resolve().as_posix().replace("'", "''")


def load_network_inputs():
    params_root = first_existing(
        [base_path / "parameters", base_path / "inputs" / "parameters"]
    )
    if params_root is None:
        raise FileNotFoundError("Could not find parameter folder")

    flow_breakpoint_dict = json.loads(
        (params_root / "flow_breakpoint_dict.json").read_text()
    )
    flow_capacity_dict = json.loads((params_root / "flow_cap_plph_dict.json").read_text())
    free_flow_speed_dict = json.loads(
        (params_root / "free_flow_speed_dict.json").read_text()
    )
    min_speed_dict = json.loads((params_root / "min_speed_cap.json").read_text())
    urban_speed_dict = json.loads((params_root / "urban_speed_cap.json").read_text())

    road_links_path = first_existing(
        [
            base_path / "networks" / "faf5" / "faf5_road_links.gpq",
            base_path / "inputs" / "networks" / "faf5" / "faf5_road_links.gpq",
        ]
    )
    if road_links_path is None:
        raise FileNotFoundError("Could not find faf5_road_links.gpq")
    road_links = gpd.read_parquet(road_links_path)
    road_links = func.edge_init(
        road_links,
        flow_breakpoint_dict,
        flow_capacity_dict,
        free_flow_speed_dict,
        urban_speed_dict,
        min_speed_dict,
        max_flow_speed_dict=None,
    )
    network, road_links = func.create_igraph_network(road_links, vehicle_type="car")
    return network, road_links


def load_sample_od(sample_n: int) -> pd.DataFrame:
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
    flow_col = "Car21" if "Car21" in od.columns else "flow"
    od[flow_col] = pd.to_numeric(od[flow_col], errors="coerce").fillna(0.0)
    od = od[(od[flow_col] > 0) & (od["origin_node"] != od["destination_node"])].copy()
    od = od.head(sample_n).rename(columns={flow_col: "Car21"})
    return od[["origin_node", "destination_node", "Car21"]].reset_index(drop=True)


def build_path_rows(network, od: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_dtype = type(network.vs["name"][0])
    od["origin_node"] = pd.to_numeric(od["origin_node"], errors="raise").astype(
        node_dtype
    )
    od["destination_node"] = pd.to_numeric(
        od["destination_node"], errors="raise"
    ).astype(node_dtype)
    valid_nodes = set(network.vs["name"])
    invalid = od[
        (~od["origin_node"].isin(valid_nodes))
        | (~od["destination_node"].isin(valid_nodes))
    ][["origin_node", "destination_node", "Car21"]].rename(columns={"Car21": "flow"})
    od = od.drop(invalid.index, errors="ignore")

    rows = []
    isolated = []
    grouped = (
        od.groupby("origin_node", as_index=False)
        .agg(destination_node=("destination_node", list), Car21=("Car21", list))
        .sort_values("origin_node")
    )
    for origin, destinations, flows in grouped.itertuples(index=False):
        paths = network.get_shortest_paths(
            v=origin,
            to=destinations,
            weights="weight",
            mode="out",
            output="epath",
        )
        for dest, path, flow in zip(destinations, paths, flows):
            if path:
                rows.append((str(origin), str(dest), path, float(flow)))
            else:
                isolated.append((str(origin), str(dest), float(flow)))

    path_df = pd.DataFrame(rows, columns=["origin", "destination", "path", "flow"])
    isolated_df = pd.concat(
        [
            invalid,
            pd.DataFrame(isolated, columns=["origin_node", "destination_node", "flow"]),
        ],
        ignore_index=True,
    )
    return path_df, isolated_df


def run_strategy(args: argparse.Namespace) -> None:
    out_dir = args.out_dir or Path("results/dev") / f"path_realization_{args.strategy}_{args.sample_n}"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "path_realization.duckdb"
    if db_path.exists():
        db_path.unlink()

    start = time.time()
    network, road_links = load_network_inputs()
    od = load_sample_od(args.sample_n)
    path_df, isolated_df = build_path_rows(network, od)

    conn = duckdb.connect(str(db_path))
    conn.register("path_input_df", path_df)
    conn.execute("CREATE TABLE temp_flow_matrix_input AS SELECT * FROM path_input_df")
    conn.unregister("path_input_df")

    old_strategy = os.environ.get("NIRD_PATH_REALIZATION_STRATEGY")
    os.environ["NIRD_PATH_REALIZATION_STRATEGY"] = args.strategy
    try:
        func.itter_path(
            network,
            road_links,
            temp_flow_matrix=None,
            num_of_chunk=args.num_chunks,
            db_path=str(db_path),
            conn=conn,
            temp_flow_table="temp_flow_matrix_input",
        )
    finally:
        if old_strategy is None:
            os.environ.pop("NIRD_PATH_REALIZATION_STRATEGY", None)
        else:
            os.environ["NIRD_PATH_REALIZATION_STRATEGY"] = old_strategy

    conn.execute(
        f"COPY (SELECT * FROM temp_flow_matrix) TO '{sql_path(out_dir / 'temp_flow_matrix.pq')}' (FORMAT PARQUET)"
    )
    if args.strategy == "streaming_arrays":
        conn.execute(
            f"COPY (SELECT e_id, flow FROM temp_edge_flow WHERE flow > 0) TO '{sql_path(out_dir / 'temp_edge_flow.pq')}' (FORMAT PARQUET)"
        )
    else:
        conn.execute(
            f"""
            COPY (
                SELECT e AS e_id, SUM(flow) AS flow
                FROM (
                    SELECT flow, UNNEST(e_id) AS e
                    FROM temp_flow_matrix
                ) AS t
                GROUP BY e
            ) TO '{sql_path(out_dir / 'temp_edge_flow.pq')}' (FORMAT PARQUET)
            """
        )
    path_df.to_parquet(out_dir / "temp_flow_matrix_input.pq", index=False)
    isolated_df.to_parquet(out_dir / "isolated_paths.pq", index=False)
    summary = {
        "strategy": args.strategy,
        "sample_n": args.sample_n,
        "input_od_rows": int(len(od)),
        "valid_path_rows": int(len(path_df)),
        "isolated_rows": int(len(isolated_df)),
        "elapsed_seconds": time.time() - start,
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    conn.close()
    logging.info("Wrote strategy outputs: %s", out_dir)


def normalize_path(value):
    if value is None:
        return tuple()
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    if not hasattr(value, "__iter__") and pd.isna(value):
        return tuple()
    return tuple(str(v) for v in list(value))


def tolerance_ok(max_abs: float, ref_sum: float, abs_tol: float, rel_tol: float) -> bool:
    return max_abs <= max(abs_tol, rel_tol * max(abs(ref_sum), 1.0))


def compare_outputs(args: argparse.Namespace) -> None:
    legacy_dir = args.legacy_dir
    streaming_dir = args.streaming_dir
    report_dir = args.report_dir or Path("results/dev")
    report_dir.mkdir(parents=True, exist_ok=True)

    legacy_od = pd.read_parquet(legacy_dir / "temp_flow_matrix.pq")
    streaming_od = pd.read_parquet(streaming_dir / "temp_flow_matrix.pq")
    legacy_edge = pd.read_parquet(legacy_dir / "temp_edge_flow.pq")
    streaming_edge = pd.read_parquet(streaming_dir / "temp_edge_flow.pq")

    for df in [legacy_od, streaming_od]:
        df["origin"] = df["origin"].astype(str)
        df["destination"] = df["destination"].astype(str)
        df["path_key"] = df["e_id"].apply(normalize_path)

    key_cols = ["origin", "destination"]
    merged_od = legacy_od.merge(
        streaming_od,
        on=key_cols,
        suffixes=("_legacy", "_streaming"),
        how="outer",
        indicator=True,
    )
    numeric_cols = ["flow", "fuel", "time", "toll", "length_mile"]
    diffs = {}
    for col in numeric_cols:
        delta = (merged_od[f"{col}_legacy"] - merged_od[f"{col}_streaming"]).abs()
        diffs[col] = {
            "max_abs": float(delta.max() if len(delta) else 0.0),
            "sum_abs": float(delta.sum() if len(delta) else 0.0),
        }

    path_mismatch = int(
        (
            merged_od["path_key_legacy"].astype(str)
            != merged_od["path_key_streaming"].astype(str)
        ).sum()
    )

    legacy_edge["e_id"] = legacy_edge["e_id"].astype(str)
    streaming_edge["e_id"] = streaming_edge["e_id"].astype(str)
    merged_edge = legacy_edge.merge(
        streaming_edge,
        on="e_id",
        suffixes=("_legacy", "_streaming"),
        how="outer",
        indicator=True,
    ).fillna({"flow_legacy": 0.0, "flow_streaming": 0.0})
    edge_abs = (merged_edge["flow_legacy"] - merged_edge["flow_streaming"]).abs()
    edge_flow_max_abs = float(edge_abs.max() if len(edge_abs) else 0.0)
    edge_flow_sum_abs = float(edge_abs.sum() if len(edge_abs) else 0.0)
    od_key_counts = merged_od["_merge"].value_counts().to_dict()
    edge_key_counts = merged_edge["_merge"].value_counts().to_dict()
    assigned_legacy = float(legacy_od["flow"].sum())
    assigned_streaming = float(streaming_od["flow"].sum())
    input_legacy = pd.read_parquet(legacy_dir / "temp_flow_matrix_input.pq")
    input_streaming = pd.read_parquet(streaming_dir / "temp_flow_matrix_input.pq")
    input_flow_legacy = float(input_legacy["flow"].sum())
    input_flow_streaming = float(input_streaming["flow"].sum())

    checks = {
        "same_od_row_count": len(legacy_od) == len(streaming_od),
        "same_od_key_set": od_key_counts.get("left_only", 0) == 0
        and od_key_counts.get("right_only", 0) == 0,
        "same_ordered_paths": path_mismatch == 0,
        "same_edge_key_set": edge_key_counts.get("left_only", 0) == 0
        and edge_key_counts.get("right_only", 0) == 0,
        "edge_flow_tolerance": tolerance_ok(
            edge_flow_max_abs, assigned_legacy, args.abs_tol, args.rel_tol
        ),
        "assigned_flow_tolerance": tolerance_ok(
            abs(assigned_legacy - assigned_streaming),
            assigned_legacy,
            args.abs_tol,
            args.rel_tol,
        ),
        "same_input_flow": tolerance_ok(
            abs(input_flow_legacy - input_flow_streaming),
            input_flow_legacy,
            args.abs_tol,
            args.rel_tol,
        ),
    }
    for col, values in diffs.items():
        checks[f"od_{col}_tolerance"] = tolerance_ok(
            values["max_abs"],
            float(legacy_od[col].sum()) if col in legacy_od else 0.0,
            args.abs_tol,
            args.rel_tol,
        )

    report = {
        "legacy_dir": str(legacy_dir),
        "streaming_dir": str(streaming_dir),
        "od_rows_legacy": int(len(legacy_od)),
        "od_rows_streaming": int(len(streaming_od)),
        "od_key_merge_counts": od_key_counts,
        "path_mismatch_count": path_mismatch,
        "od_numeric_diffs": diffs,
        "edge_rows_legacy": int(len(legacy_edge)),
        "edge_rows_streaming": int(len(streaming_edge)),
        "edge_key_merge_counts": edge_key_counts,
        "edge_flow_max_abs": edge_flow_max_abs,
        "edge_flow_sum_abs": edge_flow_sum_abs,
        "legacy_input_flow_sum": input_flow_legacy,
        "streaming_input_flow_sum": input_flow_streaming,
        "legacy_assigned_flow_sum": assigned_legacy,
        "streaming_assigned_flow_sum": assigned_streaming,
        "legacy_remaining_candidate_flow_sum": input_flow_legacy - assigned_legacy,
        "streaming_remaining_candidate_flow_sum": input_flow_streaming - assigned_streaming,
        "abs_tol": args.abs_tol,
        "rel_tol": args.rel_tol,
        "checks": checks,
        "passed": all(checks.values()),
    }
    sample_n = args.sample_n or report["od_rows_legacy"]
    json_path = report_dir / f"path_realization_comparison_{sample_n}.json"
    csv_path = report_dir / f"path_realization_comparison_{sample_n}_edge_diffs.csv"
    json_path.write_text(json.dumps(report, indent=2))
    merged_edge.assign(abs_diff=edge_abs).sort_values("abs_diff", ascending=False).head(
        1000
    ).to_csv(csv_path, index=False)
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["legacy_compact_sql", "streaming_arrays"])
    parser.add_argument("--sample-n", type=int, default=1000)
    parser.add_argument("--num-chunks", type=int, default=20)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--legacy-dir", type=Path)
    parser.add_argument("--streaming-dir", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--abs-tol", type=float, default=ABS_TOL)
    parser.add_argument("--rel-tol", type=float, default=REL_TOL)
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(process)d %(filename)s %(levelname)s %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )
    if args.compare:
        if args.legacy_dir is None or args.streaming_dir is None:
            raise ValueError("--compare requires --legacy-dir and --streaming-dir")
        compare_outputs(args)
    else:
        if args.strategy is None:
            raise ValueError("--strategy is required unless --compare is used")
        run_strategy(args)


if __name__ == "__main__":
    main()
