"""Fall enrollment (EF2024A), full-time instructional staff (S2024_IS), and
finance (F2324_F2) checked against OWU's 2025 IPEDS Data Feedback Report
(figures 3, 4, and 23) and against each file's own arithmetic."""

from pathlib import Path

import pytest

from studio import metrics, peers
from studio.paths import PEER_GROUP_DIR

FIX = Path(__file__).parent / "fixtures"
DFR = peers.PeerGroup.from_file(PEER_GROUP_DIR / "dfr_2025.yaml")


@pytest.fixture(scope="module")
def efa():
    return metrics.extract("EFA", 2024, raw_dir=FIX)


@pytest.fixture(scope="module")
def hr():
    return metrics.extract("HR", 2024, raw_dir=FIX)


@pytest.fixture(scope="module")
def fin():
    return metrics.extract("F", 2024, raw_dir=FIX)


def value(obs, metric, unitid="204909", subgroup="total"):
    row = obs[(obs["unitid"] == unitid) & (obs["metric"] == metric) & (obs["subgroup"] == subgroup)]
    assert len(row) == 1, (unitid, metric, subgroup)
    return row["value"].iloc[0]


def peer_median(obs, metric, subgroup="total"):
    d = obs[(obs["metric"] == metric) & (obs["subgroup"] == subgroup) & obs["unitid"].isin(DFR.members)]
    assert len(d) == 11
    return d["value"].median()


# --- Enrollment -------------------------------------------------------------

def test_owu_enrollment_dfr_figure_4(efa):
    assert value(efa, "enr_total") == 1525
    assert value(efa, "enr_fulltime") == 1511
    assert value(efa, "enr_parttime") == 14
    assert value(efa, "enr_ft_first_time") == 432
    assert peer_median(efa, "enr_total") == 1738
    assert peer_median(efa, "enr_fulltime") == 1723
    assert peer_median(efa, "enr_parttime") == 24


def test_owu_demographics_dfr_figure_3(efa):
    owu = {"white": 71, "black_african_american": 9, "hispanic_latino": 6, "asian": 2,
           "two_or_more_races": 4, "race_unknown": 1, "us_nonresident": 6, "women": 56}
    med = {"white": 61, "black_african_american": 6, "hispanic_latino": 8, "asian": 3,
           "two_or_more_races": 4, "race_unknown": 2, "us_nonresident": 10, "women": 53}
    for sg in owu:
        assert abs(value(efa, "enr_share", subgroup=sg) - owu[sg]) <= 0.55, sg
        assert abs(peer_median(efa, "enr_share", sg) - med[sg]) <= 0.55, sg


def test_missing_level_row_is_zero(efa):
    """One DFR peer has no part-time row in EF2024A; IPEDS means zero, as the DFR median (24) assumes."""
    pt = efa[(efa["metric"] == "enr_parttime") & (efa["subgroup"] == "total") & efa["unitid"].isin(DFR.members)]
    zeros = pt[pt["flag"] == "Z"]
    assert len(zeros) == 1 and zeros["value"].iloc[0] == 0


def test_enrollment_parts_add_up(efa):
    wide = efa[efa["subgroup"] == "total"].pivot(index="unitid", columns="metric", values="value")
    wide = wide.dropna(subset=["enr_total", "enr_fulltime", "enr_parttime"])
    assert ((wide["enr_fulltime"] + wide["enr_parttime"]) == wide["enr_total"]).all()


def test_race_shares_sum_to_100(efa):
    d = efa[(efa["metric"] == "enr_share") & efa["subgroup"].isin(metrics.RACE_SUBGROUPS)]
    sums = d.groupby("unitid")["value"].sum()
    assert ((sums - 100).abs() < 0.6).all()  # rounding of 10 groups to 0.1


# --- Faculty ----------------------------------------------------------------

def test_owu_faculty_counts(hr):
    # s2024_is.csv, UNITID 204909, HRTOTLT by SISCAT
    assert value(hr, "fac_ft_instructional") == 98
    assert value(hr, "fac_tenured") == 67
    assert value(hr, "fac_tenure_track") == 24
    assert value(hr, "fac_non_tenure_track") == 7
    assert value(hr, "fac_professors") == 34
    assert value(hr, "fac_pct_tenured") == 68.4
    assert value(hr, "fac_ft_instructional", subgroup="women") == 48


