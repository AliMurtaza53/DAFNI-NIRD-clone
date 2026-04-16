# OD Inflation Experiment

This note tracks the temporary high-demand run used to stress-test Scripts 1–4 with a larger OD table.

Branch used for this experiment: `experiment/od-inflation-50x`

## Why this exists

The baseline toy OD matrix is freight-only and represents only a small share of all network trips. To test the model under a more realistic passenger+freight demand load, the OD matrix was inflated by a factor of 50.

## What changed

- Original input: `sandbox/fairfax_soge_clusters_toy/inputs/census_datasets/faf5_od_matrix.pq`
- Experimental input used by Script 1: `sandbox/fairfax_soge_clusters_toy/census_datasets/faf5_od_matrix.pq`
- Inflation factor: `50x`
- Original OD file remains unchanged in `inputs/`

## Reproduction steps

1. Copy or regenerate the experimental OD table at `sandbox/fairfax_soge_clusters_toy/census_datasets/faf5_od_matrix.pq`.
2. Run Script 1:
   - `scripts/1_network_flow_model_revision.py 1 8`
3. Run Script 2 for the target event/depth:
   - `scripts/2_intersection_analysis.py 30 1`
4. Run Script 3:
   - `scripts/3_damage_analysis.py`
5. Run Script 4:
   - `scripts/4_rerouting_and_recovery_scenario_loop.py 30 1 1 8`

## Notes

- This is an experiment-only data change, not a code change.
- If you want to preserve the baseline 1x toy run, keep the original file under `inputs/` and avoid overwriting it.
- Suggested versioning pattern for future trials:
   - branch name: `experiment/od-inflation-<factor>x`
   - output root: `sandbox/results/<scenario_name>/revision/<factor>x/`
   - short run note: `<date> | <factor>x OD | any other changes`
