"""Apply permanent viz fixes: full OD demand, consolidated USD damage, SCTG panel."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _join_source(lines: list[str]) -> str:
    return "".join(lines)


def _split_source(text: str) -> list[str]:
    if not text.endswith("\n"):
        text += "\n"
    return [line + "\n" for line in text.splitlines()]


def patch_notebook(nb_path: Path) -> None:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))

    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        src = _join_source(cell["source"])

        if "from viz_data_loaders import (" in src and "load_odpfc" in src:
            src = src.replace(
                "from viz_data_loaders import (\n"
                "    load_edge_flows,\n"
                "    load_odpfc,\n"
                "    resolve_edge_flows_path,\n"
                "    resolve_odpfc_path,\n"
                "    should_skip_map_layers,\n"
                "    subset_links_for_map,\n"
                ")",
                "from viz_data_loaders import (\n"
                "    build_flow_validation_table,\n"
                "    event_damage_total_usd,\n"
                "    format_usd_millions,\n"
                "    load_assignment_od_demand,\n"
                "    load_edge_flows,\n"
                "    load_odpfc,\n"
                "    load_sctg_summary,\n"
                "    prepare_damage_for_viz,\n"
                "    resolve_edge_flows_path,\n"
                "    resolve_odpfc_path,\n"
                "    should_skip_map_layers,\n"
                "    subset_links_for_map,\n"
                ")",
            )

        if src.startswith("# Load all data once\n"):
            src = (
                "# Load all data once\n"
                "assignment_od, assignment_od_source = load_assignment_od_demand(input_root)\n"
                "print(f\"Loaded full assignment OD from: {assignment_od_source}\")\n"
                "try:\n"
                "    odpfc, odpfc_source = load_odpfc(results_variant_root)\n"
                "    print(f\"Loaded assigned paths from: {odpfc_source}\")\n"
                "except FileNotFoundError:\n"
                "    odpfc = None\n"
                "    odpfc_source = None\n"
                "    print(\"Assigned OD paths (odpfc) not found; distance-vs-flow plot uses demand only.\")\n"
                "edge_flows, edge_flows_source = load_edge_flows(results_variant_root)\n"
                "print(f\"Loaded edge flows from: {edge_flows_source}\")\n"
                "intersections = pd.read_parquet(paths[\"disruption_intersections\"])\n"
                "road_links = gpd.read_parquet(paths[\"disruption_links\"])\n"
                "map_edge_flows = subset_links_for_map(edge_flows)\n"
                "map_road_links = subset_links_for_map(road_links, flow_col=\"current_flow\")\n"
                "skip_map_layers = should_skip_map_layers(edge_flows)\n"
                "damage_df = prepare_damage_for_viz(pd.read_csv(paths[\"damage_csv\"]))\n"
                "\n"
                "rerouting_costs_path = paths[\"rerouting_costs\"]\n"
                "if rerouting_costs_path.exists():\n"
                "    rerouting_costs = pd.read_csv(rerouting_costs_path).sort_values(\"scenario\")\n"
                "else:\n"
                "    rerouting_costs = pd.DataFrame()\n"
                "\n"
                "print(\"Loaded shapes:\")\n"
                "print(\"  assignment_od:\", assignment_od.shape)\n"
                "print(\"  odpfc:\", None if odpfc is None else odpfc.shape)\n"
                "print(\"  edge_flows:\", edge_flows.shape)\n"
                "print(\"  intersections:\", intersections.shape)\n"
                "print(\"  road_links:\", road_links.shape)\n"
                "print(\"  damage_df:\", damage_df.shape)\n"
                "print(\"  rerouting_costs:\", rerouting_costs.shape)\n"
                "print(\n"
                "    \"  direct damage (consolidated USD):\",\n"
                "    format_usd_millions(event_damage_total_usd(damage_df)),\n"
                ")\n"
            )

        if src.startswith("flow_col = \"flow\" if \"flow\" in odpfc.columns"):
            src = src.replace(
                'flow_col = "flow" if "flow" in odpfc.columns else "Car21"\n'
                "odpfc_step1 = odpfc.copy()\n"
                'odpfc_step1["distance_miles"] = compute_path_distance_miles(odpfc_step1, edge_flows)\n'
                "valid = odpfc_step1[(odpfc_step1[flow_col] > 0) & (odpfc_step1[\"distance_miles\"] > 0)].copy()\n"
                "\n"
                "total_flow = float(odpfc_step1[flow_col].sum())\n"
                "top_share = float(odpfc_step1[flow_col].nlargest(min(10, len(odpfc_step1))).sum() / total_flow) if total_flow > 0 else np.nan\n",
                'flow_col = "flow" if "flow" in assignment_od.columns else "Car21"\n'
                "od_demand_step1 = assignment_od.copy()\n"
                "total_flow = float(od_demand_step1[flow_col].sum())\n"
                "top_share = float(od_demand_step1[flow_col].nlargest(min(10, len(od_demand_step1))).sum() / total_flow) if total_flow > 0 else np.nan\n"
                "valid = pd.DataFrame()\n"
                "if odpfc is not None and \"path\" in odpfc.columns:\n"
                "    odpfc_step1 = odpfc.copy()\n"
                '    odpfc_step1["distance_miles"] = compute_path_distance_miles(odpfc_step1, edge_flows)\n'
                "    path_flow_col = \"flow\" if \"flow\" in odpfc_step1.columns else \"Car21\"\n"
                "    valid = odpfc_step1[(odpfc_step1[path_flow_col] > 0) & (odpfc_step1[\"distance_miles\"] > 0)].copy()\n",
            )
            src = src.replace("odpfc_step1[flow_col]", "od_demand_step1[flow_col]")
            src = src.replace(
                'axes[0].set_xlabel("Flow (vehicles per day)")',
                'axes[0].set_xlabel("Daily truck trips (FAF5 demand)")',
            )
            src = src.replace(
                'axes[0].set_title("OD flow distribution")',
                'axes[0].set_title(f"Full assignment OD demand ({len(od_demand_step1):,} pairs)")',
            )
            src = src.replace(
                '    axes[1].scatter(valid["distance_miles"], valid[flow_col], s=12, alpha=0.35, color="#f58518")\n'
                '    slope, intercept = np.polyfit(valid["distance_miles"].astype(float), np.log1p(valid[flow_col].astype(float)), 1)\n',
                '    axes[1].scatter(valid["distance_miles"], valid[path_flow_col], s=12, alpha=0.35, color="#f58518")\n'
                '    slope, intercept = np.polyfit(valid["distance_miles"].astype(float), np.log1p(valid[path_flow_col].astype(float)), 1)\n',
            )
            src = src.replace(
                'axes[1].set_ylabel("Flow (vehicles per day)")',
                'axes[1].set_ylabel("Daily truck trips")',
            )
            src = src.replace("top_od = odpfc_step1.sort_values", "top_od = od_demand_step1.sort_values")
            src = src.replace(
                'axes[2].set_xlabel("Flow (vehicles per day)")',
                'axes[2].set_xlabel("Daily truck trips")',
            )

        if src.startswith("damage_step3 = damage_df.copy()"):
            src = (
                "damage_step3 = damage_df.copy()\n"
                'damage_step3["total_damage_value"] = pd.to_numeric(\n'
                '    damage_step3["direct_damage_mean_usd"], errors="coerce"\n'
                ").fillna(0.0)\n"
                "damage_fraction_cols = [c for c in damage_step3.columns if c.endswith(\"_damage_fraction\")]\n"
                'damage_step3["total_damage_fraction"] = damage_step3[damage_fraction_cols].apply(pd.to_numeric, errors="coerce").max(axis=1)\n'
                'damage_step3["e_id"] = damage_step3["e_id"].astype(str)\n'
            ) + src.split('damage_step3["e_id"] = damage_step3["e_id"].astype(str)\n', 1)[1]

        if "damage_value_cols = [c for c in dmg.columns if c.endswith(\"_damage_value_mean\")]" in src:
            src = src.replace(
                "    dmg = pd.read_csv(dmg_path)\n"
                "    damage_value_cols = [c for c in dmg.columns if c.endswith(\"_damage_value_mean\")]\n"
                "    if not damage_value_cols:\n"
                "        print(f\"Skipping {scenario_label}: no damage value columns in {dmg_path.name}\")\n"
                "        continue\n"
                "\n"
                "    damage_values = dmg[damage_value_cols].apply(pd.to_numeric, errors=\"coerce\").sum(axis=1, min_count=1).dropna().astype(float)\n",
                "    dmg = prepare_damage_for_viz(pd.read_csv(dmg_path))\n"
                '    damage_values = pd.to_numeric(dmg["direct_damage_mean_usd"], errors="coerce").dropna().astype(float)\n'
                "    if len(damage_values) == 0:\n"
                "        print(f\"Skipping {scenario_label}: no consolidated damage values in {dmg_path.name}\")\n"
                "        continue\n"
                "\n",
            )
            src = src.replace(
                '        "total_damage": float(damage_values.sum(skipna=True)),',
                '        "total_damage": float(event_damage_total_usd(dmg)),',
            )
            src = src.replace(
                '            f"{item[\'label\']} (id={item[\'flood_id\']}) | Total Damage: {item[\'total_damage\']:,.2f} USD | Links: {item[\'n_links\']:,}",',
                '            f"{item[\'label\']} (id={item[\'flood_id\']}) | Total Damage: {format_usd_millions(item[\'total_damage\'])} | Links: {item[\'n_links\']:,}",',
            )

        if "dmg[\"total_damage_value\"] = dmg[damage_value_cols]" in src:
            src = src.replace(
                "    dmg = pd.read_csv(dmg_path)\n"
                "    damage_value_cols = [c for c in dmg.columns if c.endswith(\"_damage_value_mean\")]\n"
                "    if not damage_value_cols:\n"
                "        print(f\"Skipping {scenario_label}: no damage value columns in {dmg_path.name}\")\n"
                "        continue\n"
                "\n"
                '    dmg["e_id"] = dmg["e_id"].astype(str)\n'
                '    dmg["total_damage_value"] = dmg[damage_value_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)\n',
                "    dmg = prepare_damage_for_viz(pd.read_csv(dmg_path))\n"
                '    dmg["e_id"] = dmg["e_id"].astype(str)\n'
                '    dmg["total_damage_value"] = pd.to_numeric(dmg["direct_damage_mean_usd"], errors="coerce").fillna(0.0)\n',
            )

        if "dmg_cols = [c for c in dmg.columns if c.endswith(\"_damage_value_mean\")]" in src:
            src = src.replace(
                "        dmg = pd.read_csv(dmg_path)\n"
                "        dmg_cols = [c for c in dmg.columns if c.endswith(\"_damage_value_mean\")]\n"
                "        if dmg_cols:\n"
                "            total_damage = float(dmg[dmg_cols].apply(pd.to_numeric, errors=\"coerce\").sum(axis=1, min_count=1).sum(skipna=True))\n",
                "        dmg = prepare_damage_for_viz(pd.read_csv(dmg_path))\n"
                "        total_damage = float(event_damage_total_usd(dmg))\n",
            )
            src = src.replace(
                '    axes_b[0].set_ylabel("USD")',
                '    axes_b[0].set_ylabel("USD (consolidated direct damage)")',
            )

        cell["source"] = _split_source(src)

    # Insert SCTG cell after first Step 1 code cell if missing
    has_sctg = any(
        c.get("cell_type") == "code" and "faf5_sctg_industry_breakdown" in _join_source(c.get("source", []))
        for c in nb["cells"]
    )
    if not has_sctg:
        insert_idx = None
        for i, cell in enumerate(nb["cells"]):
            if cell.get("cell_type") == "code" and _join_source(cell.get("source", [])).startswith(
                'flow_col = "flow" if "flow" in assignment_od.columns'
            ) or (
                cell.get("cell_type") == "code"
                and _join_source(cell.get("source", [])).startswith('flow_col = "flow" if "flow" in odpfc.columns')
            ):
                insert_idx = i + 1
                break
        if insert_idx is not None:
            sctg_cell = {
                "cell_type": "code",
                "metadata": {},
                "source": _split_source(
                    "# FAF5 industry (SCTG G5) breakdown from county/regional freight data\n"
                    "try:\n"
                    "    sctg_summary, sctg_source = load_sctg_summary(input_root)\n"
                    "    fig_sctg, ax_sctg = plt.subplots(figsize=(10, 6))\n"
                    "    ax_sctg.barh(sctg_summary[\"industry\"].iloc[::-1], sctg_summary[\"daily_truck_trips\"].iloc[::-1], color=\"#4c78a8\")\n"
                    "    ax_sctg.set_xlabel(\"Daily truck trips\")\n"
                    "    ax_sctg.set_title(f\"FAF5 freight by industry ({sctg_source.name})\")\n"
                    "    ax_sctg.grid(True, axis=\"x\", alpha=0.2)\n"
                    "    fig_sctg.tight_layout()\n"
                    "    save_figure(fig_sctg, step1_fig_dir, \"faf5_sctg_industry_breakdown\")\n"
                    "    plt.show()\n"
                    "except FileNotFoundError as exc:\n"
                    "    print(f\"SCTG breakdown skipped: {exc}\")\n"
                ),
                "outputs": [],
                "execution_count": None,
                "id": "sctg-breakdown-permanent",
            }
            nb["cells"].insert(insert_idx, sctg_cell)

    nb_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Patched {nb_path}")


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    nb_path = repo / "scripts" / "visualizations" / "visualize_pipeline_results.ipynb"
    patch_notebook(nb_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
