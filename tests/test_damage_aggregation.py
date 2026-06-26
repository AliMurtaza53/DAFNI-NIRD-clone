import pandas as pd

from nird.damage_aggregation import (
    add_consolidated_damage_columns,
    legacy_sum_all_mean_columns_musd,
    total_direct_damage_musd,
)


def test_consolidated_damage_averages_curve_pairs_instead_of_summing():
    row = {
        "C5_river_damage_value_mean": 1.0,
        "C6_river_damage_value_mean": 3.0,
        "C5_surface_damage_value_mean": None,
        "C6_surface_damage_value_mean": None,
    }
    df = pd.DataFrame([row])
    consolidated = add_consolidated_damage_columns(df)
    assert consolidated.loc[0, "direct_damage_mean_musd"] == 2.0
    assert consolidated.loc[0, "direct_damage_mean_usd"] == 2_000_000.0
    assert legacy_sum_all_mean_columns_musd(df) == 4.0
    assert total_direct_damage_musd(df) == 2.0
