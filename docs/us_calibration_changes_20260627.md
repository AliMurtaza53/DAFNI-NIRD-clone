# US Calibration Changes — 2026-06-27

Record of changes adapting the (originally UK NIRD) assignment physics and cost
model to the US/CONUS FAF5 network. The network topology and hazard
classification were already US-aware (`convert_faf5_to_nird.py`,
`edge_reclassification_func`, FAF/US hazard branches in
`scripts/2_intersection_analysis.py`); these edits address the remaining
UK-origin **assignment parameters and cost constants**.

Branch context: work done on `feature/lodes-passenger-od`. The code edits below
are git-tracked; the runtime parameter JSONs live in the external data root
(`config.paths.soge_clusters/parameters/`, outside the repo), so their old/new
values are recorded here and mirrored under the repo `parameters/` folder for
traceability.

## Status / caveats

- **Compile:** OK (`py_compile` exit 0).
- **Baseline comparison** (`logs/compare_rerouting_baseline_v2.ps1`, freight day0 event 1,
  `2026-06-27`): see `logs/baseline_compare_v2_20260627_081129/comparison_report.txt`.

| Mode | `NIRD_LEGACY_FREEFLOW_BASELINE` | `rer_time` | `rer_operate` | `rerouting_cost` |
| --- | --- | --- | --- | --- |
| freight day0 | `1` (legacy free-flow pre) | +70 | +1,244 | **+1,314** |
| freight day0 | `0` (consistent loaded pre, **default**) | −599 | −502 | **−1,101** |

Both runs used the same US-calibrated parameters and 3,267 veh-day disrupted flow.
Legacy is **positive** here (not the old June-26 −12,720, which used UK cost
constants). Consistent loaded baseline is still **slightly negative** but much
smaller in magnitude — consistent pre/post share one congestion regime; a negative
value can mean decongestion on rerouted paths outweighs detour costs, not a
free-flow vs loaded artifact.

**Default remains ON** (`NIRD_LEGACY_FREEFLOW_BASELINE=0`) because it is the
methodologically correct apples-to-apples comparison; use the legacy flag only to
reproduce pre-calibration-style free-flow baselines.

---

## Change 1 — Free-flow speed from observed FAF5 link speeds

File: `src/nird/road_revised.py`, `edge_initial_speed_func()`.

- Previously: `free_flow_speeds` always came from the per-class JSON
  (`free_flow_speed_dict`), and urban links were hard-overridden to the urban cap.
- Now: when the network carries observed FAF5 speeds, those are used as the base
  free-flow speed (preferring `AB_FinalSpeed`, then `BA_FinalSpeed`, then
  `Speed_Limit`, all mph, positive values only), falling back to the per-class
  default where missing. Urban links are then capped via `min(free_flow,
  urban_cap)` instead of a hard override.
- Behaviour is unchanged when the network has no observed-speed columns AND the
  urban cap is below the class free-flow speed (the current data case), so this
  is a safe, additive improvement.

## Change 2 — US/HCM transport parameters

Runtime files: `<soge_clusters>/parameters/*.json` (mirrored in repo
`parameters/`). Source basis: US Highway Capacity Manual (HCM 2016) typical
per-lane capacities and speed-flow breakpoints; US typical posted/operating
speeds.

`flow_cap_plph_dict.json` (capacity, passenger-cars/hour/lane):

| Class | Old (UK) | New (US) |
| --- | --- | --- |
| M (freeway) | 2500 | 2400 |
| A_dual (multilane divided) | 1500 | 2200 |
| A_single (two-lane) | 1500 | 1700 |
| B (arterial/local) | 2200 | 1000 |

`flow_breakpoint_dict.json` (speed begins to drop, pc/h/ln):

| Class | Old | New |
| --- | --- | --- |
| M | 1200 | 1400 |
| A_dual | 1080 | 1300 |
| A_single | 1200 | 1100 |
| B | 1200 | 800 |

`free_flow_speed_dict.json` (mph; now a fallback behind observed speeds):

| Class | Old | New |
| --- | --- | --- |
| M | 67 | 70 |
| A_dual | 45 | 60 |
| A_single | 37 | 55 |
| B | 37 | 35 |

`urban_speed_cap.json` (mph):

| Class | Old | New |
| --- | --- | --- |
| M | 47 | 55 |
| A_dual | 30 | 45 |
| A_single | 30 | 35 |
| B | 30 | 30 |

`min_speed_cap.json` (mph; congested floor — raised off the near-zero UK floors
to realistic stop-and-go averages):

| Class | Old | New |
| --- | --- | --- |
| M | 1.0 | 10.0 |
| A_dual | 0.2 | 8.0 |
| A_single | 0.2 | 7.0 |
| B | 0.4 | 5.0 |

## Change 3 — US value-of-time and fuel price

File: `src/nird/constants.py` (+ use site in `road_revised.compute_costs_for_links`).

- Value of time (`VOT_POUND_PER_HOUR`, name kept for backward compatibility; USD
  alias `VOT_USD_PER_HOUR` added). Source: USDOT *Revised Departmental Guidance
  on Valuation of Travel Time* (2022 dollars).

  | Vehicle | Old (GBP→USD) | New (US, USD/hr) |
  | --- | --- | --- |
  | car | 27.19 | 18.50 |
  | lgv | 21.42 | 31.00 |
  | ogv | 25.84 | 32.50 |
  | psv | 16.70 | 18.50 |
  | rail | 48.62 | 22.90 |

- Fuel price: the cost function used a UK pump price of ~1.4 GBP/L × 1.27 ≈
  **$1.78/L** (~$6.73/gal). Replaced with US pump prices via new
  `constants.FUEL_USD_PER_LITRE` (gasoline $0.90/L for car/lgv, diesel $1.04/L
  for ogv/psv/rail). The fuel-consumption polynomial structure
  (`FUEL_LITRE_PER_KM`) is unchanged.

## Change 4 — Consistent loaded-speed pre/post rerouting baseline (default ON)

File: `scripts/4_rerouting_and_recovery_scenario_loop.py`.

- Problem: the pre-event baseline cost used the **free-flow** Pass A per-flow
  costs (`time_cost_per_flow`), while the post-event cost was computed on the
  **congestion-loaded** recovery network. That regime mismatch can produce
  negative rerouting costs (observed in event-1 day-0 results).
- Fix (default): pre-event cost is recomputed by routing the same disrupted OD on
  an **undisrupted network built at the same loaded baseline speeds** (full
  current capacity, no flood speed caps, disrupted edges open). Pre and post
  share one speed/congestion regime.
- Legacy escape hatch: set `NIRD_LEGACY_FREEFLOW_BASELINE=1` to restore the old
  free-flow pre vs loaded post comparison (for reproducing prior run numbers).
  Baseline-run artifacts are written with a `_baseline` suffix.

---

## How to verify and commit

```powershell
$py = "$env:LOCALAPPDATA\miniforge3\envs\nird\python.exe"
& $py -m py_compile src/nird/road_revised.py src/nird/constants.py scripts/4_rerouting_and_recovery_scenario_loop.py
# Script 4 only smoke: legacy vs consistent baseline comparison
Remove-Item Env:NIRD_LEGACY_FREEFLOW_BASELINE -ErrorAction SilentlyContinue  # default ON
git checkout -b feature/us-calibration
git add -A
git commit -m "US calibration: observed link speeds, HCM params, US VOT/fuel, consistent rerouting baseline"
```
