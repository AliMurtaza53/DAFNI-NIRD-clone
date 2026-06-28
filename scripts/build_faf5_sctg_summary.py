"""Build permanent FAF5 industry (SCTG G5) daily-truck summary for visualization."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from nird.faf5_paths import (
    resolve_detailed_county_od_path,
    resolve_faf5_data_root,
    resolve_regional_od_path,
    truck_factor_paths,
)
from nird.utils import load_config

LOGGER = logging.getLogger(__name__)
SCTG_G5_LABELS = {
    "sctg0109": "SCTG 01-09: Ag, fish, forestry",
    "sctg1014": "SCTG 10-14: Mining",
    "sctg1519": "SCTG 15-19: Petroleum & coal",
    "sctg2033": "SCTG 20-33: Manufactured goods",
    "sctg3499": "SCTG 34-99: Mixed & other",
}


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".pq", ".parquet"}:
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _flow_column(df: pd.DataFrame) -> str:
    for col in ("daily_truck_trips", "Car21", "flow", "daily_trips", "annual_truck_trips"):
        if col in df.columns:
            return col
    raise ValueError(f"No truck-flow column in {list(df.columns)}")


def _normalize_sctg(df: pd.DataFrame) -> pd.DataFrame:
    from nird.faf5_county_disaggregation import map_faf_sctg_to_sctgG5

    working = df.copy()
    if "sctgG5" not in working.columns:
        if "sctg" not in working.columns and "sctg2" in working.columns:
            working = working.rename(columns={"sctg2": "sctg"})
        working = map_faf_sctg_to_sctgG5(working)
    working["sctgG5"] = working["sctgG5"].astype(str).str.lower()
    return working


def aggregate_sctg_daily_trucks(df: pd.DataFrame) -> pd.DataFrame:
    flow_col = _flow_column(df)
    flows = pd.to_numeric(df[flow_col], errors="coerce").fillna(0.0)
    if flow_col == "annual_truck_trips":
        flows = flows / 365.0
    grouped = (
        df.assign(sctgG5=df["sctgG5"].astype(str).str.lower(), daily_truck_trips=flows)
        .groupby("sctgG5", as_index=False)["daily_truck_trips"]
        .sum()
        .sort_values("daily_truck_trips", ascending=False)
    )
    grouped["industry"] = grouped["sctgG5"].map(SCTG_G5_LABELS).fillna(grouped["sctgG5"])
    total = grouped["daily_truck_trips"].sum()
    grouped["share_pct"] = grouped["daily_truck_trips"] / total * 100.0 if total > 0 else 0.0
    return grouped


def _manifest_county_sources(base_path: Path, repo_root: Path) -> list[Path]:
    manifest_path = base_path / "tables" / "conus_freight_workflow_manifest.json"
    manifest_sources: list[Path] = []
    if not manifest_path.exists():
        return manifest_sources
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("county_od_source", "county_od_destination"):
        raw = manifest.get(key)
        if not raw:
            continue
        manifest_sources.append(Path(raw))
        if not Path(raw).is_absolute():
            manifest_sources.append(repo_root / raw)
    return manifest_sources


def resolve_county_source(
    base_path: Path,
    repo_root: Path,
    faf5_root: Path | None,
    explicit: str | None = None,
) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    for candidate in _manifest_county_sources(base_path, repo_root):
        if candidate.exists():
            return candidate
    return resolve_detailed_county_od_path(faf5_root, base_path)


def materialize_county_od_from_local_faf5(
    faf5_root: Path,
    *,
    year: int = 2022,
    output_path: Path | None = None,
) -> Path:
    """Build detailed county OD with SCTG from local FAF5 inputs under faf5_data."""
    from nird.faf5_county_disaggregation import run_county_disaggregation

    regional = resolve_regional_od_path(faf5_root)
    if regional is None:
        raise FileNotFoundError(
            f"No regional FAF OD found under {faf5_root / 'regional_od_data'}. "
            "Place FAF5.7.1_2018-2024.csv there or set NIRD_FAF_REGIONAL_OD_PATH."
        )
    origin_factors, destination_factors = truck_factor_paths(faf5_root)
    if not origin_factors.exists() or not destination_factors.exists():
        raise FileNotFoundError(
            f"Missing truck county factors under {faf5_root / 'county_disaggregation_factors'}"
        )

    out = output_path or (
        faf5_root / "processed" / f"faf5_county_truck_od_usa_{year}_detail.parquet"
    )
    if out.exists():
        return out

    out.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Building detailed county OD from %s", regional)
    run_county_disaggregation(
        faf_od_path=regional,
        origin_factor_path=origin_factors,
        destination_factor_path=destination_factors,
        output_path=out,
        year=year,
        mode="truck",
        tons_unit="thousand_tons",
        read_chunksize=50_000,
    )
    return out


def build_from_regional_faf(regional_path: Path, *, year: int = 2022, payload_tons: float = 20.0) -> pd.DataFrame:
    from nird.faf5_county_disaggregation import load_faf_regional_od, map_faf_sctg_to_sctgG5

    regional = map_faf_sctg_to_sctgG5(
        load_faf_regional_od(regional_path, year=year, mode="truck", tons_unit="thousand_tons")
    )
    regional["daily_truck_trips"] = (
        pd.to_numeric(regional["tons"], errors="coerce").fillna(0.0) * 1000.0 / payload_tons / 365.0
    )
    return aggregate_sctg_daily_trucks(regional)


def build_sctg_summary(
    base_path: Path,
    repo_root: Path,
    *,
    county_od_path: str | None = None,
    regional_od_path: str | None = None,
    output_path: Path | None = None,
    year: int = 2022,
    build_county_od: bool = False,
) -> Path:
    out = output_path or (base_path / "census_datasets" / "faf5_sctg_daily_trucks.pq")
    out.parent.mkdir(parents=True, exist_ok=True)
    faf5_root = resolve_faf5_data_root(base_path, repo_root)

    source = resolve_county_source(base_path, repo_root, faf5_root, county_od_path)
    if source is None and build_county_od and faf5_root is not None:
        source = materialize_county_od_from_local_faf5(faf5_root, year=year)
    if source is not None:
        df = _normalize_sctg(_read_table(source))
        if "sctgG5" not in df.columns:
            LOGGER.warning("%s has no sctgG5 column; falling back to regional FAF", source)
        else:
            summary = aggregate_sctg_daily_trucks(df)
            summary.to_parquet(out, index=False)
            LOGGER.info("Wrote %s rows to %s from county OD %s", len(summary), out, source)
            return out

    regional = Path(regional_od_path) if regional_od_path else None
    if regional is None and faf5_root is not None:
        regional = resolve_regional_od_path(faf5_root)
    if regional is not None and regional.exists():
        summary = build_from_regional_faf(regional, year=year)
        summary.to_parquet(out, index=False)
        LOGGER.info("Wrote %s rows to %s from regional FAF %s", len(summary), out, regional)
        return out

    hint = f"{faf5_root / 'regional_od_data'}" if faf5_root is not None else "Desktop/data/faf5_data/regional_od_data"
    raise FileNotFoundError(
        "No county OD or regional FAF source found for SCTG summary. "
        f"Add FAF5.7.1_2018-2024.csv under {hint}, or pass --build-county-od once regional OD is present."
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county-od-path", default=None)
    parser.add_argument("--regional-od-path", default=None)
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--build-county-od", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config = load_config()
    base_path = Path(config["paths"]["soge_clusters"])
    repo_root = Path(__file__).resolve().parents[1]
    output = Path(args.output) if args.output else None
    build_sctg_summary(
        base_path,
        repo_root,
        county_od_path=args.county_od_path,
        regional_od_path=args.regional_od_path,
        output_path=output,
        year=args.year,
        build_county_od=args.build_county_od,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
