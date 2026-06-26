# LODES passenger OD module

County-to-county passenger demand from Census LEHD LODES8, designed to plug into the
existing NIRD network assignment workflow alongside freight (FAF5).

## Data sources

- LODES8 base URL: https://lehd.ces.census.gov/data/lodes/LODES8/
- LEHD code samples: https://lehd.ces.census.gov/data/lehd-code-samples/sections/lodes/basic_examples.html

## Scope (v1)

- **County-to-county** home-to-work flows only (block OD aggregated with the official geographic crosswalk).
- **Inner-county trips** are included in the county matrix (`origin_county == destination_county`); within-county disaggregation is deferred.
- **Job counts (`S000`)** are used as a daily person-trip proxy for `vehicle_type=car` assignment.

## Files

| File | Role |
|------|------|
| `src/nird/lodes_paths.py` | LODES URL/path helpers, CONUS state list |
| `src/nird/lodes_county_od.py` | Read OD + crosswalk, aggregate to county pairs |
| `scripts/build_lodes_passenger_od.py` | CLI: county OD + optional network mapping |
| `tests/test_lodes_county_od.py` | Unit tests (no network download) |

## Build county OD (single state smoke)

```powershell
python scripts/build_lodes_passenger_od.py --states va --year 2022 --skip-centroid
```

## Build county OD + map to network nodes

```powershell
python scripts/build_lodes_passenger_od.py --states va md dc --year 2022 --force-county
```

Outputs under `lodes_data/processed/` (or `NIRD_LODES_DATA_ROOT/processed/`):

- `lodes_county_od_jt00_2022.parquet`
- `lodes_passenger_centroid_od_jt00_2022.parquet`
- `lodes_passenger_assignment_od_jt00_2022.parquet` (`origin_node`, `destination_node`, `Car21`)

## Environment

| Variable | Purpose |
|----------|---------|
| `NIRD_LODES_DATA_ROOT` | Local mirror of LODES8 files (recommended for CONUS builds) |
| `NIRD_LODES8_BASE_URL` | Override download base URL |

## Multi-state / CONUS notes

For each state, the builder reads **both** `od_main` and `od_aux` files so cross-state commutes are captured once (workplace in state, home anywhere). National county OD is produced by concatenating all states and re-aggregating on `(origin_county, destination_county)`.

Use a local mirror for full CONUS; raw downloads are large and slow.

## Next steps

- Split or downscale inner-county flows to sub-county zones.
- Run Script 1 Pass A with passenger assignment OD (`vehicle_type=car`) alongside freight.
- Hazard/rerouting coupling for passenger mode in Script 4.
