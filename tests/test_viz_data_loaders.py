"""Tests for visualization data loaders."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VIZ_DIR = REPO_ROOT / "scripts" / "visualizations"
if str(VIZ_DIR) not in sys.path:
    sys.path.insert(0, str(VIZ_DIR))

from viz_data_loaders import (
    aggregate_sctg_daily_trucks,
    build_flow_validation_table,
    event_damage_total_usd,
    format_usd_millions,
    prepare_damage_for_viz,
    summarize_od_flows,
)


def test_summarize_od_flows_uses_car21() -> None:
    df = pd.DataFrame({"origin_node": [1, 2], "destination_node": [2, 3], "Car21": [10.0, 5.0]})
    summary = summarize_od_flows(df, "test")
    assert summary["total_daily_trucks"] == 15.0
    assert summary["max_daily_trucks"] == 10.0


def test_prepare_damage_for_viz_uses_consolidated_usd() -> None:
    df = pd.DataFrame(
        {
            "e_id": ["a", "b"],
            "C5_surface_damage_value_mean": [1.0, 0.5],
            "C6_surface_damage_value_mean": [1.0, 0.5],
        }
    )
    out = prepare_damage_for_viz(df)
    assert event_damage_total_usd(out) == pytest.approx(1_500_000.0)


def test_format_usd_millions() -> None:
    assert format_usd_millions(1_370_000.0) == "$1.37M"


def test_aggregate_sctg_daily_trucks() -> None:
    county = pd.DataFrame(
        {
            "sctgG5": ["sctg0109", "sctg0109", "sctg2033"],
            "daily_truck_trips": [100.0, 50.0, 200.0],
        }
    )
    grouped = aggregate_sctg_daily_trucks(county)
    assert grouped.loc[grouped["sctgG5"] == "sctg0109", "daily_truck_trips"].iloc[0] == 150.0


def test_build_flow_validation_table_skips_stale_odpfc(tmp_path) -> None:
    input_root = tmp_path / "input"
    variant_root = tmp_path / "variant"
    (input_root / "census_datasets").mkdir(parents=True)
    variant_root.mkdir(parents=True)

    od = pd.DataFrame({"origin_node": [1, 2], "destination_node": [2, 3], "Car21": [100.0, 100.0]})
    od.to_parquet(input_root / "census_datasets" / "faf5_od_matrix.pq", index=False)
    stale = pd.DataFrame({"origin_node": [1], "destination_node": [2], "flow": [1.0]})
    stale.to_parquet(variant_root / "odpfc.pq", index=False)
    import geopandas as gpd
    from shapely.geometry import LineString

    edges = gpd.GeoDataFrame(
        {"e_id": ["1"], "acc_flow": [1.0], "geometry": [LineString([(0, 0), (1, 1)])]},
        crs="EPSG:4326",
    )
    edges.to_parquet(variant_root / "edge_flows.gpq")

    table = build_flow_validation_table(input_root, variant_root)
    labels = table["label"].tolist()
    assert any("Full assignment OD" in label for label in labels)
    assert not any("Assigned OD paths" in label for label in labels)


def test_build_flow_validation_table_skips_stride_when_one(tmp_path, monkeypatch) -> None:
    input_root = tmp_path / "input"
    variant_root = tmp_path / "variant"
    (input_root / "census_datasets").mkdir(parents=True)
    (variant_root).mkdir(parents=True)

    od = pd.DataFrame({"origin_node": [1, 2, 3], "destination_node": [2, 3, 4], "Car21": [1.0, 2.0, 3.0]})
    od.to_parquet(input_root / "census_datasets" / "faf5_od_matrix.pq", index=False)

    import geopandas as gpd
    from shapely.geometry import LineString

    edges = gpd.GeoDataFrame(
        {"e_id": ["1"], "acc_flow": [6.0], "geometry": [LineString([(0, 0), (1, 1)])]},
        crs="EPSG:4326",
    )
    edges.to_parquet(variant_root / "edge_flows_pass_a.gpq")

    monkeypatch.setenv("NIRD_VIZ_SAMPLE_STRIDE", "1")
    table = build_flow_validation_table(input_root, variant_root)
    labels = table["label"].tolist()
    assert any("Full assignment OD" in label for label in labels)
    assert not any("Stride-" in label for label in labels)
