"""End-to-end pipeline test on a TNTP-derived Sioux Falls fixture."""

from __future__ import annotations

import math
import subprocess

import pandas as pd
import pytest

from nird.geo_runtime import is_conus_albers_alias
from sioux_falls_fixtures import build_sioux_falls_dataset, sioux_falls_env
from toy_pipeline_fixtures import (
    base_scenario_dir,
    damage_dir,
    disruption_dir,
    reroute_dir,
    run_pipeline_scripts,
)


def _edge_flows(edge_flows_path) -> pd.DataFrame:
    flows = pd.read_parquet(edge_flows_path)
    assert not flows.empty, f"edge flows output is empty: {edge_flows_path}"
    flow_col = "acc_flow" if "acc_flow" in flows.columns else "flow"
    flows = flows.copy()
    flows["e_id"] = flows["e_id"].astype(str)
    flows[flow_col] = pd.to_numeric(flows[flow_col], errors="coerce").fillna(0.0)
    return flows[["e_id", flow_col]].rename(columns={flow_col: "flow"})


def _flow_sum_on_edges(flows: pd.DataFrame, edge_ids: tuple[str, ...]) -> float:
    return float(flows.loc[flows["e_id"].isin(edge_ids), "flow"].sum())


def _assert_finite_costs(path, *, require_disrupted_flow: bool) -> pd.DataFrame:
    costs = pd.read_csv(path)
    assert not costs.empty, f"empty cost matrix: {path}"
    assert "total_disrupted_flow" in costs.columns
    assert "rerouting_cost" in costs.columns
    disrupted_total = costs["total_disrupted_flow"].astype(float).sum()
    if require_disrupted_flow:
        assert disrupted_total > 0.0
    else:
        assert disrupted_total >= 0.0
    for value in costs["rerouting_cost"].astype(float):
        assert math.isfinite(value)
    return costs


def test_sioux_falls_pipeline_scripts_reroute_bridge_bottleneck(tmp_path):
    config_path, spec, source_links = build_sioux_falls_dataset(tmp_path)
    env = sioux_falls_env(tmp_path, config_path)

    try:
        run_pipeline_scripts(env)
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            "pipeline failed for Sioux Falls fixture\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        ) from exc

    base_dir = base_scenario_dir(tmp_path, env)
    disrupt_dir = disruption_dir(tmp_path, env)
    dmg_dir = damage_dir(tmp_path, env)
    reroute_out = reroute_dir(tmp_path, env)

    edge_flows_path = base_dir / "edge_flows.gpq"
    odpfc_path = base_dir / "odpfc.pq"
    road_links_path = disrupt_dir / "links" / "road_links_1.gpq"
    intersections_path = disrupt_dir / "intersections" / "intersections_1.pq"
    damage_csv = dmg_dir / "intersections_1_with_damage_values.csv"
    cost_matrix = reroute_out / "cost_matrix_by_scenario.csv"
    passenger_cost_matrix = reroute_out / "cost_matrix_passenger_by_scenario.csv"
    freight_post_path = reroute_out / "edge_flows_freight_s1_day1.gpq"
    passenger_post_path = reroute_out / "edge_flows_passenger_s1_day1.gpq"

    assert edge_flows_path.exists(), f"missing baseline edge flows: {edge_flows_path}"
    assert odpfc_path.exists() or (base_dir / "odpfc_parts").is_dir()
    assert road_links_path.exists(), f"missing disrupted road links: {road_links_path}"
    assert intersections_path.exists(), f"missing intersections: {intersections_path}"
    assert damage_csv.exists(), f"missing damage csv: {damage_csv}"
    assert cost_matrix.exists(), f"missing freight cost matrix: {cost_matrix}"
    assert passenger_cost_matrix.exists(), (
        f"missing passenger cost matrix: {passenger_cost_matrix}"
    )

    baseline_edges = _edge_flows(edge_flows_path)
    assert _flow_sum_on_edges(baseline_edges, spec.flooded_edge_ids) > 0.0
    assert _flow_sum_on_edges(baseline_edges, spec.bridge_edge_ids) > 0.0

    source_bridges = source_links.loc[source_links["e_id"].isin(spec.bridge_edge_ids)]
    assert not source_bridges.empty
    assert set(source_bridges["road_label"].str.lower()) == {"bridge"}
    crs_epsg = source_links.crs.to_epsg() if source_links.crs is not None else None
    assert crs_epsg in {2163, 9311} or is_conus_albers_alias(source_links.crs)

    disrupted_links = pd.read_parquet(road_links_path)
    flooded = disrupted_links.loc[disrupted_links["e_id"].isin(spec.flooded_edge_ids)]
    assert len(flooded) == len(spec.flooded_edge_ids)
    assert set(flooded["road_label"].str.lower()) == {"bridge"}
    assert float(flooded["flood_depth_max"].fillna(0).min()) > 0.0
    assert float(flooded["max_speed"].fillna(999).max()) == 0.0

    non_flooded = disrupted_links.loc[~disrupted_links["e_id"].isin(spec.flooded_edge_ids)]
    assert float(non_flooded["flood_depth_max"].fillna(0).max()) == 0.0

    # Freight uses capacity-adjusted baseline odpfc flows (max ~daily link cap), so
    # disrupted freight can be zero on this network; passenger overlay uses raw demand.
    _assert_finite_costs(cost_matrix, require_disrupted_flow=False)
    _assert_finite_costs(passenger_cost_matrix, require_disrupted_flow=True)

    freight_post = _edge_flows(freight_post_path)
    passenger_post = _edge_flows(passenger_post_path)
    assert _flow_sum_on_edges(passenger_post, spec.flooded_edge_ids) < 0.0

    passenger_alternate_gain = _flow_sum_on_edges(
        passenger_post,
        spec.reroute_gain_edge_ids,
    )
    assert passenger_alternate_gain > 0.0

