# %%
from pathlib import Path
import os
import pandas as pd
from nird.damage_aggregation import add_consolidated_damage_columns, total_direct_damage_musd
from nird.utils import get_results_variant, load_config
import warnings
import logging

warnings.simplefilter("ignore")
base_path = Path(load_config()["paths"]["soge_clusters"])
results_root = base_path.parent / "results" / "damage_analysis" / get_results_variant()


# %%
def compute_edge_damage(intersections):
    intersections = add_consolidated_damage_columns(intersections)
    edges_with_damage = (
        intersections.groupby("e_id", as_index=False)["direct_damage_mean_musd"]
        .sum()
        .rename(columns={"direct_damage_mean_musd": "edge_direct_damage_mean_musd"})
    )
    return edges_with_damage


intersections_list = []
for root, _, files in os.walk(
    results_root
):
    for file in files:
        intersection_path = Path(root) / file
        if intersection_path.suffix.lower() == ".csv" and "with_damage_values" in intersection_path.name:
            intersections_list.append(intersection_path)

if not intersections_list:
    logging.warning(f"No damage CSVs found under {results_root}")

event_list = []
min_cost_list = []
max_cost_list = []
for event_path in intersections_list:
    intersections = pd.read_csv(event_path)

    # integrate damage from segments to edges
    edges_with_damage = compute_edge_damage(intersections)
    flood_key = event_path.stem.split("_")[1]
    min_cost = float(edges_with_damage["edge_direct_damage_mean_musd"].sum())
    max_cost = min_cost

    # more attributes should be added
    event_list.append(flood_key)
    min_cost_list.append(min_cost)
    max_cost_list.append(max_cost)

temp = pd.DataFrame(
    {
        "event_id": event_list,
        "damage_cost_min_musd": min_cost_list,
        "damage_cost_max_musd": max_cost_list,
    }
)
temp["damage_cost_mean_musd"] = temp[["damage_cost_min_musd", "damage_cost_max_musd"]].mean(axis=1)
temp["damage_cost_mean_usd"] = temp["damage_cost_mean_musd"] * 1_000_000.0

summary_path = results_root / "damage_summary.csv"
summary_path.parent.mkdir(parents=True, exist_ok=True)
temp.to_csv(summary_path, index=False)
print(f"Saved damage summary to {summary_path}")
print(temp.to_string(index=False))
