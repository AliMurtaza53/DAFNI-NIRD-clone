"""Validate Patch 2 OD path output modes.

Compares a legacy ``duckdb_table`` output directory against an
``iteration_parquet`` output directory. The script expects combined ``odpfc.pq``
files for the detailed row comparison and also reports partition counts for the
iteration-parquet directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd


ABS_TOL = 1e-4
REL_TOL = 1e-8


def normalize_path(value) -> tuple[str, ...]:
    if value is None:
        return tuple()
    if isinstance(value, str):
        return tuple(tok.strip() for tok in value.strip("[]").split(",") if tok.strip())
    return tuple(str(v) for v in list(value))


def read_odpfc(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["origin_node"] = df["origin_node"].astype(str)
    df["destination_node"] = df["destination_node"].astype(str)
    df["path_key"] = df["path"].apply(normalize_path)
    for col in [
        "flow",
        "operating_cost_per_flow",
        "time_cost_per_flow",
        "toll_cost_per_flow",
        "fare_cost_per_flow",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def count_parts(parts_dir: Path) -> tuple[int, int]:
    part_files = sorted(parts_dir.glob("*.pq")) if parts_dir.exists() else []
    if not part_files:
        return 0, 0
    pattern = (parts_dir / "*.pq").as_posix().replace("'", "''")
    row_count = duckdb.connect().execute(
        f"SELECT COUNT(*) FROM read_parquet('{pattern}')"
    ).fetchone()[0]
    return len(part_files), int(row_count)


def tolerance_ok(max_abs: float, ref_sum: float, abs_tol: float, rel_tol: float) -> bool:
    return max_abs <= max(abs_tol, rel_tol * max(abs(ref_sum), 1.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duckdb-dir", type=Path, required=True)
    parser.add_argument("--iteration-dir", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--abs-tol", type=float, default=ABS_TOL)
    parser.add_argument("--rel-tol", type=float, default=REL_TOL)
    args = parser.parse_args()

    duckdb_od = read_odpfc(args.duckdb_dir / "odpfc.pq")
    iter_od = read_odpfc(args.iteration_dir / "odpfc.pq")
    part_count, part_rows = count_parts(args.iteration_dir / "odpfc_parts")

    key_cols = ["origin_node", "destination_node", "path_key"]
    merged = duckdb_od.merge(
        iter_od,
        on=key_cols,
        how="outer",
        suffixes=("_duckdb", "_iteration"),
        indicator=True,
    )
    merge_counts = merged["_merge"].value_counts().to_dict()
    numeric_cols = [
        "flow",
        "operating_cost_per_flow",
        "time_cost_per_flow",
        "toll_cost_per_flow",
        "fare_cost_per_flow",
    ]
    numeric_diffs = {}
    checks = {
        "same_row_count": len(duckdb_od) == len(iter_od),
        "same_key_set": merge_counts.get("left_only", 0) == 0
        and merge_counts.get("right_only", 0) == 0,
        "iteration_parts_exist": part_count > 0,
        "iteration_part_rows_positive": part_rows > 0,
    }
    for col in numeric_cols:
        delta = (merged[f"{col}_duckdb"] - merged[f"{col}_iteration"]).abs()
        max_abs = float(delta.max() if len(delta) else 0.0)
        sum_abs = float(delta.sum() if len(delta) else 0.0)
        numeric_diffs[col] = {"max_abs": max_abs, "sum_abs": sum_abs}
        checks[f"{col}_tolerance"] = tolerance_ok(
            max_abs,
            float(duckdb_od[col].sum()),
            args.abs_tol,
            args.rel_tol,
        )

    report = {
        "duckdb_dir": str(args.duckdb_dir),
        "iteration_dir": str(args.iteration_dir),
        "duckdb_rows": int(len(duckdb_od)),
        "iteration_rows": int(len(iter_od)),
        "iteration_part_count": part_count,
        "iteration_part_rows": part_rows,
        "key_merge_counts": merge_counts,
        "numeric_diffs": numeric_diffs,
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
