# Network Assignment Path Realization Refactor Plan

## Purpose

This note gives implementation instructions for improving the path-realization bottleneck in the transport network assignment model.

The current implementation computes shortest paths for OD pairs, stores each path as a list of igraph edge indices, and then expands each OD path into one row per path-edge using DuckDB `CROSS JOIN UNNEST(path)` or pandas `explode()`. At full scale, this creates hundreds of millions of logical or physical intermediate rows. The immediate goal is not to redesign the traffic assignment algorithm itself. The goal is to preserve current model semantics while replacing the expensive full path-edge materialization step with a streaming/two-pass accumulator.

Relevant files:

- `src/nird/road_revised.py`
  - Focus functions:
    - `itter_path()`
    - `network_flow_model()`
    - `find_least_cost_path()`
- `scripts/1_network_flow_model_revision.py`
- `scripts/4_rerouting_and_recovery_scenario_loop.py`

## Scope of this first refactor

Do not attempt a full user-equilibrium assignment in this phase.

Do not spend time benchmarking the existing three large-scale options as production candidates:

1. one large DuckDB aggregate over `UNNEST(path)`,
2. chunked DuckDB aggregation over `UNNEST(path)`,
3. chunked pandas `explode/groupby`.

These can remain as reference/fallback implementations, but the first serious development target should be a new streaming implementation that avoids global path-edge materialization.

The required comparison is:

- current status quo implementation on a controlled sample, such as 20,000 OD rows;
- new streaming implementation on the same sample;
- identical or near-identical outputs under the same model settings.

## Core diagnosis

The expensive step is not shortest-path computation alone. The bottleneck is converting this compact OD path table:

```text
origin, destination, flow, path = [edge_idx_1, edge_idx_2, ...]
```

into this expanded incidence table:

```text
origin, destination, flow, edge_idx/e_id, ord, time, fuel, toll, length, capacity
```

If there are `N` OD rows and the average path contains `L` edges, then expansion creates approximately `N × L` path-edge rows. With 9.7 million OD rows and average path length of 40-80 edges, this implies roughly 388-776 million logical rows before grouping, joining, sorting, writing, spilling, or list aggregation.

The following outputs are needed:

1. OD-level path edge lists;
2. OD-level summed costs;
3. edge-level total flow;
4. per-OD minimum capacity ratio along the path;
5. adjusted OD flow;
6. adjusted edge flow for updating `road_links`.

A physical global path-edge table is not required to compute these.

## Preserve current model semantics

The current model is a capacity-constrained, iterative all-or-nothing shortest-path assignment with proportional bottleneck adjustment. It is not a full user-equilibrium assignment.

For each iteration, preserve this sequence exactly:

1. Compute shortest paths using current network weights.
2. Store candidate OD paths and candidate OD flow.
3. Compute unadjusted total candidate flow on each edge.
4. Compute edge ratio:

```text
edge_ratio[e] = min(acc_capacity[e] / total_candidate_flow[e], 1.0)
```

5. For each OD path, compute:

```text
adjust_r[od] = min(edge_ratio[e] for e in path)
adjusted_flow[od] = original_flow[od] × adjust_r[od]
```

6. Assign adjusted flow.
7. Subtract adjusted flow from remaining OD demand.
8. Update edge accumulated flow, residual capacity, speed, and network structure.

Do not compute edge ratios using already-adjusted flow. The denominator must be the unadjusted candidate flow from the current iteration.

## Recommended new implementation

Add a new function in `src/nird/road_revised.py`, for example:

```python
def realize_paths_streaming(
    network,
    road_links,
    conn,
    temp_flow_table: str = "temp_flow_matrix_input",
    od_output_table: str = "temp_flow_matrix",
    edge_output_table: str = "temp_edge_flow",
    chunk_size: int = 100_000,
    persist_debug_tables: bool = False,
) -> None:
    ...
```

The function should replace the production use of `itter_path()` after validation.

### Internal data structures

Use arrays aligned to igraph edge index:

```python
edge_eid = np.asarray(network.es["e_id"])
edge_time = np.asarray(network.es["time_cost"], dtype=np.float64)
edge_fuel = np.asarray(network.es["operating_cost"], dtype=np.float64)
edge_toll = np.asarray(network.es["average_toll_cost"], dtype=np.float64)
edge_length = np.asarray(network.es["length_mile"], dtype=np.float64)
```

Construct `edge_capacity` aligned to igraph edge index. Prefer an explicit mapping:

```python
cap_by_eid = road_links.set_index("e_id")["acc_capacity"].to_dict()
edge_capacity = np.asarray([cap_by_eid.get(eid, 0.0) for eid in edge_eid], dtype=np.float64)
```

Use accumulator arrays:

```python
edge_total_flow = np.zeros(len(edge_eid), dtype=np.float64)
adjusted_edge_flow = np.zeros(len(edge_eid), dtype=np.float64)
```

