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
