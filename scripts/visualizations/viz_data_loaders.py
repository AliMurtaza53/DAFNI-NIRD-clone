"""Shared loaders for recovery pipeline visualization notebooks."""

from __future__ import annotations

import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

DEFAULT_MAX_MAP_EDGES = int(os.getenv("NIRD_VIZ_MAX_MAP_EDGES", "50000"))
DEFAULT_MAP_EDGE_THRESHOLD = int(os.getenv("NIRD_VIZ_MAP_EDGE_THRESHOLD", "100000"))
VIZ_SAMPLE_STRIDE = int(os.getenv("NIRD_VIZ_SAMPLE_STRIDE", "1"))

SCTG_G5_LABELS: dict[str, str] = {
    "sctg0109": "SCTG 01-09: Ag, fish, forestry",
    "sctg1014": "SCTG 10-14: Mining",
    "sctg1519": "SCTG 15-19: Petroleum & coal",
    "sctg2033": "SCTG 20-33: Manufactured goods",
    "sctg3499": "SCTG 34-99: Mixed & other",
}


def resolve_input_od_matrix_path(input_root: Path) -> Path:
    candidates = [
        input_root / "census_datasets" / "faf5_od_matrix.pq",
        input_root / "inputs" / "census_datasets" / "faf5_od_matrix.pq",
    ]
    env_path = os.getenv("NIRD_FAF5_OD_MATRIX_PATH")
    if env_path:
        candidates.insert(0, Path(env_path))
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Could not locate faf5_od_matrix.pq under {input_root}")


def resolve_sctg_summary_path(input_root: Path) -> Path:
    path = input_root / "census_datasets" / "faf5_sctg_daily_trucks.pq"
    if path.exists():
        return path
    raise FileNotFoundError(
        f"Missing {path}. Run scripts/build_faf5_sctg_summary.py after installing county OD."
    )


def load_assignment_od_demand(input_root: Path) -> tuple[pd.DataFrame, Path]:
    """Load the full Script 1 demand table (daily truck trips)."""
    path = resolve_input_od_matrix_path(input_root)
    df = pd.read_parquet(path)
    flow_col = _flow_column(df)
    out = df.copy()
    if flow_col != "flow":
        out["flow"] = pd.to_numeric(out[flow_col], errors="coerce").fillna(0.0)
    return out, path


def load_sctg_summary(input_root: Path) -> tuple[pd.DataFrame, Path]:
    path = resolve_sctg_summary_path(input_root)
    return pd.read_parquet(path), path


def prepare_damage_for_viz(damage_df: pd.DataFrame) -> pd.DataFrame:
    """Attach consolidated USD damage columns for plotting."""
    from nird.damage_aggregation import add_consolidated_damage_columns

    if "direct_damage_mean_usd" in damage_df.columns:
        out = damage_df.copy()
    else:
        out = add_consolidated_damage_columns(damage_df)
    out["total_damage_value_usd"] = pd.to_numeric(
        out["direct_damage_mean_usd"], errors="coerce"
    ).fillna(0.0)
    return out


def event_damage_total_usd(damage_df: pd.DataFrame) -> float:
    from nird.damage_aggregation import total_direct_damage_usd

    if "direct_damage_mean_usd" in damage_df.columns:
        return float(pd.to_numeric(damage_df["direct_damage_mean_usd"], errors="coerce").fillna(0).sum())
    return total_direct_damage_usd(damage_df)


def format_usd_millions(value_usd: float) -> str:
    if abs(value_usd) >= 1_000_000:
        return f"${value_usd / 1_000_000:,.2f}M"
    if abs(value_usd) >= 1_000:
        return f"${value_usd / 1_000:,.1f}K"
    return f"${value_usd:,.2f}"


def resolve_county_od_path(input_root: Path) -> Path | None:
    """Optional county-level OD with commodity columns (sctgG5 / daily_truck_trips)."""
    from nird.faf5_paths import resolve_detailed_county_od_path, resolve_faf5_data_root

    repo_root = Path(__file__).resolve().parents[2]
    faf5_root = resolve_faf5_data_root(input_root, repo_root)
    return resolve_detailed_county_od_path(faf5_root, input_root)