### Pass 1: OD costs and unadjusted edge totals

Stream `temp_flow_matrix_input` in chunks.

For each OD row:

```python
path = np.asarray(row.path, dtype=np.int64)
flow = float(row.flow)

np.add.at(edge_total_flow, path, flow)

fuel = edge_fuel[path].sum()
time = edge_time[path].sum()
toll = edge_toll[path].sum()
length_mile = edge_length[path].sum()
path_eids = edge_eid[path].tolist()
```

Write an intermediate compact OD-cost table, not a path-edge table. For example:

```text
od_results_iter
----------------
origin VARCHAR
destination VARCHAR
e_id VARCHAR[]
flow DOUBLE
fuel DOUBLE
time DOUBLE
toll DOUBLE
length_mile DOUBLE
```

This table is O(number of OD rows), not O(number of OD-edge incidences).

### Pass 2: OD adjustment and adjusted edge flow

After pass 1:

```python
edge_ratio = np.ones(len(edge_eid), dtype=np.float64)
mask = edge_total_flow > 0
edge_ratio[mask] = np.minimum(edge_capacity[mask] / edge_total_flow[mask], 1.0)
```

Then stream either the original compact path table again or a compact intermediate that still contains path indices.

For each OD row:

```python
path = np.asarray(row.path, dtype=np.int64)
adjust_r = float(edge_ratio[path].min()) if len(path) else 1.0
adjusted_flow = float(row.flow) * adjust_r
np.add.at(adjusted_edge_flow, path, adjusted_flow)
```

Write final `temp_flow_matrix`:

```text
temp_flow_matrix
----------------
origin VARCHAR
destination VARCHAR
e_id VARCHAR[]
flow DOUBLE                # adjusted OD flow
fuel DOUBLE
time DOUBLE
toll DOUBLE
length_mile DOUBLE
```

Also write final `temp_edge_flow`:

```text
temp_edge_flow
--------------
e_id VARCHAR
flow DOUBLE                # adjusted edge flow for this iteration
total_candidate_flow DOUBLE optional
acc_capacity DOUBLE optional
edge_ratio DOUBLE optional
```

### Update `network_flow_model()`

After `realize_paths_streaming()` is called, replace the current edge-flow extraction query:

```sql
SELECT
    e AS e_id,
    SUM(flow) AS flow
FROM (
    SELECT
        flow,
        UNNEST(e_id) AS e
    FROM temp_flow_matrix
) AS t
GROUP BY e
```

with:

```python
temp_edge_flow = conn.execute(
    "SELECT e_id, flow FROM temp_edge_flow WHERE flow > 0"
).fetchdf()
```

This avoids a second global unnest operation.

Keep downstream logic initially unchanged:

```python
road_links = road_links.merge(temp_edge_flow[["e_id", "flow"]], on="e_id", how="left")
road_links["flow"] = road_links["flow"].fillna(0.0)
road_links["acc_flow"] += road_links["flow"]
road_links["acc_capacity"] = road_links["acc_capacity"] - road_links["flow"]
update_edge_speed(road_links, inplace=True)
```

### Add an environment switch

Add an environment variable so old and new implementations can be compared without editing code repeatedly:

```text
NIRD_PATH_REALIZATION_STRATEGY=legacy_compact_sql
NIRD_PATH_REALIZATION_STRATEGY=streaming_arrays
```

Inside `network_flow_model()` or `itter_path()`, route accordingly.

Recommended behavior:

- default to existing strategy until validation passes;
- allow `streaming_arrays` to call the new function;
- keep `legacy_compact_sql` as the status quo comparator.

## Testing and validation plan

Create a new test/experiment script, for example:

```text
scripts/dev_compare_path_realization.py
```

This script should run the current and new path-realization methods on the exact same sample and produce comparable outputs.

### Sample sizes

Run in ascending scale:

1. toy or very small sample, if available;
2. 1,000 OD rows;
3. 20,000 OD rows;
4. optionally 100,000 OD rows after correctness passes.

The 20,000 OD comparison is the main acceptance test before full-scale use.

### Required comparisons

For old vs new `temp_flow_matrix`, compare:

- row count;
- OD key set: `(origin, destination)`;
- path list equality, preserving order;
- adjusted flow;
- fuel;
- time;
- toll;
- length_mile.

For old vs new edge flows, compare:

- edge key set;
- adjusted edge flow by `e_id`;
- total assigned edge flow;
- max absolute difference;
- sum absolute difference.

For model-level conservation, compare:

```text
previous_remaining_flow ≈ assigned_adjusted_flow + new_remaining_flow + newly_isolated_flow
```

For cost conservation, compare:

```text
SUM(flow × fuel)
SUM(flow × time)
SUM(flow × toll)
SUM(flow × fare), if applicable
```

For capacity sanity:

```text
0 <= adjust_r <= 1
adjusted edge flow should not exceed candidate capacity beyond numerical tolerance
```

### Suggested tolerances

