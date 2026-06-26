"""Performance profiling infographic for the Pass B freight assignment pipeline.

Produces a multi-panel figure summarizing:
  A. Wall-time reduction across optimization steps (baseline -> Patch 6 -> pool -> production)
  B. Per-phase time breakdown (LCP, od_id rewrite, streaming pass 1/2) by step
  C. NumCpu scaling behavior (LCP vs wall time)
  D. Convergence trajectory of the unbounded production run (parsed from its log)

Benchmark numbers are the authoritative values documented in
docs/passb_parallel_optimization_log.md (1-iteration smoke benchmarks).
The convergence panel is parsed live from the unbounded Pass B log if present.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# ---------------------------------------------------------------------------
# Authoritative benchmark data (docs/passb_parallel_optimization_log.md)
# 1-iteration smoke, NumCpu=1 unless noted. Times in seconds.
# ---------------------------------------------------------------------------
STEPS = [
    # label, wall, lcp, od_id, stream_p1, stream_p2
    ("0 baseline\n(legacy)", 4859, 1455, 1188, 549, 1503),
    ("1 Patch 6\n(od_id@insert)", 2608, 1088, 0, 247, 1225),
    ("3 pool recycle\n(maxtasks=50)", 3153, 1130, 0, 251, 1724),
    ("4 production\n(NumCpu=1)", 2537, 1048, 0, 245, 1198),
]

# NumCpu sweep (production flags): numcpu, wall, lcp  (4 aborted -> None)
NUMCPU_SWEEP = [
    (1, 2537, 1048),
    (2, 2572, 838),
    (4, None, None),  # aborted: severe negative scaling
]

PHASE_COLORS = {
    "LCP (shortest paths)": "#4c78a8",
    "od_id rewrite": "#e45756",
    "Streaming pass 1": "#54a24b",
    "Streaming pass 2": "#f58518",
}


def _fig_root() -> Path:
    results_root = Path(os.environ["NIRD_RESULTS_ROOT"])
    variant = os.environ.get("NIRD_RESULTS_VARIANT", "revision")
    out = results_root / "figures" / variant / "perf"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _read_text_any_encoding(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def parse_convergence(log_path: Path) -> tuple[list[float], float | None]:
    """Return (progress_rel_percent_per_iteration, total_sim_time_seconds)."""
    if not log_path or not log_path.exists():
        return [], None
    text = _read_text_any_encoding(log_path).replace("\r", "").replace("\n", " ")
    progress = [float(p) for p in re.findall(r"progress_rel=([0-9.]+)%", text)]
    sim_match = re.findall(r"The total simulation time:\s*([0-9.]+)", text)
    sim_time = float(sim_match[-1]) if sim_match else None
    return progress, sim_time


def _find_unbounded_log() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    logs = sorted((repo_root / "logs").glob("*passB_script1_event_candidates.log"))
    return logs[-1] if logs else None


def build_infographic(fig_dir: Path) -> Path:
    labels = [s[0] for s in STEPS]
    walls = np.array([s[1] for s in STEPS], dtype=float)
    lcp = np.array([s[2] for s in STEPS], dtype=float)
    od_id = np.array([s[3] for s in STEPS], dtype=float)
    sp1 = np.array([s[4] for s in STEPS], dtype=float)
    sp2 = np.array([s[5] for s in STEPS], dtype=float)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    # ---- Panel A: wall-time reduction ------------------------------------
    ax = axes[0, 0]
    x = np.arange(len(labels))
    bars = ax.bar(x, walls / 60.0, color=["#b0b0b0", "#4c78a8", "#7aa6c2", "#54a24b"])
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_ylabel("Wall time (minutes, 1-iter smoke)")
    ax.set_title("A. Pass B wall-time reduction by optimization step", fontweight="bold")
    base = walls[0]
    for i, b in enumerate(bars):
        pct = (walls[i] - base) / base * 100.0
        tag = f"{walls[i]/60:.0f} min"
        if i > 0:
            tag += f"\n({pct:+.0f}%)"
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), tag,
                ha="center", va="bottom", fontsize=9)
    ax.grid(True, axis="y", alpha=0.2)
    ax.set_ylim(0, walls.max() / 60.0 * 1.18)

    # ---- Panel B: phase breakdown (stacked) ------------------------------
    ax = axes[0, 1]
    ax.bar(x, lcp / 60.0, label="LCP (shortest paths)", color=PHASE_COLORS["LCP (shortest paths)"])
    bottom = lcp.copy()
    ax.bar(x, od_id / 60.0, bottom=bottom / 60.0, label="od_id rewrite", color=PHASE_COLORS["od_id rewrite"])
    bottom = bottom + od_id
    ax.bar(x, sp1 / 60.0, bottom=bottom / 60.0, label="Streaming pass 1", color=PHASE_COLORS["Streaming pass 1"])
    bottom = bottom + sp1
    ax.bar(x, sp2 / 60.0, bottom=bottom / 60.0, label="Streaming pass 2", color=PHASE_COLORS["Streaming pass 2"])
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_ylabel("Phase time (minutes)")
    ax.set_title("B. Where the time goes (per-phase breakdown)", fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, axis="y", alpha=0.2)
    # annotate the eliminated od_id phase on the baseline
    ax.annotate("Patch 6 eliminates\nthe ~20 min od_id rewrite",
                xy=(0, (lcp[0] + od_id[0] / 2) / 60.0),
                xytext=(0.6, (walls[0]) / 60.0 * 0.92),
                fontsize=8, color="#e45756",
                arrowprops=dict(arrowstyle="->", color="#e45756"))

    # ---- Panel C: NumCpu scaling -----------------------------------------
    ax = axes[1, 0]
    cpus = [str(c[0]) for c in NUMCPU_SWEEP]
    cx = np.arange(len(cpus))
    width = 0.38
    wall_vals = [c[1] / 60.0 if c[1] else 0 for c in NUMCPU_SWEEP]
    lcp_vals = [c[2] / 60.0 if c[2] else 0 for c in NUMCPU_SWEEP]
    ax.bar(cx - width / 2, wall_vals, width, label="Wall time", color="#4c78a8")
    ax.bar(cx + width / 2, lcp_vals, width, label="LCP time", color="#f58518")
    ax.set_xticks(cx, [f"NumCpu={c}" for c in cpus])
    ax.set_ylabel("Time (minutes)")
    ax.set_title("C. Parallel scaling: more cores did NOT help", fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.2)
    # mark the aborted run
    ax.text(cx[-1], 1.0, "ABORTED\n(severe negative\nscaling)", ha="center", va="bottom",
            fontsize=9, color="#e45756", fontweight="bold")

    # ---- Panel D: convergence trajectory ---------------------------------
    ax = axes[1, 1]
    log_path = _find_unbounded_log()
    progress, sim_time = parse_convergence(log_path) if log_path else ([], None)
    if progress:
        iters = np.arange(1, len(progress) + 1)
        ax.plot(iters, progress, marker="o", color="#54a24b")
        ax.set_yscale("log")
        ax.set_xlabel("Assignment iteration")
        ax.set_ylabel("Relative progress per iter (%, log scale)")
        title = "D. Unbounded run convergence"
        if sim_time:
            title += f"  ({len(progress)} iters, {sim_time/3600:.1f} h)"
        ax.set_title(title, fontweight="bold")
        ax.grid(True, which="both", alpha=0.2)
        ax.annotate("flow exhausted\n-> stop",
                    xy=(iters[-1], progress[-1]),
                    xytext=(iters[-1] * 0.6, max(progress[-1] * 4, min(progress))),
                    fontsize=8, arrowprops=dict(arrowstyle="->"))
    else:
        ax.text(0.5, 0.5, "Convergence log not found", ha="center", va="center",
                transform=ax.transAxes)
        ax.set_title("D. Unbounded run convergence", fontweight="bold")

    fig.suptitle(
        "Pass B freight assignment - performance profile\n"
        "Benchmarks: 1-iteration smoke, Windows / nird env (docs/passb_parallel_optimization_log.md)",
        fontsize=14, fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = fig_dir / "passb_performance_profile.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> None:
    fig_dir = _fig_root()
    out = build_infographic(fig_dir)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
