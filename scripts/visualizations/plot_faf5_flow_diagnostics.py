"""Generate FAF5 flow validation and commodity breakdown figures."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from viz_data_loaders import (
    build_flow_validation_table,
    format_usd_millions,
    load_assignment_od_demand,
    load_sctg_summary,
)


def _resolve_roots() -> tuple[Path, Path, Path]:
    input_root = Path(os.environ.get("NIRD_INPUT_ROOT", Path.cwd()))
    results_root = Path(os.environ["NIRD_RESULTS_ROOT"])
    variant = os.environ.get("NIRD_RESULTS_VARIANT", "revision")
    variant_root = results_root / "base_scenario" / variant
    fig_root = results_root / "figures" / variant / "step1_base"
    fig_root.mkdir(parents=True, exist_ok=True)
    return input_root, variant_root, fig_root


def ensure_sctg_summary(input_root: Path) -> None:
    summary_path = input_root / "census_datasets" / "faf5_sctg_daily_trucks.pq"
    if summary_path.exists():
        return
    repo_root = Path(__file__).resolve().parents[2]
    build_script = repo_root / "scripts" / "build_faf5_sctg_summary.py"
    subprocess.run([sys.executable, str(build_script)], check=True)


def plot_flow_validation(fig_dir: Path, input_root: Path, variant_root: Path) -> Path:
    table = build_flow_validation_table(input_root, variant_root)
    table.to_csv(fig_dir / "faf5_flow_validation.csv", index=False)

    plot_df = table[table["label"].str.contains("OD", na=False)].copy()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    labels = plot_df["label"].tolist()
    x = range(len(labels))
    colors = ["#4c78a8", "#54a24b", "#f58518"]
    axes[0].bar(x, plot_df["total_daily_trucks"], color=colors[: len(labels)])
    axes[0].set_xticks(list(x), labels, rotation=12, ha="right")
    axes[0].set_title("Total daily truck trips")
    axes[0].set_ylabel("Trucks / day")
    axes[0].grid(True, axis="y", alpha=0.2)

    axes[1].bar(x, plot_df["max_daily_trucks"], color=colors[: len(labels)])
    axes[1].set_xticks(list(x), labels, rotation=12, ha="right")
    axes[1].set_title("Largest OD pair (daily trucks)")
    axes[1].set_ylabel("Trucks / day")
    axes[1].grid(True, axis="y", alpha=0.2)

    fig.suptitle("FAF5 flow scale check (full assignment demand)", fontsize=13)
    fig.tight_layout()
    out = fig_dir / "faf5_flow_validation.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_sctg_breakdown(fig_dir: Path, input_root: Path) -> Path:
    ensure_sctg_summary(input_root)
    grouped, summary_source = load_sctg_summary(input_root)
    grouped.to_csv(fig_dir / "faf5_sctg_daily_trucks.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(grouped["industry"].iloc[::-1], grouped["daily_truck_trips"].iloc[::-1], color="#4c78a8")
    ax.set_xlabel("Daily truck trips")
    ax.set_title(f"FAF5 freight flows by industry ({summary_source.name})")
    ax.grid(True, axis="x", alpha=0.2)
    fig.tight_layout()
    out = fig_dir / "faf5_sctg_industry_breakdown.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_assignment_histogram(fig_dir: Path, input_root: Path) -> Path:
    demand, _ = load_assignment_od_demand(input_root)
    flows = pd.to_numeric(demand["flow"], errors="coerce").fillna(0.0)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(flows[flows > 0], bins=50, color="#4c78a8", edgecolor="white")
    ax.set_title("Full CONUS assignment OD demand")
    ax.set_xlabel("Daily truck trips per OD pair")
    ax.set_ylabel("Count")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    out = fig_dir / "faf5_full_od_flow_histogram.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> None:
    input_root, variant_root, fig_dir = _resolve_roots()
    print(f"Wrote {plot_flow_validation(fig_dir, input_root, variant_root)}")
    print(f"Wrote {plot_assignment_histogram(fig_dir, input_root)}")
    try:
        print(f"Wrote {plot_sctg_breakdown(fig_dir, input_root)}")
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        note = fig_dir / "faf5_sctg_breakdown_missing.txt"
        note.write_text(f"SCTG plot skipped: {exc}\n", encoding="utf-8")
        print(note.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    main()