Use strict tolerances for small samples:

```python
ABS_TOL = 1e-6
REL_TOL = 1e-9
```

Allow slightly looser floating-point tolerances for larger samples if accumulation order differs:

```python
ABS_TOL = 1e-4
REL_TOL = 1e-8
```

Path list equality should be exact.

## PowerShell transparency requirement

Each run should be launched in a separate, trackable PowerShell window with a descriptive title and a dedicated log file.

Codex should create a helper script, for example:

```text
scripts/dev_run_path_realization_windows.ps1
```

The PowerShell helper should launch separate windows for:

1. legacy 1,000 OD comparison;
2. streaming 1,000 OD comparison;
3. legacy 20,000 OD comparison;
4. streaming 20,000 OD comparison;
5. validation/diff report generation.

Use commands similar to the following pattern:

```powershell
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "$Host.UI.RawUI.WindowTitle = 'NIRD legacy 20k path realization'; " +
  "$env:NIRD_PATH_REALIZATION_STRATEGY='legacy_compact_sql'; " +
  "$env:NIRD_SAMPLE_OD_N='20000'; " +
  "python scripts/dev_compare_path_realization.py --strategy legacy_compact_sql --sample-n 20000 2>&1 | Tee-Object -FilePath logs/path_realization_legacy_20k.log"
)
```

For the new method:

```powershell
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "$Host.UI.RawUI.WindowTitle = 'NIRD streaming 20k path realization'; " +
  "$env:NIRD_PATH_REALIZATION_STRATEGY='streaming_arrays'; " +
  "$env:NIRD_SAMPLE_OD_N='20000'; " +
  "python scripts/dev_compare_path_realization.py --strategy streaming_arrays --sample-n 20000 2>&1 | Tee-Object -FilePath logs/path_realization_streaming_20k.log"
)
```

Do not run a full-scale production model until the 20,000 OD comparison passes.

## Script 4 recovery improvements

Do not refactor script 4 before script 1 path realization is validated. However, design script 1 outputs so script 4 can become cheaper later.

### Near-term script 4 change

Script 4 currently reads baseline/disruption `odpfc`, parses `path`, derives or reads `flood_links`, filters OD paths touching damaged edges, computes disrupted flow, and reroutes only disrupted flow.

Keep this logic for now, but add stronger assumptions and checks:

- `path` must be a normalized list of edge ids;
- `flood_links` must be a normalized list of edge ids;
- `disrupted_candidates` must be non-empty before rerouting;
- total disrupted flow must be less than or equal to candidate flow;
- damage edge ids and path edge ids must use the same dtype/string format.

### Later script 4 improvement: inverted edge-to-OD index

During script 1 baseline assignment, optionally create an inverted index:

```text
edge_idx or e_id -> list of OD row_ids using that edge
```

Then script 4 can identify affected OD paths by:

```python
affected_od_ids = union(edge_to_od_index[e] for e in damaged_edges)
```

This avoids scanning every OD path and checking whether it intersects the damaged edge set.

Possible storage formats:

1. Parquet with columns:

```text
edge_idx, od_ids INT64[]
```

2. CSR-like NumPy arrays:

```text
edge_ptr: length num_edges + 1
od_ids: concatenated OD row ids
```

Do not implement this until the streaming path realization passes validation.

## Deliverables for this development phase

Codex should produce:

1. New function in `src/nird/road_revised.py`:

```text
realize_paths_streaming()
```

2. Environment switch to select old vs new path realization.

3. Update to `network_flow_model()` so it consumes `temp_edge_flow` directly when using streaming mode.

4. New comparison script:

```text
scripts/dev_compare_path_realization.py
```

5. New PowerShell launcher:

```text
scripts/dev_run_path_realization_windows.ps1
```

6. Logs directory convention:

```text
logs/path_realization_*.log
```

7. A validation report output, for example:

```text
results/dev/path_realization_comparison_20k.json
results/dev/path_realization_comparison_20k.csv
```

8. Minimal inline comments explaining why global `UNNEST(path)` materialization is avoided.

## Acceptance criteria

The new streaming implementation is acceptable only if the 20,000 OD sample comparison shows:

1. same OD key set;
2. same ordered path lists;
3. same or near-identical OD adjusted flows;
4. same or near-identical OD costs;
5. same or near-identical edge adjusted flows;
6. same model-level assigned flow and remaining flow;
7. no full-scale `exploded_paths` table is created;
8. runtime and peak disk use are visibly better than the legacy implementation on the same sample.

## What not to do yet

Do not:

- implement Frank-Wolfe or user-equilibrium assignment in this phase;
- rewrite shortest-path computation unless the path-realization tests pass first;
- replace script 4 recovery logic before validating script 1 output compatibility;
- remove legacy path-realization branches before comparisons are complete;
- optimize with multiprocessing until the single-process streaming version is correct;
- run full-scale production until 20,000 OD correctness passes.
