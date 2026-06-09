"""Validate Patch 5 fused event candidates against Patch 4 event candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd


ABS_TOL = 1e-4
REL_TOL = 1e-8


def safe_event_id(value) -> str:
    text = str(value).strip() if value is not None else "event_000001"
    if not text:
        text = "event_000001"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def normalize_path(value) -> tuple[str, ...]:
    if value is None:
        return tuple()
    return tuple(str(v) for v in list(value))


def tolerance_ok(max_abs: float, ref_sum: float, abs_tol: float, rel_tol: float) -> bool:
    return max_abs <= max(abs_tol, rel_tol * max(abs(ref_sum), 1.0))


def load_candidates(base_dir: Path, event_id: str) -> pd.DataFrame:
    root = base_dir / "event_disrupted_candidates" / safe_event_id(event_id)
    combined = root / "disrupted_candidates.pq"
    parts = root / "parts"
    if combined.exists():
        return pd.read_parquet(combined)
    if parts.exists() and any(parts.glob("*.pq")):
        files = [sql_path(p) for p in sorted(parts.glob("*.pq"))]
        con = duckdb.connect()
        try:
            return con.execute(
                "SELECT * FROM read_parquet(?)",
                [files],
            ).fetchdf()
        finally:
            con.close()
    raise FileNotFoundError(f"Missing candidates under {root}")


def summarize_parts(base_dir: Path, event_id: str) -> dict:
    parts = base_dir / "event_disrupted_candidates" / safe_event_id(event_id) / "parts"
    files = sorted(parts.glob("*.pq")) if parts.exists() else []
    return {
        "part_count": len(files),
        "part_bytes": int(sum(p.stat().st_size for p in files)),
    }


def edge_flow_frame(path: Path) -> pd.DataFrame:
    df = gpd.read_parquet(path)
    keep = [c for c in ["e_id", "acc_flow", "acc_capacity", "acc_speed"] if c in df.columns]
    out = pd.DataFrame(df[keep]).copy()
    out["e_id"] = out["e_id"].astype(str)
    return out.sort_values("e_id").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch4-dir", type=Path, required=True)
    parser.add_argument("--patch5-dir", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--abs-tol", type=float, default=ABS_TOL)
    parser.add_argument("--rel-tol", type=float, default=REL_TOL)
    args = parser.parse_args()

    patch4 = load_candidates(args.patch4_dir, args.event_id)
    patch5 = load_candidates(args.patch5_dir, args.event_id)
    for df in [patch4, patch5]:
        df["od_id"] = pd.to_numeric(df["od_id"], errors="raise").astype("int64")
        df["path_key"] = df["path"].apply(normalize_path)
        df["flood_key"] = df["flood_links"].apply(normalize_path)

    compare_cols = [
        "od_id",
        "origin_node",
        "destination_node",
        "flow",
        "operating_cost_per_flow",
        "time_cost_per_flow",
        "toll_cost_per_flow",
        "fare_cost_per_flow",
        "length_mile",
        "path_key",
        "flood_key",
    ]
    merged = patch4[compare_cols].merge(
        patch5[compare_cols],
        on="od_id",
        how="outer",
        suffixes=("_patch4", "_patch5"),
        indicator=True,
    )
    merge_counts = merged["_merge"].value_counts().to_dict()
    path_mismatch = int(
        (merged["path_key_patch4"].astype(str) != merged["path_key_patch5"].astype(str)).sum()
    )
    flood_mismatch = int(
        (merged["flood_key_patch4"].astype(str) != merged["flood_key_patch5"].astype(str)).sum()
    )

    scalar_cols = [
        "flow",
        "operating_cost_per_flow",
        "time_cost_per_flow",
        "toll_cost_per_flow",
        "fare_cost_per_flow",
        "length_mile",
    ]
    scalar_diffs = {}
    checks = {
        "same_candidate_count": len(patch4) == len(patch5),
        "same_od_id_set": merge_counts.get("left_only", 0) == 0
        and merge_counts.get("right_only", 0) == 0,
        "same_paths": path_mismatch == 0,
        "same_flood_links": flood_mismatch == 0,
    }
    for col in scalar_cols:
        ref = pd.to_numeric(merged[f"{col}_patch4"], errors="coerce").fillna(0.0)
        new = pd.to_numeric(merged[f"{col}_patch5"], errors="coerce").fillna(0.0)
        delta = (ref - new).abs()
        max_abs = float(delta.max() if len(delta) else 0.0)
        sum_abs = float(delta.sum() if len(delta) else 0.0)
        scalar_diffs[col] = {"max_abs": max_abs, "sum_abs": sum_abs}
        checks[f"{col}_tolerance"] = tolerance_ok(
            max_abs, float(ref.sum()), args.abs_tol, args.rel_tol
        )

    pre_cost4 = (
        patch4["flow"]
        * (
            patch4["operating_cost_per_flow"]
            + patch4["time_cost_per_flow"]
            + patch4["toll_cost_per_flow"]
            + patch4["fare_cost_per_flow"]
        )
    ).sum()
    pre_cost5 = (
        patch5["flow"]
        * (
            patch5["operating_cost_per_flow"]
            + patch5["time_cost_per_flow"]
            + patch5["toll_cost_per_flow"]
            + patch5["fare_cost_per_flow"]
        )
    ).sum()
    checks["pre_event_cost_tolerance"] = tolerance_ok(
        abs(float(pre_cost4) - float(pre_cost5)),
        float(pre_cost4),
        args.abs_tol,
        args.rel_tol,
    )

    edge4 = edge_flow_frame(args.patch4_dir / "edge_flows.gpq")
    edge5 = edge_flow_frame(args.patch5_dir / "edge_flows.gpq")
    edge = edge4.merge(edge5, on="e_id", how="outer", suffixes=("_patch4", "_patch5"), indicator=True)
    edge_counts = edge["_merge"].value_counts().to_dict()
    checks["same_edge_ids"] = edge_counts.get("left_only", 0) == 0 and edge_counts.get("right_only", 0) == 0
    edge_diffs = {}
    for col in ["acc_flow", "acc_capacity", "acc_speed"]:
        ref_col = f"{col}_patch4"
        new_col = f"{col}_patch5"
        if ref_col not in edge.columns or new_col not in edge.columns:
            continue
        ref = pd.to_numeric(edge[ref_col], errors="coerce").fillna(0.0)
        new = pd.to_numeric(edge[new_col], errors="coerce").fillna(0.0)
        delta = (ref - new).abs()
        max_abs = float(delta.max() if len(delta) else 0.0)
        sum_abs = float(delta.sum() if len(delta) else 0.0)
        edge_diffs[col] = {"max_abs": max_abs, "sum_abs": sum_abs}
        checks[f"edge_{col}_tolerance"] = tolerance_ok(
            max_abs, float(ref.sum()), args.abs_tol, args.rel_tol
        )

    report = {
        "patch4_dir": str(args.patch4_dir),
        "patch5_dir": str(args.patch5_dir),
        "event_id": safe_event_id(args.event_id),
        "patch4_candidate_rows": int(len(patch4)),
        "patch5_candidate_rows": int(len(patch5)),
        "candidate_merge_counts": merge_counts,
        "path_mismatch_count": path_mismatch,
        "flood_link_mismatch_count": flood_mismatch,
        "scalar_diffs": scalar_diffs,
        "pre_event_cost_patch4": float(pre_cost4),
        "pre_event_cost_patch5": float(pre_cost5),
        "patch4_parts": summarize_parts(args.patch4_dir, args.event_id),
        "patch5_parts": summarize_parts(args.patch5_dir, args.event_id),
        "edge_merge_counts": edge_counts,
        "edge_diffs": edge_diffs,
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
