# CONUS Freight Desktop Handoff

Use this note to resume the CONUS county-level FAF5 freight run on another
machine with VS Code and Codex.

## Code

Checkout the branch:

```powershell
git checkout full-usa-county-od-matrix
```

Install the Python environment used by the repo, then open the repo in VS Code.
Point Codex to this file and `docs/CONUS_FREIGHT_WORKFLOW.md`.

## Data Bundle

Copy the handoff data bundle from the old machine to the new machine and unzip
it so the folder layout is:

```text
D:\NIRD_Data\soge_clusters
  census_datasets\faf5_od_matrix.pq
  networks\faf5\faf5_road_links.gpq
  networks\faf5\faf5_road_nodes.gpq
  networks\faf5\faf5_centroid_nodes.gpq
  parameters\
  inputs\test_141node_50m\
  tables\
```

Do not copy old `dbs\baseline.duckdb` or `*.wal` files. They were partial
failed runs and are not usable outputs.

## Config

Set `config.json` to the new data path:

```json
{
  "paths": {
    "soge_clusters": "D:\\NIRD_Data\\soge_clusters",
    "base_path": "D:\\NIRD_Data\\soge_clusters",
    "output_path": "results"
  }
}
```

## Recommended First Run

Start with the faster temporary smoke run:

```powershell
.\scripts\launch_conus_freight_workflow_terminal.ps1 -DepthKey 30 -EventKeys 1,2,3 -NumChunks 20 -NumCpu 1 -MaxFlowIterations 1 -ShortestPathDestBatch 0 -RunSensitivity
```

If the machine has plenty of RAM, try `-NumCpu 2` after the single-worker run is
stable. Keep `-ShortestPathDestBatch 0` unless memory errors occur.

Put the DuckDB database on the fastest internal SSD/NVMe available. If needed:

```powershell
.\scripts\launch_conus_freight_workflow_terminal.ps1 -DepthKey 30 -EventKeys 1,2,3 -NumChunks 20 -NumCpu 1 -MaxFlowIterations 1 -ShortestPathDestBatch 0 -BaselineDbPath "E:\NIRD_work\baseline.duckdb" -RunSensitivity
```

## Current State

- The assignment OD is already generated:
  `census_datasets\faf5_od_matrix.pq`
- The FAF5 road network classification was patched from the FAF5 geodatabase
  class codes.
- The old removable-drive run failed at Script 1 because DuckDB lost access to
  `baseline.duckdb.wal` when the drive disconnected.
