import pandas as pd

from nird import freight_od_disaggregation as freight_od


def test_freight_disaggregation_preserves_faf_tons_and_builds_assignment_od():
    faf = pd.DataFrame(
        [
            {
                "dms_orig": 1,
                "dms_dest": 2,
                "dms_mode": 1,
                "sctg2": "01",
                "tons_2021": 10.0,
                "value_2021": 100.0,
            }
        ]
    )
    crosswalk = pd.DataFrame(
        [
            {"faf_zone": 1, "subarea_id": "A"},
            {"faf_zone": 1, "subarea_id": "B"},
            {"faf_zone": 2, "subarea_id": "C"},
        ]
    )
    weights = pd.DataFrame(
        [
            {"subarea_id": "A", "commodity": "01", "production_weight": 3.0, "attraction_weight": 0.0},
            {"subarea_id": "B", "commodity": "01", "production_weight": 1.0, "attraction_weight": 0.0},
            {"subarea_id": "C", "commodity": "01", "production_weight": 0.0, "attraction_weight": 1.0},
        ]
    )
    payload = pd.DataFrame(
        [{"commodity": "01", "truck_type": "combination", "payload_tons": 20.0, "distance_bin": "all"}]
    )

    normalized_faf = freight_od.normalize_faf_flows(faf, year=2021)
    normalized_weights = freight_od.compute_production_attraction_weights(crosswalk, weights)
    tons = freight_od.apply_gravity_disaggregation(normalized_faf, normalized_weights)
    tons = freight_od.balance_to_faf_totals(tons, normalized_faf)
    trucks = freight_od.convert_tons_to_truck_trips(tons, payload)
    assignment = freight_od.build_assignment_od(
        trucks,
        pd.DataFrame(
            [
                {"subarea_id": "A", "node_id": "n1"},
                {"subarea_id": "B", "node_id": "n2"},
                {"subarea_id": "C", "node_id": "n3"},
            ]
        ),
    )
    diagnostics = freight_od.validation_summaries(normalized_faf, tons)

    assert round(tons["tons"].sum(), 6) == 10_000.0
    assert diagnostics["faf_total_preservation"]["within_tolerance"].all()
    assert set(assignment.columns) == {"origin_node", "destination_node", "Car21"}
    assert round(assignment["Car21"].sum(), 6) == round((10_000.0 / 20.0) / 365.0, 6)


def test_schema_markdown_mentions_assignment_contract():
    markdown = freight_od.schema_markdown()

    assert "`origin_node`" in markdown
    assert "`destination_node`" in markdown
    assert "`Car21`" in markdown
