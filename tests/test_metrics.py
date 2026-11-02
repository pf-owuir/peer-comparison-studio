import pandas as pd
import pytest

from studio import metrics


@pytest.fixture
def efd(raw_dir):
    return metrics.extract("EFD", 2024, raw_dir=raw_dir)


def value(obs, unitid, metric):
    row = obs[(obs["unitid"] == unitid) & (obs["metric"] == metric)]
    assert len(row) == 1
    return row["value"].iloc[0]


def test_owu_fall_2024_retention(efd):
    # Checked by hand against ef2024d.csv on 2026-11-02.
    assert value(efd, "204909", "ret_ft_cohort") == 426
    assert value(efd, "204909", "ret_ft_retained") == 361
    assert value(efd, "204909", "ret_ft_rate") == 85
    assert value(efd, "204909", "student_faculty_ratio") == 12


def test_wabash_fall_2024_retention(efd):
    assert value(efd, "152673", "ret_ft_rate") == 93
    assert value(efd, "152673", "ret_ft_cohort") == 227


def test_published_rate_matches_counts(efd):
    """IPEDS rate should equal retained / cohort, rounded, for every institution."""
    wide = efd.pivot(index="unitid", columns="metric", values="value")
    ok = wide.dropna(subset=["ret_ft_cohort", "ret_ft_retained", "ret_ft_rate"])
    ok = ok[ok["ret_ft_cohort"] > 0]
    assert len(ok) > 100
    computed = ok["ret_ft_retained"] / ok["ret_ft_cohort"] * 100
    assert ((computed - ok["ret_ft_rate"]).abs() <= 1).all()


def test_rates_in_range(efd):
    rates = efd[efd["metric"].isin(["ret_ft_rate", "ret_pt_rate"])]["value"].dropna()
    assert rates.between(0, 100).all()


def test_one_row_per_institution_metric(efd):
    assert not efd.duplicated(["unitid", "year", "metric"]).any()


def test_every_row_traces_to_source(efd):
    assert (efd["source_file"] == "EF2024D.zip/ef2024d.csv").all()
    assert efd["source_variable"].ne("").all()


def test_flags_are_known(efd):
    flags = set(efd["flag"].dropna()) - {""}
    assert flags <= set(metrics.FLAG_MEANINGS)


def test_catalog_variables_exist_in_file(raw_dir):
    from studio import ipeds
    df, _ = ipeds.read("EF2024D", raw_dir)
    for m in metrics.catalog().values():
        if m.survey == "EFD":
            assert m.variable in df.columns
            assert m.flag in df.columns


def test_check_dictionary(tmp_path):
    """Mimics the NCES *_Dict.zip layout: an Excel file with a 'varlist' sheet."""
    import io
    import zipfile

    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xl:
        pd.DataFrame({"varnumber": [1, 2], "varname": ["UNITID", "RET_PCF"],
                      "varTitle": ["Unique identification number", "Full-time retention rate, 2024"]}
                     ).to_excel(xl, sheet_name="varlist", index=False)
    with zipfile.ZipFile(tmp_path / "EF2024D_Dict.zip", "w") as zf:
        zf.writestr("ef2024d.xlsx", buf.getvalue())

    titles = metrics.check_dictionary("EF2024D", ["RET_PCF"], raw_dir=tmp_path)
    assert titles == {"RET_PCF": "Full-time retention rate, 2024"}
    with pytest.raises(KeyError, match="STUFACR"):
        metrics.check_dictionary("EF2024D", ["STUFACR"], raw_dir=tmp_path)