def _flow_column(df: pd.DataFrame) -> str:
    for col in ("Car21", "flow", "daily_truck_trips", "daily_trips"):
        if col in df.columns:
            return col
    raise ValueError(f"No flow column found in {list(df.columns)}")


def summarize_od_flows(df: pd.DataFrame, label: str) -> dict[str, float | int | str]:
    flow_col = _flow_column(df)
    flows = pd.to_numeric(df[flow_col], errors="coerce").fillna(0.0)
    return {
        "label": label,
        "rows": int(len(df)),
        "flow_column": flow_col,
        "total_daily_trucks": float(flows.sum()),
        "max_daily_trucks": float(flows.max()) if len(flows) else 0.0,
        "median_daily_trucks": float(flows.median()) if len(flows) else 0.0,
        "p99_daily_trucks": float(flows.quantile(0.99)) if len(flows) else 0.0,
    }


def build_flow_validation_table(
    input_root: Path,
    variant_root: Path,
    *,
    viz_stride: int | None = None,
) -> pd.DataFrame:
    """Compare full assignment OD, optional viz sidecar sample, and edge-flow totals."""
    stride = VIZ_SAMPLE_STRIDE if viz_stride is None else viz_stride
    rows: list[dict[str, float | int | str]] = []

    od_path = resolve_input_od_matrix_path(input_root)
    full_od = pd.read_parquet(od_path)
    rows.append(summarize_od_flows(full_od, "Full assignment OD (faf5_od_matrix)"))
    if stride > 1:
        rows.append(
            summarize_od_flows(
                full_od.iloc[::stride].copy(),
                f"Stride-{stride} sample (dev only)",
            )
        )

    try:
        assigned, assigned_source = load_odpfc(variant_root)
        full_total = float(rows[0]["total_daily_trucks"]) if rows else 0.0
        assigned_total = float(
            pd.to_numeric(assigned.get("flow", assigned.get("Car21", 0)), errors="coerce")
            .fillna(0.0)
            .sum()
        )
        # Ignore stale partial odpfc sidecars that are not representative of full assignment.
        if full_total <= 0 or assigned_total >= 0.5 * full_total:
            rows.append(
                summarize_od_flows(
                    assigned,
                    f"Assigned OD paths ({assigned_source.name})",
                )
            )
    except FileNotFoundError:
        pass

    edge_flows, edge_source = load_edge_flows(variant_root)
    edge_col = next(
        (c for c in ("acc_flow", "flow", "Car21", "current_flow") if c in edge_flows.columns),
        None,
    )
    if edge_col:
        edge_vals = pd.to_numeric(edge_flows[edge_col], errors="coerce").fillna(0.0)
        rows.append(
            {
                "label": f"Link flows ({edge_source.name})",
                "rows": int(len(edge_flows)),
                "flow_column": edge_col,
                "total_daily_trucks": float(edge_vals.sum()),
                "max_daily_trucks": float(edge_vals.max()),
                "median_daily_trucks": float(edge_vals.median()),
                "p99_daily_trucks": float(edge_vals.quantile(0.99)),
            }
        )

    out = pd.DataFrame(rows)
    out["note"] = (
        "Car21 / flow = daily truck trips from FAF5 county disaggregation "
        "(annual_tons / payload / 365). Link-flow totals sum across links and "
        "are not comparable to OD-trip totals."
    )
    return out


def load_county_od_by_sctg(input_root: Path) -> tuple[pd.DataFrame, Path]:
    county_path = resolve_county_od_path(input_root)
    if county_path is None:
        raise FileNotFoundError(
            "County-level FAF5 OD with commodity not found. Set NIRD_FAF5_COUNTY_OD_PATH "
            "to a parquet/CSV containing sctgG5 and daily_truck_trips or tons."
        )
    if county_path.suffix.lower() in {".pq", ".parquet"}:
        df = pd.read_parquet(county_path)
    else:
        df = pd.read_csv(county_path)
    if "sctgG5" not in df.columns:
        from nird.faf5_county_disaggregation import map_faf_sctg_to_sctgG5

        working = df.copy()
        if "sctg" not in working.columns and "sctg2" in working.columns:
            working = working.rename(columns={"sctg2": "sctg"})
        df = map_faf_sctg_to_sctgG5(working)
    if "sctgG5" not in df.columns:
        raise ValueError(f"{county_path} does not contain sctgG5 or sctg2")
    return df, county_path


