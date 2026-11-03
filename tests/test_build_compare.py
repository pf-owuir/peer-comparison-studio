import pandas as pd

from studio import build, compare


def test_build_and_compare(raw_dir, tmp_path):
    obs = build.build([2024], 2024, raw_dir=raw_dir, out_dir=tmp_path)
    assert not obs.empty
    members = pd.read_csv(tmp_path / "peer_groups.csv", dtype={"UNITID": str})
    inst = pd.read_csv(tmp_path / "institutions.csv", dtype={"UNITID": str})
    names = dict(zip(inst["UNITID"], inst["INSTNM"]))
    obs = pd.read_csv(tmp_path / "observations.csv", dtype={"unitid": str})

    table, summary = compare.compare(obs, members, names, "dfr_2025", "204909", "ret_ft_rate", 2024)
    assert len(table) == 12
    assert summary["benchmark_value"] == 85
    assert summary["peer_n"] == 11
    assert summary["peer_min"] == 71 and summary["peer_max"] == 93
    assert summary["peer_median"] == 88
    assert summary["benchmark_rank"] == "7 of 12"
    assert table.loc[table["role"] == "benchmark", "institution"].iloc[0] == "Ohio Wesleyan University"

    table, summary = compare.compare(obs, members, names, "dfr_2025", "204909", "grad_rate_150", 2024)
    assert summary["benchmark_value"] == 58.6
    assert summary["peer_median"] == 76.0  # DFR figure 17: 76%
    assert summary["period"] == "Fall 2018 cohort, status Aug 31, 2024"

    # Only 2 peers report transfer-out; rank counts institutions with a value.
    _, summary = compare.compare(obs, members, names, "dfr_2025", "204909", "transfer_out_rate", 2024)
    assert summary["peer_n"] == 2
    assert summary["benchmark_rank"] == "1 of 3"

    _, summary = compare.compare(obs, members, names, "dfr_2025", "204909", "grad_rate_150", 2024, "asian")
    assert round(summary["benchmark_value"]) == 44 and round(summary["peer_median"]) == 74  # DFR figure 18


def test_trend(raw_dir, tmp_path):
    build.build([2024], 2024, raw_dir=raw_dir, out_dir=tmp_path)
    obs = pd.read_csv(tmp_path / "observations.csv", dtype={"unitid": str})
    members = pd.read_csv(tmp_path / "peer_groups.csv", dtype={"UNITID": str})
    t = compare.trend(obs, members, "dfr_2025", "204909", "ret_ft_rate")
    assert t.to_dict("records") == [{"year": 2024, "period": "Fall 2023 cohort, retained to Fall 2024",
                                     "benchmark": 85.0, "peer_median": 88.0, "peer_mean": 85.0, "peer_n": 11}]
