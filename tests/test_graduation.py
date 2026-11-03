"""Graduation Rates (GR2024: fall 2018 cohort) checked against OWU's 2025
IPEDS Data Feedback Report (DFR), figures 17 and 18, and against the GR file's
own internal arithmetic."""

import pandas as pd
import pytest

from studio import metrics


@pytest.fixture(scope="module")
def gr():
    from pathlib import Path
    return metrics.extract("GR", 2024, raw_dir=Path(__file__).parent / "fixtures")


def value(obs, unitid, metric, subgroup="total"):
    row = obs[(obs["unitid"] == unitid) & (obs["metric"] == metric) & (obs["subgroup"] == subgroup)]
    assert len(row) == 1, (unitid, metric, subgroup)
    return row["value"].iloc[0]


def test_owu_counts(gr):
    # gr2024.csv, UNITID 204909, column GRTOTLT
    assert value(gr, "204909", "grs_cohort") == 449
    assert value(gr, "204909", "grs_completers_150") == 263
    assert value(gr, "204909", "grs_transfer_out") == 122
    assert value(gr, "204909", "bach_cohort") == 449
    assert value(gr, "204909", "bach_completers_4yr") == 229
    assert value(gr, "204909", "bach_completers_5th_yr") == 28
    assert value(gr, "204909", "bach_completers_6yr") == 263


def test_owu_matches_dfr_figure_17(gr):
    assert round(value(gr, "204909", "grad_rate_150")) == 59
    assert round(value(gr, "204909", "transfer_out_rate")) == 27


def test_owu_matches_dfr_figure_18_by_race(gr):
    dfr = {"asian": 44, "black_african_american": 39, "hispanic_latino": 52, "white": 63,
           "two_or_more_races": 39, "race_unknown": 80, "us_nonresident": 66}
    for subgroup, expected in dfr.items():
        assert round(value(gr, "204909", "grad_rate_150", subgroup)) == expected, subgroup


def test_dfr_peer_median_figure_17(gr):
    from studio.paths import PEER_GROUP_DIR
    from studio import peers
    g = peers.PeerGroup.from_file(PEER_GROUP_DIR / "dfr_2025.yaml")
    rates = gr[(gr["metric"] == "grad_rate_150") & (gr["subgroup"] == "total") & gr["unitid"].isin(g.members)]
    assert len(rates) == 11
    assert round(rates["value"].median()) == 76


def test_period_label(gr):
    row = gr[(gr["unitid"] == "204909") & (gr["metric"] == "grad_rate_150")].iloc[0]
    assert row["period"] == "Fall 2018 cohort, status Aug 31, 2024"


def test_rates_are_flagged_as_calculated(gr):
    rates = gr[gr["metric"].isin(["grad_rate_150", "bach_grad_rate_6yr"])]
    assert (rates["flag"] == "calc").all()
    assert rates["value"].dropna().between(0, 100).all()


def test_rate_ladder(gr):
    """4-year <= 5-year <= 6-year bachelor's rates for every institution and subgroup."""
    wide = gr[gr["metric"].str.startswith("bach_grad_rate")].pivot_table(
        index=["unitid", "subgroup"], columns="metric", values="value").dropna()
    assert len(wide) > 100
    assert (wide["bach_grad_rate_4yr"] <= wide["bach_grad_rate_5yr"] + 1e-9).all()
    assert (wide["bach_grad_rate_5yr"] <= wide["bach_grad_rate_6yr"] + 1e-9).all()


def test_gender_and_race_sum_to_total(gr):
    counts = gr[gr["metric"] == "grs_cohort"].pivot(index="unitid", columns="subgroup", values="value").dropna()
    assert ((counts["men"] + counts["women"]) == counts["total"]).all()
    races = [c for c in counts.columns if c not in ("total", "men", "women")]
    assert (counts[races].sum(axis=1) == counts["total"]).all()


def test_zero_cohort_gives_blank_rate():
    m = metrics.catalog()
    done = {
        "a": pd.DataFrame({"unitid": ["1", "2"], "subgroup": "total", "value": [5.0, 0.0]}),
        "b": pd.DataFrame({"unitid": ["1", "2"], "subgroup": "total", "value": [10.0, 0.0]}),
    }
    ratio = metrics.Metric(id="r", label="r", survey="GR", unit="percent", definition="",
                           kind="ratio", numerator=("a",), denominator="b")
    out = metrics._ratio_rows(ratio, done).set_index("unitid")["value"]
    assert out["1"] == 50.0
    assert pd.isna(out["2"])
