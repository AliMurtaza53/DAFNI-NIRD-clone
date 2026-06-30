# Toy Routing Disruption Tests — Findings & Tightened Assertions

Branch: `test/toy-routing-disruptions`
Status: 46/46 tests passing (~21s)

## What the toy tests cover

Two synthetic networks run the real pipeline (scripts 1 -> 4) in a pytest tmp dir:

- `three_parallel`: n1 -> n2 over 3 parallel edges (`e_fast` / `e_mid` / `e_slow`)
- `braess`: n1 -> n4 diamond (`e_12`, `e_13`, `e_23`, `e_24`, `e_34`)

Both carry freight + passenger demand on the same OD pair, so the tests exercise
the combined freight+passenger assignment and the passenger rerouting path.

## Golden reroute behavior (now asserted exactly)

| Network        | Flooded | Reroutes onto | Freight disrupted | Pass. disrupted | Reroute cost (F / P)   |
|----------------|---------|---------------|-------------------|-----------------|------------------------|
| three_parallel | e_fast  | e_mid         | 12                | 18              | 7.4344571 / 11.1516856 |
| braess         | e_23    | e_13          | 12                | 13              | 5.1605877 / 5.5906367  |

- Baseline edge flows (capacity-limited): 24 veh on each used edge.
- Post-reroute: the flooded edge shows negative `acc_flow` equal to the rerouted
  volume; the gain edge (`e_mid` / `e_13`) gains exactly the disrupted flow.

## Key fixes that made exact assertions possible

1. **Capacity too high -> zero disrupted flow.** Default `A_dual` cap
   (2200 plph x 2 lanes x 24h ~= 105,600) dwarfed toy demand, so
   `disrupted_flow = flow - acc_capacity` clipped to 0 and rerouting never
   triggered. Fix: toy links use `flow_cap_plph = 1`, `lanes = 1` -> 24/day
   capacity, below toy demand.
2. **Braess flooded the whole bbox.** The buffered hazard raster covered every
   edge. Fix: `write_hazard_raster(..., interior_fraction=(0.35, 0.65),
   resolution_m=50)` rasterizes only the interior of `e_23`, so only that edge
   closes.
3. **Script 4 crash on compact path.** `legacy_compact_sql` with
   `NIRD_CREATE_FULL_TEMP_FLOW_MATRIX=0` queried `temp_iteration_costs` before it
   existed. Fix in `src/nird/road_revised.py`: build `temp_iteration_costs` from
   the compact `temp_flow_matrix` when the full matrix is disabled.
4. Toy tests now use `NIRD_PATH_REALIZATION_STRATEGY=streaming_arrays` (the
   production strategy), so the test path matches the real CONUS path.

## Files touched

- `tests/toy_pipeline_fixtures.py` (ToyNetworkSpec golden fields, capacity, hazard)
- `tests/test_toy_pipeline_disruptions.py` (exact assertions)
- `src/nird/road_revised.py` (compact `temp_iteration_costs` fix)
- `src/nird/combined_od.py`, `scripts/1_network_flow_model_revision.py` (passenger OD wiring)

## Production OD wiring (confirmed)

Script 1 merges passenger `Car21` into freight OD *in full* before assignment
(`load_combined_assignment_od`) whenever `NIRD_PASSENGER_OD_PATH` is set and
`NIRD_DISABLE_PASSENGER_OD` is unset. So passenger demand expands the baseline
OD set, not just Script 4 rerouting.

## Full CONUS run plan (freight + passenger, no sampling)

Launcher: `scripts/run_patch5_recovery_conus.ps1` with `-IncludePassenger`.

1. **Bounded smoke (validate wiring + timing):**

   ```powershell
   .\scripts\run_patch5_recovery_conus.ps1 -IncludePassenger -MaxFlowIterations 2
   ```

   Confirm the Pass A log prints `Combined freight+passenger OD: freight=...
   passenger=... total=...` and Script 4 emits both `cost_matrix_by_scenario.csv`
   and `cost_matrix_passenger_by_scenario.csv`.

2. **Full strict-convergence run** (reuse Script 2/3 artifacts from the smoke;
   redo Pass A/Pass B/Script 4 to strict convergence):

   ```powershell
   .\scripts\run_patch5_recovery_conus.ps1 -IncludePassenger -MaxFlowIterations 0 -SkipScript2 -SkipScript3
   ```

   Strict convergence = `NIRD_MAX_FLOW_ITERATIONS=0` with defaults
   `NIRD_MIN_FLOW_PROGRESS_REL=1e-6`, `NIRD_STAGNANT_ITERATIONS=3` (three
   consecutive iterations below the relative-progress threshold).

### Cost caveat

A prior unbounded CONUS run (freight only, ~9.7M ODs) was aborted after 17
iterations / many hours; best `progress_rel` was ~4.3e-4 (~427x above the 1e-6
threshold). Adding passenger demand increases the baseline OD set, so a strict
unbounded run should be expected to take many hours to days.
