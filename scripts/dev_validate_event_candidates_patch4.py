"""Validate Patch 4 event-filtered candidates against legacy full odpfc."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
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


def load_event_candidates(event_dir: Path, event_id: str) -> pd.DataFrame:
    root = event_dir / "event_disrupted_candidates" / safe_event_id(event_id)
    combined = root / "disrupted_candidates.pq"
    parts = root / "parts"
    if combined.exists():
        return pd.read_parquet(combined)
    if parts.exists() and any(parts.glob("*.pq")):
        con = duckdb.connect()
        try:
            return con.execute(
                f"SELECT * FROM read_parquet('{sql_path(parts / '*.pq')}')"
            ).fetchdf()
        finally:
            con.close()
    raise FileNotFoundError(f"Missing event candidates under {root}")


def load_damaged_edges(path: Path, event_id: str) -> set[str]:
    if path.suffix.lower() in {".pq", ".parquet"}:
        damaged = pd.read_parquet(path)
    else:
        damaged = pd.read_csv(path)
    if "e_id" not in damaged.columns:
        raise ValueError("Damaged-edge file must contain e_id")
    if "event_id" in damaged.columns:
        damaged = damaged[damaged["event_id"].map(safe_event_id) == safe_event_id(event_id)]
    return set(damaged["e_id"].astype(str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-dir", type=Path, required=True)
    parser.add_argument("--event-dir", type=Path, required=True)
    parser.add_argument("--damaged-edges-path", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--abs-tol", type=float, default=ABS_TOL)
    parser.add_argument("--rel-tol", type=float, default=REL_TOL)
    args = parser.parse_args()

    legacy_path = args.legacy_dir / "odpfc.pq"
    legacy = pd.read_parquet(legacy_path)
    event_candidates = load_event_candidates(args.event_dir, args.event_id)
    damaged_edges = load_damaged_edges(args.damaged_edges_path, args.event_id)

    for df in [legacy, event_candidates]:
        df["od_id"] = pd.to_numeric(df["od_id"], errors="raise").astype("int64")
        df["path_key"] = df["path"].apply(normalize_path)

    legacy["flood_links"] = legacy["path_key"].apply(
        lambda path: tuple(edge for edge in path if edge in damaged_edges)
    )
    legacy_ref = legacy[legacy["flood_links"].map(len) > 0].copy()
    legacy_ref["flood_key"] = legacy_ref["flood_links"]
    event_candidates["flood_key"] = event_candidates["flood_links"].apply(normalize_path)

    compare_cols = [
        "od_id",
        "origin_node",
        "destination_node",
        "flow",
        "operating_cost_per_flow",
        "time_cost_per_flow",
        "toll_cost_per_flow",
        "fare_cost_per_flow",
        "path_key",
        "flood_key",
    ]
    if "length_mile" in event_candidates.columns and "length_mile" in legacy_ref.columns:
        compare_cols.insert(-2, "length_mile")

    merged = legacy_ref[compare_cols].merge(
        event_candidates[compare_cols],
        on="od_id",
        how="outer",
        suffixes=("_legacy", "_event"),
        indicator=True,
    )
    merge_counts = merged["_merge"].value_counts().to_dict()
    path_mismatch = int(
        (merged["path_key_legacy"].astype(str) != merged["path_key_event"].astype(str)).sum()
    )
    flood_mismatch = int(
        (merged["flood_key_legacy"].astype(str) != merged["flood_key_event"].astype(str)).sum()
    )
    scalar_cols = [
        "flow",
        "operating_cost_per_flow",
        "time_cost_per_flow",
        "toll_cost_per_flow",
        "fare_cost_per_flow",
    ]
    if "length_mile_legacy" in merged.columns:
        scalar_cols.append("length_mile")
    scalar_diffs = {}
    checks = {
        "same_affected_od_ids": merge_counts.get("left_only", 0) == 0
        and merge_counts.get("right_only", 0) == 0,
        "same_candidate_count": len(legacy_ref) == len(event_candidates),
        "same_paths": path_mismatch == 0,
        "same_flood_links": flood_mismatch == 0,
    }
    for col in scalar_cols:
        legacy_col = f"{col}_legacy"
        event_col = f"{col}_event"
        legacy_values = pd.to_numeric(merged[legacy_col], errors="coerce").fillna(0.0)
        event_values = pd.to_numeric(merged[event_col], errors="coerce").fillna(0.0)
        delta = (legacy_values - event_values).abs()
        max_abs = float(delta.max() if len(delta) else 0.0)
        sum_abs = float(delta.sum() if len(delta) else 0.0)
        scalar_diffs[col] = {"max_abs": max_abs, "sum_abs": sum_abs}
        checks[f"{col}_tolerance"] = tolerance_ok(
            max_abs, float(legacy_values.sum()), args.abs_tol, args.rel_tol
        )

    pre_cost_legacy = (
        legacy_ref["flow"]
        * (
            legacy_ref["operating_cost_per_flow"]
            + legacy_ref["time_cost_per_flow"]
            + legacy_ref["toll_cost_per_flow"]
            + legacy_ref["fare_cost_per_flow"]
        )
    ).sum()
    pre_cost_event = (
        event_candidates["flow"]
        * (
            event_candidates["operating_cost_per_flow"]
            + event_candidates["time_cost_per_flow"]
            + event_candidates["toll_cost_per_flow"]
            + event_candidates["fare_cost_per_flow"]
        )
    ).sum()
    checks["pre_event_cost_tolerance"] = tolerance_ok(
        abs(float(pre_cost_legacy) - float(pre_cost_event)),
        float(pre_cost_legacy),
        args.abs_tol,
        args.rel_tol,
    )

    report = {
        "legacy_dir": str(args.legacy_dir),
        "event_dir": str(args.event_dir),
        "damaged_edges_path": str(args.damaged_edges_path),
        "event_id": safe_event_id(args.event_id),
        "damaged_edge_count": len(damaged_edges),
        "legacy_rows": int(len(legacy)),
        "legacy_affected_rows": int(len(legacy_ref)),
        "event_candidate_rows": int(len(event_candidates)),
        "merge_counts": merge_counts,
        "path_mismatch_count": path_mismatch,
        "flood_link_mismatch_count": flood_mismatch,
        "scalar_diffs": scalar_diffs,
        "pre_event_cost_legacy": float(pre_cost_legacy),
        "pre_event_cost_event": float(pre_cost_event),
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