def test_tenure_status_adds_up(hr):
    wide = hr[hr["subgroup"] == "total"].pivot(index="unitid", columns="metric", values="value")
    cols = ["fac_tenured", "fac_tenure_track", "fac_non_tenure_track"]
    w = wide.dropna(subset=["fac_with_faculty_status"])
    assert len(w) > 100
    assert (w[cols].fillna(0).sum(axis=1) == w["fac_with_faculty_status"]).all()


# --- Finance ----------------------------------------------------------------

def test_owu_core_revenue_dfr_figure_23(fin):
    owu = {"rev_tuition_share": 24, "rev_government_share": 5, "rev_private_gifts_share": 27,
           "rev_investment_share": 40, "rev_other_core_share": 4}
    med = {"rev_tuition_share": 28, "rev_government_share": 1, "rev_private_gifts_share": 38,
           "rev_investment_share": 31, "rev_other_core_share": 3}
    # The DFR prints whole percents; allow for its rounding (e.g. 27.49 shows as 27).
    for m in owu:
        assert abs(value(fin, m) - owu[m]) <= 0.55, m
        assert abs(peer_median(fin, m) - med[m]) <= 0.55, m


def test_core_revenue_definition(fin):
    """Core revenue = total revenue minus auxiliary, hospital, and independent operations."""
    from studio import ipeds
    df, _ = ipeds.read("F2324_F2", FIX)
    owu = df[df["UNITID"] == "204909"].iloc[0]
    expected = int(owu["F2D16"]) - int(owu["F2D12"]) - int(owu["F2D13"]) - int(owu["F2D14"])
    assert value(fin, "rev_core") == expected == 70424870


def test_owu_finance_values(fin):
    assert value(fin, "endowment_eoy") == 306030062
    assert value(fin, "exp_total") == 77847937
    assert value(fin, "discount_rate_estimate") == 76.5


def test_finance_file_name():
    from studio import ipeds
    assert ipeds.file_name("F", 2024) == "F2324_F2"
    assert ipeds.file_name("F", 2015) == "F1415_F2"
    assert ipeds.file_name("F", 2000) == "F9900_F2"
    assert ipeds.file_name("HR", 2024) == "S2024_IS"
    assert ipeds.file_name("EFA", 2024) == "EF2024A"


# --- 12-month FTE and per-FTE (cross-file) ---------------------------------

@pytest.fixture(scope="module")
def per_fte(fin):
    efia = metrics.extract("EFIA", 2024, raw_dir=FIX)
    import pandas as pd
    obs = pd.concat([fin, efia], ignore_index=True)
    return pd.concat([efia, metrics.derive(obs)], ignore_index=True)


def test_revised_efia_file_used():
    from studio import ipeds
    _, member = ipeds.read("EFIA2024", FIX)
    assert member == "efia2024_rv.csv"


def test_owu_fte_dfr_figure_4(per_fte):
    assert value(per_fte, "fte_12month") == 1475
    assert peer_median(per_fte, "fte_12month") == 1827


def test_expenses_per_fte_dfr_figure_24(per_fte):
    owu = {"exp_instruction_per_fte": 15050, "exp_research_per_fte": 347, "exp_public_service_per_fte": 316,
           "exp_academic_support_per_fte": 4641, "exp_institutional_support_per_fte": 9027,
           "exp_student_services_per_fte": 11867}
    med = {"exp_instruction_per_fte": 20681, "exp_research_per_fte": 517, "exp_public_service_per_fte": 195,
           "exp_academic_support_per_fte": 6296, "exp_institutional_support_per_fte": 9545,
           "exp_student_services_per_fte": 12283}
    for m in owu:
        assert value(per_fte, m) == owu[m], m
        assert peer_median(per_fte, m) == med[m], m


def test_derived_rows_trace_both_files(per_fte):
    row = per_fte[(per_fte["metric"] == "endowment_per_fte") & (per_fte["unitid"] == "204909")].iloc[0]
    assert row["survey"] == "derived" and row["flag"] == "calc"
    assert "EFIA2024.zip" in row["source_file"] and "F2324_F2.zip" in row["source_file"]
    assert row["value"] == round(306030062 / 1475)