def aggregate_sctg_daily_trucks(county_od: pd.DataFrame) -> pd.DataFrame:
    flow_col = _flow_column(county_od)
    grouped = (
        county_od.assign(
            sctgG5=county_od["sctgG5"].astype(str),
            flow=pd.to_numeric(county_od[flow_col], errors="coerce").fillna(0.0),
        )
        .groupby("sctgG5", as_index=False)["flow"]
        .sum()
        .sort_values("flow", ascending=False)
    )
    grouped["industry"] = grouped["sctgG5"].map(SCTG_G5_LABELS).fillna(grouped["sctgG5"])
    grouped["share_pct"] = grouped["flow"] / grouped["flow"].sum() * 100.0
    return grouped.rename(columns={"flow": "daily_truck_trips"})


def should_skip_map_layers(links_gdf: gpd.GeoDataFrame | pd.DataFrame) -> bool:
    """Skip choropleth/line maps when link counts exceed safe notebook limits."""
    if os.getenv("NIRD_VIZ_SKIP_MAPS", "0").strip().lower() in {"1", "true", "yes"}:
        return True
    return len(links_gdf) > DEFAULT_MAP_EDGE_THRESHOLD


def resolve_odpfc_path(variant_root: Path) -> Path | None:
    """Return combined odpfc.pq or the first available odpfc_parts parquet."""
    combined = variant_root / "odpfc.pq"
    if combined.exists():
        return combined
    parts_dir = variant_root / "odpfc_parts"
    if parts_dir.is_dir():
        parts = sorted(parts_dir.glob("*.pq"))
        if parts:
            return parts[0] if len(parts) == 1 else parts_dir
    return None


def load_odpfc(variant_root: Path) -> tuple[pd.DataFrame, Path]:
    """Load baseline OD path table from odpfc.pq or odpfc_parts/*.pq."""
    combined = variant_root / "odpfc.pq"
    if combined.exists():
        return pd.read_parquet(combined), combined

    parts_dir = variant_root / "odpfc_parts"
    parts = sorted(parts_dir.glob("*.pq")) if parts_dir.is_dir() else []
    if not parts:
        raise FileNotFoundError(
            f"Missing odpfc.pq and odpfc_parts under {variant_root}. "
            "Run the viz ODPFC sidecar with NIRD_COMBINE_ODPFC_PARTS=1."
        )

    frames = [pd.read_parquet(part) for part in parts]
    merged = pd.concat(frames, ignore_index=True)
    return merged, parts_dir


def resolve_edge_flows_path(variant_root: Path) -> Path:
    """Prefer Pass A edge flows backup for baseline Step 1 panels when present."""
    pass_a = variant_root / "edge_flows_pass_a.gpq"
    if pass_a.exists():
        return pass_a
    current = variant_root / "edge_flows.gpq"
    if current.exists():
        return current
    raise FileNotFoundError(f"Missing edge flows under {variant_root}")


def load_edge_flows(variant_root: Path) -> tuple[gpd.GeoDataFrame, Path]:
    path = resolve_edge_flows_path(variant_root)
    return gpd.read_parquet(path), path


def subset_links_for_map(
    links_gdf: gpd.GeoDataFrame,
    flow_col: str = "acc_flow",
    *,
    max_edges: int | None = None,
    min_flow: float = 0.0,
) -> gpd.GeoDataFrame:
    """Keep high-flow links only so CONUS maps stay within notebook memory limits."""
    limit = DEFAULT_MAX_MAP_EDGES if max_edges is None else max_edges
    if limit <= 0 or len(links_gdf) <= limit:
        return links_gdf

    flow_candidates = [flow_col, "flow", "current_flow", "acc_flow"]
    col = next((c for c in flow_candidates if c in links_gdf.columns), None)
    if col is None:
        return links_gdf.iloc[:limit].copy()

    flows = pd.to_numeric(links_gdf[col], errors="coerce").fillna(0.0)
    active = links_gdf.loc[flows > min_flow].copy()
    if len(active) <= limit:
        return active
    return active.assign(_viz_flow=flows.loc[active.index]).nlargest(limit, "_viz_flow").drop(
        columns="_viz_flow"
    )
