"""Generate step 2/3 draft figures from existing disruption and damage outputs."""

from __future__ import annotations

import os
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from viz_data_loaders import format_usd_millions, prepare_damage_for_viz


def _roots() -> tuple[Path, Path]:
    input_root = Path(os.environ.get("NIRD_INPUT_ROOT", Path.cwd()))
    results_root = Path(os.environ["NIRD_RESULTS_ROOT"])
    variant = os.environ.get("NIRD_RESULTS_VARIANT", "revision")
    depth = os.environ.get("NIRD_DEPTH_KEY", "30")
    fig_root = results_root / "figures" / variant
    disruption_root = results_root / "disruption_analysis" / variant / depth
    damage_root = results_root / "damage_analysis" / variant
    return fig_root, disruption_root, damage_root


def plot_disruption_summary(disruption_root: Path, fig_dir: Path) -> Path | None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    links_dir = disruption_root / "links"
    if not links_dir.is_dir():
        return None

    event_keys = sorted(p.stem.replace("road_links_", "") for p in links_dir.glob("road_links_*.gpq"))
    if not event_keys:
        return None

    fig, axes = plt.subplots(1, len(event_keys), figsize=(5 * len(event_keys), 4), squeeze=False)
    for idx, event_key in enumerate(event_keys):
        links = gpd.read_parquet(links_dir / f"road_links_{event_key}.gpq")
        flood_col = "flood_depth_max" if "flood_depth_max" in links.columns else None
        if flood_col is None:
            flood_col = next((c for c in links.columns if str(c).startswith("flood_depth")), None)
        ax = axes[0, idx]
        if flood_col:
            vals = pd.to_numeric(links[flood_col], errors="coerce").fillna(0.0)
            vals[vals > 0].plot(kind="hist", bins=30, color="#9e77c9", edgecolor="white", ax=ax)
            ax.set_title(f"Event {event_key}: flooded link depths")
            ax.set_xlabel("Flood depth (cm)")
        else:
            ax.text(0.5, 0.5, "No flood depth column", ha="center", va="center", transform=ax.transAxes)
        ax.set_ylabel("Link count")
        ax.grid(True, alpha=0.2)

    fig.suptitle("Step 2 draft: toy hazard disruption (CONUS network)", fontsize=13)
    fig.tight_layout()
    out = fig_dir / "step2_disruption" / "step2_disruption_summary_draft.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_damage_summary(damage_root: Path, fig_dir: Path) -> Path | None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    summary_path = damage_root / "damage_summary.csv"
    if not summary_path.exists():
        return None

    summary = pd.read_csv(summary_path)
    value_col = "damage_cost_mean_musd" if "damage_cost_mean_musd" in summary.columns else "damage_cost_mean"
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(summary))
    ax.bar(x, summary[value_col], color="#e45756", edgecolor="white")
    ax.set_xticks(list(x), [f"Event {eid}" for eid in summary["event_id"]])
    ax.set_ylabel("Direct damage (MUSD)")
    ax.set_title("Step 3 draft: direct flood damage by toy hazard event")
    for i, val in enumerate(summary[value_col]):
        ax.text(i, val, format_usd_millions(float(val) * 1_000_000), ha="center", va="bottom", fontsize=9)
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    out = fig_dir / "step3_damage" / "step3_damage_summary_draft.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_damage_detail(damage_root: Path, fig_dir: Path) -> Path | None:
    csv_paths = sorted(damage_root.glob("intersections_*_with_damage_values.csv"))
    if not csv_paths:
        return None

    totals: list[tuple[str, float]] = []
    for path in csv_paths:
        event_id = path.stem.split("_")[1]
        damage = prepare_damage_for_viz(pd.read_csv(path))
        totals.append((event_id, float(damage["direct_damage_mean_usd"].sum()) / 1_000_000))

    fig, ax = plt.subplots(figsize=(8, 5))
    events, values = zip(*totals)
    ax.bar(events, values, color="#f58518", edgecolor="white")
    ax.set_xlabel("Event")
    ax.set_ylabel("Segment damage total (MUSD)")
    ax.set_title("Step 3 draft: consolidated segment damage totals")
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    out = fig_dir / "step3_damage" / "step3_damage_by_event_draft.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_recovery_draft(results_root: Path, fig_dir: Path) -> Path | None:
    variant = os.environ.get("NIRD_RESULTS_VARIANT", "revision")
    depth = os.environ.get("NIRD_DEPTH_KEY", "30")
    reroot = results_root / "rerouting_analysis" / variant / depth
    if not reroot.is_dir():
        return None

    frames: list[pd.DataFrame] = []
    for event_dir in sorted(p for p in reroot.iterdir() if p.is_dir()):
        cost_path = event_dir / "cost_matrix_by_scenario.csv"
        if not cost_path.exists():
            continue
        df = pd.read_csv(cost_path)
        if df.empty:
            continue
        chunk = df.copy()
        chunk["event"] = event_dir.name
        frames.append(chunk)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)

    # x-axis: recovery day if present (post day-keying fix), else fall back to scenario
    x_col = "event_day" if "event_day" in combined.columns else "scenario"
    x_label = "Recovery day" if x_col == "event_day" else "Recovery scenario"

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), squeeze=True)

    # Panel 1: rerouting cost (MUSD) along the recovery timeline
    ax = axes[0]
    for event, group in combined.groupby("event"):
        group = group.sort_values(x_col)
        ax.plot(
            group[x_col],
            group["rerouting_cost"] / 1_000_000.0,
            marker="o",
            label=f"Event {event}",
        )
    ax.axhline(0.0, color="#999999", linewidth=0.8, linestyle="--")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Rerouting cost (MUSD)")
    ax.set_title("Step 4: rerouting cost along recovery")
    ax.legend()
    ax.grid(True, alpha=0.2)

    # Panel 2: disrupted freight flow along the recovery timeline
    ax = axes[1]
    flow_col = "total_disrupted_flow" if "total_disrupted_flow" in combined.columns else None
    if flow_col:
        for event, group in combined.groupby("event"):
            group = group.sort_values(x_col)
            ax.plot(
                group[x_col],
                group[flow_col],
                marker="s",
                label=f"Event {event}",
            )
        ax.set_xlabel(x_label)
        ax.set_ylabel("Disrupted flow (trucks/day)")
        ax.set_title("Step 4: disrupted freight flow along recovery")
        ax.legend()
        ax.grid(True, alpha=0.2)
    else:
        # fall back to combined total cost if disrupted-flow column is absent
        value_col = "combined_total_cost" if "combined_total_cost" in combined.columns else "rerouting_cost"
        for event, group in combined.groupby("event"):
            group = group.sort_values(x_col)
            ax.plot(group[x_col], group[value_col] / 1_000_000.0, marker="s", label=f"Event {event}")
        ax.set_xlabel(x_label)
        ax.set_ylabel("Combined cost (MUSD)")
        ax.set_title("Step 4: combined cost along recovery")
        ax.legend()
        ax.grid(True, alpha=0.2)

    fig.suptitle("Step 4 draft: recovery timeline (rerouting + direct damage)", fontsize=13)
    fig.tight_layout()
    out = fig_dir / "step4_rerouting" / "step4_recovery_costs_draft.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> None:
    fig_root, disruption_root, damage_root = _roots()
    results_root = Path(os.environ["NIRD_RESULTS_ROOT"])
    for label, path in [
        ("disruption", plot_disruption_summary(disruption_root, fig_root)),
        ("damage summary", plot_damage_summary(damage_root, fig_root)),
        ("damage detail", plot_damage_detail(damage_root, fig_root)),
        ("recovery", plot_recovery_draft(results_root, fig_root)),
    ]:
        if path:
            print(f"Wrote {path}")
        else:
            print(f"Skipped {label} (inputs missing)")


if __name__ == "__main__":
    main()
