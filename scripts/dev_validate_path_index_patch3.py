"""Validate Patch 3 path-index artifacts against legacy full_odpfc output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd


ABS_TOL = 1e-4
REL_TOL = 1e-8


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def normalize_path(value) -> tuple[str, ...]:
    if value is None:
        return tuple()
    return tuple(str(v) for v in list(value))


def tolerance_ok(max_abs: float, ref_sum: float, abs_tol: float, rel_tol: float) -> bool:
    return max_abs <= max(abs_tol, rel_tol * max(abs(ref_sum), 1.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-dir", type=Path, required=True)
    parser.add_argument("--path-index-dir", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--damaged-edge-count", type=int, default=50)
    parser.add_argument("--abs-tol", type=float, default=ABS_TOL)
    parser.add_argument("--rel-tol", type=float, default=REL_TOL)
    args = parser.parse_args()

    legacy_path = args.legacy_dir / "odpfc.pq"
    meta_path = args.path_index_dir / "baseline_od_meta.pq"
    index_dir = args.path_index_dir / "baseline_path_index_parts"
    lookup_path = args.path_index_dir / "edge_lookup.pq"
    report = {
        "legacy_dir": str(args.legacy_dir),
        "path_index_dir": str(args.path_index_dir),
    }

    con = duckdb.connect()
    legacy_sql = sql_path(legacy_path)
    meta_sql = sql_path(meta_path)
    index_sql = sql_path(index_dir / "*.pq")
    lookup_sql = sql_path(lookup_path)

    reconstructed = con.execute(
        f"""
        SELECT
            m.*,
            p.path
        FROM read_parquet('{meta_sql}') m
        JOIN (
            SELECT
                p.od_id,
                LIST(e.e_id ORDER BY p.path_pos) AS path
            FROM read_parquet('{index_sql}') p
            JOIN read_parquet('{lookup_sql}') e USING (edge_idx)
            GROUP BY p.od_id
        ) p USING (od_id)
        """
    ).fetchdf()
    legacy = pd.read_parquet(legacy_path)
    for df in [legacy, reconstructed]:
        df["od_id"] = pd.to_numeric(df["od_id"], errors="raise").astype("int64")
        df["path_key"] = df["path"].apply(normalize_path)
    scalar_cols = [
        "flow",
        "operating_cost_per_flow",
        "time_cost_per_flow",
        "toll_cost_per_flow",
        "fare_cost_per_flow",
    ]
    if "length_mile" in reconstructed.columns:
        scalar_cols.append("length_mile")
    legacy_cols = {
        "origin_node": "origin_node",
        "destination_node": "destination_node",
        "flow": "flow",
        "operating_cost_per_flow": "operating_cost_per_flow",
        "time_cost_per_flow": "time_cost_per_flow",
        "toll_cost_per_flow": "toll_cost_per_flow",
        "fare_cost_per_flow": "fare_cost_per_flow",
        "path_key": "path_key",
        "od_id": "od_id",
    }
    legacy = legacy[list(legacy_cols)].copy()
    merged = legacy.merge(
        reconstructed,
        on="od_id",
        how="outer",
        suffixes=("_legacy", "_index"),
        indicator=True,
    )
    merge_counts = merged["_merge"].value_counts().to_dict()
    path_mismatch = int(
        (
            merged["path_key_legacy"].astype(str)
            != merged["path_key_index"].astype(str)
        ).sum()
    )
    scalar_diffs = {}
    checks = {
        "same_od_id_count": len(legacy) == len(reconstructed),
        "same_od_id_set": merge_counts.get("left_only", 0) == 0
        and merge_counts.get("right_only", 0) == 0,
        "same_reconstructed_paths": path_mismatch == 0,
    }
    for col in scalar_cols:
        legacy_col = f"{col}_legacy"
        index_col = f"{col}_index"
        if legacy_col not in merged or index_col not in merged:
            continue
        legacy_values = pd.to_numeric(merged[legacy_col], errors="coerce").fillna(0.0)
        index_values = pd.to_numeric(merged[index_col], errors="coerce").fillna(0.0)
        delta = (legacy_values - index_values).abs()
        max_abs = float(delta.max() if len(delta) else 0.0)
        sum_abs = float(delta.sum() if len(delta) else 0.0)
        scalar_diffs[col] = {"max_abs": max_abs, "sum_abs": sum_abs}
        checks[f"{col}_tolerance"] = tolerance_ok(
            max_abs, float(legacy_values.sum()), args.abs_tol, args.rel_tol
        )

    damaged_edges = con.execute(
        f"""
        SELECT DISTINCT e
        FROM read_parquet('{legacy_sql}'), UNNEST(path) AS u(e)
        LIMIT {int(args.damaged_edge_count)}
        """
    ).fetchdf()
    con.register("damaged_edges", damaged_edges)
    legacy_affected = con.execute(
        f"""
        SELECT
            od_id,
            LIST(u.e ORDER BY ord) AS flood_links
        FROM read_parquet('{legacy_sql}'),
        UNNEST(path) WITH ORDINALITY AS u(e, ord)
        JOIN damaged_edges d ON d.e = u.e
        GROUP BY od_id
        ORDER BY od_id
        """
    ).fetchdf()
    index_affected = con.execute(
        f"""
        WITH damaged_idx AS (
            SELECT edge_idx, e_id
            FROM read_parquet('{lookup_sql}') e
            JOIN damaged_edges d ON d.e = e.e_id
        )
        SELECT
            p.od_id,
            LIST(d.e_id ORDER BY p.path_pos) AS flood_links
        FROM read_parquet('{index_sql}') p
        JOIN damaged_idx d USING (edge_idx)
        GROUP BY p.od_id
        ORDER BY p.od_id
        """
    ).fetchdf()
    con.unregister("damaged_edges")
    con.close()
    for df in [legacy_affected, index_affected]:
        df["od_id"] = pd.to_numeric(df["od_id"], errors="raise").astype("int64")
        df["flood_key"] = df["flood_links"].apply(normalize_path)
    affected_merge = legacy_affected.merge(
        index_affected,
        on="od_id",
        how="outer",
        suffixes=("_legacy", "_index"),
        indicator=True,
    )
    affected_counts = affected_merge["_merge"].value_counts().to_dict()
    flood_mismatch = int(
        (
            affected_merge["flood_key_legacy"].astype(str)
            != affected_merge["flood_key_index"].astype(str)
        ).sum()
    )
    affected_legacy_ids = set(legacy_affected["od_id"].tolist())
    pre_cost_legacy = legacy.loc[legacy["od_id"].isin(affected_legacy_ids)].assign(
        total_cost=lambda df: df["flow"]
        * (
            df["operating_cost_per_flow"]
            + df["time_cost_per_flow"]
            + df["toll_cost_per_flow"]
            + df["fare_cost_per_flow"]
        )
    )["total_cost"].sum()
    reconstructed_affected = reconstructed[
        reconstructed["od_id"].isin(affected_legacy_ids)
    ].copy()
    pre_cost_index = (
        reconstructed_affected["flow"]
        * (
            reconstructed_affected["operating_cost_per_flow"]
            + reconstructed_affected["time_cost_per_flow"]
            + reconstructed_affected["toll_cost_per_flow"]
            + reconstructed_affected["fare_cost_per_flow"]
        )
    ).sum()
    checks.update(
        {
            "same_affected_od_ids": affected_counts.get("left_only", 0) == 0
            and affected_counts.get("right_only", 0) == 0,
            "same_flood_links": flood_mismatch == 0,
            "same_disrupted_candidate_count": len(legacy_affected)
            == len(index_affected),
            "pre_event_cost_tolerance": tolerance_ok(
                abs(float(pre_cost_legacy) - float(pre_cost_index)),
                float(pre_cost_legacy),
                args.abs_tol,
                args.rel_tol,
            ),
        }
    )
    report.update(
        {
            "legacy_rows": int(len(legacy)),
            "reconstructed_rows": int(len(reconstructed)),
            "od_id_merge_counts": merge_counts,
            "path_mismatch_count": path_mismatch,
            "scalar_diffs": scalar_diffs,
            "damaged_edge_count": int(len(damaged_edges)),
            "affected_legacy_count": int(len(legacy_affected)),
            "affected_index_count": int(len(index_affected)),
            "affected_merge_counts": affected_counts,
            "flood_link_mismatch_count": flood_mismatch,
            "pre_event_cost_legacy": float(pre_cost_legacy),
            "pre_event_cost_index": float(pre_cost_index),
            "checks": checks,
            "passed": all(checks.values()),
        }
    )
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
