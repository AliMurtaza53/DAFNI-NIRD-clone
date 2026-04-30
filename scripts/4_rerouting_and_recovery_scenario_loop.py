# %%
import sys
import json
import warnings
import gc
import ast

from pathlib import Path
from typing import Tuple, Dict
import logging

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(1, str(REPO_ROOT))

import geopandas as gpd
import pandas as pd
import numpy as np
from tqdm import tqdm
from collections import defaultdict

import nird.road_revised as func
from nird.utils import get_results_variant, load_config, get_flow_on_edges
import duckdb

# %%
warnings.simplefilter("ignore")
base_path = Path(load_config()["paths"]["soge_clusters"])
tqdm.pandas()


def first_existing(paths):
    """Return first existing path from a sequence, else None."""
    for path in paths:
        p = Path(path)
        if p.exists():
            return p
    return None


def to_edge_id_list(value):
    """Convert path-like values from parquet into a normalized list of edge-id strings."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []

    # already list-like
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v is not None and str(v) != "nan"]

    # numpy array from parquet/object coercion
    if isinstance(value, np.ndarray):
        vals = value.tolist()
        # Handle character-array encodings of a stringified list
        if vals and all(isinstance(v, str) and len(v) == 1 for v in vals):
            joined = "".join(vals)
            if joined.startswith("[") and joined.endswith("]"):
                try:
                    parsed = ast.literal_eval(joined)
                    return [str(v) for v in parsed if v is not None and str(v) != "nan"]
                except Exception:
                    pass
        if value.dtype.kind in {"U", "S"}:
            joined = "".join(vals)
            if joined.startswith("[") and joined.endswith("]"):
                try:
                    parsed = ast.literal_eval(joined)
                    return [str(v) for v in parsed if v is not None and str(v) != "nan"]
                except Exception:
                    return [str(v) for v in vals if v not in {"[", "]", ",", " "}]
        return [str(v) for v in vals if v is not None and str(v) != "nan"]

    # stringified list
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, (list, tuple, set, np.ndarray)):
                    return [str(v) for v in parsed if v is not None and str(v) != "nan"]
            except Exception:
                pass
        # fallback: comma-separated tokens
        return [tok.strip() for tok in s.split(",") if tok.strip()]

    return [str(value)]


# %%
def bridge_recovery(
    day: int,
    damage_level: str,
    pre_event_capacity: float,
    acc_capacity: float,
    bridge_recovery_dict: Dict,
) -> float:
    if damage_level != "no":  # minor, moderate, extensive, severe
        recovery_rate = bridge_recovery_dict.get(damage_level, [])[day]
        acc_capacity = pre_event_capacity * recovery_rate
    return acc_capacity


def ordinary_road_recovery(
    day: int,
    damage_level: str,
    pre_event_capacity: float,
    acc_capacity: float,
    road_recovery_dict: Dict,
) -> float:
    if damage_level != "no":  # minor, moderate, extensive, severe
        recovery_rate = road_recovery_dict.get(damage_level, [])[day]
        acc_capacity = pre_event_capacity * recovery_rate
    return acc_capacity


def load_scenarios(base_path: Path) -> Tuple[Dict, Dict]:
    """Load recovery rates for bridges and ordinary roads."""
    scenario_path = first_existing(
        [
            base_path / "tables" / "recovery design_updated.csv",
            base_path / "inputs" / "tables" / "recovery design_updated.csv",
        ]
    )
    if scenario_path is None:
        raise FileNotFoundError(
            "Could not find recovery dfesign_updated.csv in standard or toy input table paths"
        )
    df = pd.read_csv(scenario_path)

    bridge_recovery_dict = defaultdict(list)
    road_recovery_dict = defaultdict(list)
    scenarios = []
    conditions = []
    for _, row in df.iterrows():
        bridge_recovery_dict["minor"].append(row["bridge_minor"])
        bridge_recovery_dict["moderate"].append(row["bridge_moderate"])
        bridge_recovery_dict["extensive"].append(row["bridge_extensive"])
        bridge_recovery_dict["severe"].append(row["bridge_severe"])
        road_recovery_dict["minor"].append(row["road_minor"])
        road_recovery_dict["moderate"].append(row["road_moderate"])
        road_recovery_dict["extensive"].append(row["road_extensive"])
        road_recovery_dict["severe"].append(row["road_severe"])
        scenarios.append(int(row["scenario"]))
        conditions.append(int(row["event_day"]))

    return (bridge_recovery_dict, road_recovery_dict, scenarios, conditions)


def load_event_damage_from_script3(base_path: Path, flood_key: int) -> Tuple[pd.DataFrame, float]:
    """Load script-3 event damage CSV and aggregate per-edge damage level.

    Returns
    -------
    Tuple[pd.DataFrame, float]
        - DataFrame with columns ["e_id", "damage_level_max", "road_label"]
        - total direct damage (sum of all *_damage_value_mean columns)
    """
    damage_csv = (
        base_path.parent
        / "results"
        / "damage_analysis"
        / get_results_variant()
        / f"intersections_{flood_key}_with_damage_values.csv"
    )
    if not damage_csv.exists():
        logging.warning(f"Script-3 damage output not found for event {flood_key}: {damage_csv}")
        return pd.DataFrame(columns=["e_id", "damage_level_max", "road_label"]), 0.0

    damage_df = pd.read_csv(damage_csv, low_memory=False)
    if damage_df.empty:
        return pd.DataFrame(columns=["e_id", "damage_level_max", "road_label"]), 0.0

    # total direct damage from all mean damage columns
    mean_cols = [c for c in damage_df.columns if c.endswith("_damage_value_mean")]
    direct_damage_total = float(damage_df[mean_cols].fillna(0).sum().sum()) if mean_cols else 0.0

    # aggregate event damage levels to a per-edge max
    level_map = {"no": 0, "minor": 1, "moderate": 2, "extensive": 3, "severe": 4}
    level_rev = {v: k for k, v in level_map.items()}

    for col in ["damage_level_surface", "damage_level_river"]:
        if col not in damage_df.columns:
            damage_df[col] = "no"
        # tolerate mixed str/int in CSV by coercing robustly
        as_num = pd.to_numeric(damage_df[col], errors="coerce")
        as_str_num = damage_df[col].astype(str).str.lower().map(level_map)
        damage_df[col] = as_num.fillna(as_str_num).fillna(0).astype(int)

    if "road_label" not in damage_df.columns:
        damage_df["road_label"] = "road"
    damage_df["road_label"] = damage_df["road_label"].astype(str).str.lower()
    damage_df.loc[~damage_df["road_label"].isin(["road", "bridge", "tunnel"]), "road_label"] = "road"

    damage_by_edge = (
        damage_df.assign(damage_level_max_num=damage_df[["damage_level_surface", "damage_level_river"]].max(axis=1))
        .groupby("e_id", as_index=False)
        .agg(
            {
                "damage_level_max_num": "max",
                "road_label": "first",
            }
        )
    )
    damage_by_edge["e_id"] = damage_by_edge["e_id"].astype(str)
    damage_by_edge["damage_level_max"] = damage_by_edge["damage_level_max_num"].map(level_rev)
    damage_by_edge = damage_by_edge[["e_id", "damage_level_max", "road_label"]]

    logging.info(
        f"Loaded script-3 damages for event {flood_key}: edges={len(damage_by_edge)}, "
        f"direct_damage_total={direct_damage_total:.2f}"
    )
    return damage_by_edge, direct_damage_total


def main(
    depth_key,
    flood_key,
    num_of_chunk,
    num_of_cpu,
):
    logging.info("Start...")
    db_path = base_path / "dbs" / f"recovery_{depth_key}_{flood_key}.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info(f"Database path is: {db_path}")

    # Load network parameters
    breakpoint_path = first_existing(
        [
            base_path / "parameters" / "flow_breakpoint_dict.json",
            base_path / "inputs" / "parameters" / "flow_breakpoint_dict.json",
        ]
    )
    if breakpoint_path is None:
        raise FileNotFoundError(
            "Could not find flow_breakpoint_dict.json in standard or toy parameter paths"
        )
    with open(breakpoint_path, "r") as f:
        flow_breakpoint_dict = json.load(f)

    # Load recovery scenarios
    (
        bridge_recovery_dict,
        road_recovery_dict,
        scenarios,  # list of scenarios
        conditions,  # condition == 1: day 0, otherwise: day > 0
    ) = load_scenarios(base_path)

    # Load pre-identified odpfc (containing flooded links)
    results_variant = get_results_variant()
    odpfc_path = (
        base_path.parent
        / "results"
        / "disruption_analysis"
        / results_variant
        / "od"
        / f"odpfc_{depth_key}_{flood_key}.pq"
    )
    if not odpfc_path.exists():
        logging.warning(
            f"Missing odpfc at {odpfc_path}. Falling back to base scenario odpfc."
        )
        base_odpfc_path = (
            base_path.parent / "results" / "base_scenario" / results_variant / "odpfc.pq"
        )
        if base_odpfc_path.exists():
            odpfc_path.parent.mkdir(parents=True, exist_ok=True)
            pd.read_parquet(base_odpfc_path).to_parquet(odpfc_path)
        else:
            logging.error(f"Base scenario odpfc missing: {base_odpfc_path}")
            sys.exit(1)

    disrupted_candidates = pd.read_parquet(odpfc_path)
    if "path" in disrupted_candidates.columns:
        disrupted_candidates["path"] = disrupted_candidates["path"].apply(to_edge_id_list)
    if "flood_links" in disrupted_candidates.columns:
        disrupted_candidates["flood_links"] = disrupted_candidates["flood_links"].apply(
            to_edge_id_list
        )
    disrupted_candidates["od_id"] = disrupted_candidates.index  # numbering od pairs
    # Load road links with damage (e.g., flood depth and damage level)
    road_links = gpd.read_parquet(
        base_path.parent
        / "results"
        / "disruption_analysis"
        / results_variant
        / str(depth_key)
        / "links"
        / f"road_links_{flood_key}.gpq"
    )
    road_links["e_id"] = road_links["e_id"].astype(str)

    # Wire to script-3 outputs (direct damage table by event)
    damage_by_edge, direct_damage_total = load_event_damage_from_script3(base_path, flood_key)
    if len(damage_by_edge) > 0:
        if "damage_level_max" in road_links.columns:
            road_links = road_links.drop(columns=["damage_level_max"])
        road_links = road_links.merge(damage_by_edge, on="e_id", how="left")
        road_links["damage_level_max"] = road_links["damage_level_max"].fillna("no")

        # Prefer road_label from script 3 if present
        if "road_label_x" in road_links.columns and "road_label_y" in road_links.columns:
            road_links["road_label"] = road_links["road_label_y"].fillna(road_links["road_label_x"])
            road_links = road_links.drop(columns=["road_label_x", "road_label_y"])

    # FAF data does not include road_label; create a default
    if "road_label" not in road_links.columns:
        road_links["road_label"] = "road"
        if "road_bridge" in road_links.columns:
            road_links.loc[road_links["road_bridge"].astype(str).str.lower() == "yes", "road_label"] = "bridge"
    road_links["breakpoint_flows"] = road_links["combined_label"].map(
        flow_breakpoint_dict
    )
    initial_road_links_cols = road_links.columns

    # Build flood_links if missing (FAF pipeline uses base scenario odpfc)
    if "flood_links" not in disrupted_candidates.columns:
        if "path" not in disrupted_candidates.columns:
            logging.error("odpfc is missing 'path' column; cannot derive flood_links.")
            sys.exit(1)
        flooded_edges = set(
            road_links.loc[road_links["damage_level_max"] != "no", "e_id"]
        )
        disrupted_candidates["flood_links"] = disrupted_candidates["path"].apply(
            lambda p: [e for e in p if e in flooded_edges]
        )
        disrupted_candidates = disrupted_candidates[
            disrupted_candidates["flood_links"].map(len) > 0
        ].reset_index(drop=True)

    # Recovery analysis loop
    cDict = {}
    out_path = (
        base_path.parent
        / "results"
        / "rerouting_analysis"
        / results_variant
        / str(depth_key)
        / str(flood_key)
    )
    out_path.mkdir(parents=True, exist_ok=True)
    # Load link recovery scenarios (both capacity and speed)
    for day_idx, (scenario_id, event_day) in enumerate(zip(scenarios, conditions)):
        logging.info(f"Rerouting Analysis on Scenario-{scenario_id} of recovery...")
        logging.info(f"Updating edge capacities on D-{event_day} of recovery...")
        road_links["acc_capacity"] = road_links["current_capacity"]
        road_links["acc_capacity"] = road_links.apply(
            lambda row: (
                bridge_recovery(
                    day_idx,
                    row["damage_level_max"],
                    row["current_capacity"],
                    row["acc_capacity"],
                    bridge_recovery_dict,
                )
                if row["road_label"] == "bridge"
                else (
                    ordinary_road_recovery(
                        day_idx,
                        row["damage_level_max"],
                        row["current_capacity"],
                        row["acc_capacity"],
                        road_recovery_dict,
                    )
                )
            ),
            axis=1,
        )
        # Extract disrupted od after road recovery
        logging.info("Extracting disrupted OD pairs...")
        disrupted_od = disrupted_candidates.copy()

        # conduct exploded chunks
        total_disrupted = len(disrupted_od)
        if total_disrupted == 0:
            logging.info("No flooded od pairs detected for current scenario.")
            continue

        max_chunk_size = 10_000
        if max_chunk_size > total_disrupted:
            chunk_size = total_disrupted
        else:
            n_chunk = min(100, max(1, total_disrupted // max_chunk_size))
            chunk_size = max(1, total_disrupted // n_chunk)
        logging.info(f"disrupted_od size: {total_disrupted}")
        logging.info(f"chunk_size: {chunk_size}")

        # create Duckdb to store mid-outputs
        conn = duckdb.connect(db_path)
        conn.execute("DROP TABLE IF EXISTS od_results")  # reset table
        conn.execute("DROP TABLE IF EXISTS edge_flows")  # reset table
        first = True
        for start in tqdm(
            range(0, total_disrupted, chunk_size),
            desc="Processing chunks",
            unit="chunk",
        ):
            chunk = disrupted_od.iloc[start : start + chunk_size].copy()
            chunk = chunk.explode("flood_links")  # list of e_id
            if chunk.empty:
                continue
            chunk = chunk.merge(
                road_links[["e_id", "acc_capacity"]],
                how="left",
                left_on="flood_links",
                right_on="e_id",
            )
            od_df = chunk.groupby(by=["od_id"])["acc_capacity"].min().reset_index()
            if first:
                conn.register("od_df", od_df)
                conn.execute("CREATE TABLE od_results AS SELECT * FROM od_df")
                first = False
            else:
                conn.append("od_results", od_df)
            del chunk, od_df
            gc.collect()

        logging.info("Aggregating final results...")
        # to retrieve min edge capacity for each od
        min_capacity = conn.execute(
            """
            SELECT od_id, MIN(acc_capacity) AS acc_capacity
            FROM od_results
            GROUP BY od_id
        """
        ).df()
        conn.close()
        logging.info("Completing chunk process...")

        # calculate disrupted flow
        disrupted_od = disrupted_od.merge(min_capacity, how="left", on="od_id")
        disrupted_od["disrupted_flow"] = (
            disrupted_od["flow"] - disrupted_od["acc_capacity"]
        ).clip(lower=0)
        disrupted_od = disrupted_od[disrupted_od["disrupted_flow"] > 0].reset_index(
            drop=True
        )
        logging.info(f"The total disrupted flows: {disrupted_od.disrupted_flow.sum()}")

        # estimate the pre-event cost matrix for disrupted flows
        pre_time = (disrupted_od.disrupted_flow * disrupted_od.time_cost_per_flow).sum()
        pre_operate = (
            disrupted_od.disrupted_flow * disrupted_od.operating_cost_per_flow
        ).sum()
        pre_toll = (disrupted_od.disrupted_flow * disrupted_od.toll_cost_per_flow).sum()
        total_pre_cost = pre_time + pre_operate + pre_toll

        # Restore capacity for non-disrupted roads
        logging.info("Calibrate capacity for non-flooded links...")
        disrupted_edge_flow = get_flow_on_edges(
            disrupted_od, "e_id", "path", "disrupted_flow"
        )

        road_links = road_links.merge(disrupted_edge_flow, on="e_id", how="left")
        road_links["disrupted_flow"] = road_links["disrupted_flow"].fillna(0)

        """ Update road link attributes for rerouting analysis
        """
        road_links.current_capacity = road_links.current_capacity.round(0).astype(int)
        road_links.acc_capacity = road_links.acc_capacity.round(0).astype(int)
        road_links.current_flow = road_links.current_flow.round(0).astype(int)
        road_links.disrupted_flow = road_links.disrupted_flow.round(0).astype(int)

        road_links["acc_capacity"] = (
            road_links["acc_capacity"] + road_links["disrupted_flow"]
        )
        road_links["acc_flow"] = (
            road_links["current_flow"] - road_links["disrupted_flow"]
        )

        logging.info("Updating road speed limits...")
        func.update_edge_speed(road_links, inplace=True)
        if event_day == 1:  # apply speed constraint to every road
            road_links["acc_speed"] = road_links[["acc_speed", "max_speed"]].min(axis=1)
        if (
            event_day == 2
        ):  # only apply speed constraint to roads with flooddepth (2-6) meters
            mask = (road_links["flood_depth_max"] >= 2) & (
                road_links["flood_depth_max"] < 6
            )
            road_links.loc[mask, "acc_speed"] = road_links.loc[
                mask, ["acc_speed", "max_speed"]
            ].min(axis=1)
        if event_day == 3:  # only for roads > 6 meters
            mask = road_links["flood_depth_max"] >= 6
            road_links.loc[mask, "acc_speed"] = road_links.loc[
                mask, ["acc_speed", "max_speed"]
            ].min(axis=1)

        # create network (time-consuming when updating network edge index)
        logging.info("Creating igraph network...")
        valid_road_links = road_links[
            (road_links["acc_capacity"] > 0) & (road_links["acc_speed"] > 0)
        ].reset_index(drop=True)
        valid_road_links["from_id"] = valid_road_links["from_id"].astype(str)
        valid_road_links["to_id"] = valid_road_links["to_id"].astype(str)
        network, valid_road_links = func.create_igraph_network(valid_road_links, vehicle_type="car")

        # !!! make sure to pass disrupted flow for rerouting analysis
        disrupted_od.rename(columns={"disrupted_flow": "Car21"}, inplace=True)
        disrupted_od["origin_node"] = disrupted_od["origin_node"].astype(str)
        disrupted_od["destination_node"] = disrupted_od["destination_node"].astype(str)

        # Run flow model
        logging.info("Running flow simulation...")
        isolation_path = out_path / f"trip_isolations_{scenario_id}.pq"
        odpfc_path_iter = out_path / f"odpfc_{scenario_id}.pq"
        valid_road_links, (post_time, post_operate, post_toll, total_post_cost) = func.network_flow_model(
            valid_road_links,  # update this one
            network,
            disrupted_od[
                ["origin_node", "destination_node", "Car21"]
            ],  # update this one
            flow_breakpoint_dict,
            num_of_chunk,
            num_of_cpu,
            db_path,
            iso_out_path=str(isolation_path),
            odpfc_out_path=str(odpfc_path_iter),
            vehicle_type="car",
        )

        # estimate rerouting cost matrix
        rer_time = post_time - pre_time
        rer_operate = post_operate - pre_operate
        rer_toll = post_toll - pre_toll
        rerouting_cost = rer_time + rer_operate + rer_toll
        logging.info(
            f"The original travel costs for disrupted od: $ million {total_pre_cost/ 1e6}"
        )
        logging.info(
            f"The total travel costs after disruption: $ million {total_post_cost/ 1e6}"
        )
        logging.info(
            f"The rerouting cost for scenario {scenario_id}: $ million {rerouting_cost / 1e6}"
        )

        logging.info("Saving results to disk...")

        # rerouting costs
        cDict[scenario_id] = [rer_time, rer_operate, rer_toll, rerouting_cost]
        cost_df = pd.DataFrame.from_dict(
            cDict,
            orient="index",
            columns=["rer_time", "rer_operate", "rer_toll", "rerouting_cost"],
        ).reset_index()
        cost_df.rename(columns={"index": "scenario"}, inplace=True)
        cost_df["direct_damage_total"] = direct_damage_total
        cost_df["combined_total_cost"] = cost_df["rerouting_cost"] + cost_df["direct_damage_total"]
        cost_df.to_csv(out_path / f"rerouting_cost_{scenario_id}.csv", index=False)

        # trip isolations
        if isolation_path.exists():
            isolation_df = pd.read_parquet(isolation_path)
            if "flow" in isolation_df.columns:
                isolation_df = isolation_df.rename(columns={"flow": "Car21"})
        else:
            isolation_df = pd.DataFrame(columns=["origin_node", "destination_node", "Car21"])

        isolation_df = isolation_df[
            (isolation_df.origin_node != isolation_df.destination_node)
            & (isolation_df.Car21 > 0)
        ].reset_index(drop=True)
        isolation_df.to_csv(
            out_path / f"trip_isolations_{scenario_id}.csv",
            index=False,
        )

        # edge flows
        def _to_scalar_float(value):
            if isinstance(value, np.ndarray):
                arr = np.asarray(value).reshape(-1)
                if arr.size == 0:
                    return np.nan
                return float(arr[0])
            if isinstance(value, (list, tuple, set)):
                arr = np.asarray(list(value)).reshape(-1)
                if arr.size == 0:
                    return np.nan
                return float(arr[0])
            if value is None:
                return np.nan
            try:
                return float(value)
            except Exception:
                return np.nan

        valid_road_links = valid_road_links.copy()
        valid_road_links["acc_flow"] = valid_road_links["acc_flow"].apply(_to_scalar_float).astype(float)
        road_links["acc_flow"] = pd.to_numeric(road_links["acc_flow"], errors="coerce").astype(float)
        road_links["current_flow"] = pd.to_numeric(road_links["current_flow"], errors="coerce").astype(float)
        road_links = road_links.set_index("e_id")
        updated_acc_flow = valid_road_links.set_index("e_id")["acc_flow"].astype(float)
        road_links.loc[updated_acc_flow.index, "acc_flow"] = updated_acc_flow.to_numpy(dtype=float)
        road_links = road_links.reset_index()
        road_links["change_flow"] = road_links["acc_flow"] - road_links["current_flow"]
        road_links.to_parquet(out_path / f"edge_flows_{scenario_id}.gpq")

        # reset road_links for next scenario
        road_links = road_links[initial_road_links_cols]

        del disrupted_od
        del disrupted_edge_flow
        del valid_road_links
        gc.collect()

    logging.info("Saving overall rerouting costs to disk...")
    if len(cDict) == 0:
        logging.info("No rerouting results to save.")
        return
    cost_df = pd.DataFrame.from_dict(
        cDict,
        orient="index",
        columns=["rer_time", "rer_operate", "rer_toll", "rerouting_cost"],
    ).reset_index()
    cost_df.rename(columns={"index": "scenario"}, inplace=True)
    cost_df["direct_damage_total"] = direct_damage_total
    cost_df["combined_total_cost"] = cost_df["rerouting_cost"] + cost_df["direct_damage_total"]
    cost_df.to_csv(out_path / "cost_matrix_by_scenario.csv", index=False)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(process)d %(filename)s %(message)s", level=logging.INFO
    )
    try:
        depth_key, event_key, num_of_chunk, num_of_cpu = sys.argv[1:]
        main(int(depth_key), int(event_key), int(num_of_chunk), int(num_of_cpu))
    except (IndexError, ValueError):
        logging.info(
            "Please provide inputs: depth_key, event_key, num_of_chunk, and num_of_cpu!"
        )
        sys.exit(1)
