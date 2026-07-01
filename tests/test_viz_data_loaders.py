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
    build_scenario_summary_table,
    event_damage_total_usd,
    format_cost,
    format_usd_millions,
    is_testbed_variant,
    prepare_damage_for_viz,
    resolve_cost_display_unit,
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


def test_format_cost_uses_kusd_for_testbed() -> None:
    assert format_cost(264.87, variant="toy_sioux_falls") == "$0.3K"
    assert resolve_cost_display_unit(264.87, variant="toy_sioux_falls") == "kusd"


def test_format_cost_uses_musd_for_production_scale() -> None:
    assert format_cost(2_500_000.0, variant="revision") == "$2.50M"
    assert resolve_cost_display_unit(2_500_000.0, variant="revision") == "musd"


def test_is_testbed_variant() -> None:
    assert is_testbed_variant("toy_sioux_falls")
    assert not is_testbed_variant("revision")


def test_build_scenario_summary_table(tmp_path) -> None:
    variant = "toy_sioux_falls"
    depth_key = 30
    flood_key = 1
    links_dir = (
        tmp_path / "disruption_analysis" / variant / str(depth_key) / "links"
    )
    reroute_dir = tmp_path / "rerouting_analysis" / variant / str(depth_key) / str(flood_key)
    damage_dir = tmp_path / "damage_analysis" / variant
    links_dir.mkdir(parents=True)
    reroute_dir.mkdir(parents=True)
    damage_dir.mkdir(parents=True)

    links = pd.DataFrame(
        {
            "e_id": ["e1", "e2"],
            "flood_depth_max": [0.5, 0.0],
            "max_speed": [0.0, 45.0],
            "damage_level_max": ["moderate", "no"],
        }
    )
    links.to_parquet(links_dir / f"road_links_{flood_key}.gpq", index=False)
    pd.DataFrame(
        {
            "scenario": [1],
            "event_day": [1],
            "total_disrupted_flow": [0.0],
            "rerouting_cost": [0.0],
            "direct_damage_total_usd": [12_345.0],
            "combined_total_cost": [12_345.0],
        }
    ).to_csv(reroute_dir / "cost_matrix_by_scenario.csv", index=False)
    pd.DataFrame(
        {
            "scenario": [1],
            "event_day": [1],
            "total_disrupted_flow": [100.0],
            "rerouting_cost": [-50.0],
            "direct_damage_total_usd": [12_345.0],
            "combined_total_cost": [12_295.0],
        }
    ).to_csv(reroute_dir / "cost_matrix_passenger_by_scenario.csv", index=False)
    pd.DataFrame({"e_id": ["e1"], "C5_surface_damage_value_mean": [0.01]}).to_csv(
        damage_dir / f"intersections_{flood_key}_with_damage_values.csv",
        index=False,
    )

    summary = build_scenario_summary_table(tmp_path, variant, depth_key, flood_keys=[flood_key])
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["flooded_links"] == 1
    assert row["passenger_disrupted_flow"] == pytest.approx(100.0)
    assert row["direct_damage_display"] == "$12.3K"


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
