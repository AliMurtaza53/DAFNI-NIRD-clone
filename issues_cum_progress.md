# Issues & Cumulative Progress

Summary (concise):

- Fixed:
  - Visualization: split into independent cells; axis/label/layout fixes.
  - Road classification: `convert_faf5_to_nird.py` preserves detailed FAF labels.
  - Centroid connectors: excluded from damage totals in visualization (226,898 links after exclusion).
  - Repo cleanup: sandbox/docs/experiments removed; demo branch prepared.
  - Configuration: `config.json` updated to use local path for user's workflow.

- Remaining / To do:
  1. Move centroid-connector filtering upstream into the converter or damage-analysis script.
  2. Add a batch runner to execute the pipeline end-to-end.
  3. Add lightweight profiling / timing for each pipeline stage.
  4. Validate 500x scenario recovery behavior in script 4.
  5. Add automated tests for data-path validation (CI-friendly).

- Notes:
  - Current `config.json` points to: `C:\\Users\\alimu\\NIRD_Data\\fairfax_soge_clusters_toy`.
  - If collaborators use a different layout, update `config.json`.

