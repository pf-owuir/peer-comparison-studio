import shutil

import pandas as pd
import pytest

from studio import build, peers, suggest
from studio.paths import PEER_GROUP_DIR


@pytest.fixture(scope="module")
def cands():
    from pathlib import Path
    from studio import directory
    raw = Path(__file__).parent / "fixtures"
    return suggest.candidates(directory.load(2024, raw), 2024, raw)


def test_candidates_have_owu_measures(cands):
    owu = cands.loc["204909"]
    assert owu["INSTNM"] == "Ohio Wesleyan University"
    assert owu["enr_total"] == 1525
    assert owu["ret_ft_rate"] == 85
    assert owu["grad_rate_150"] == 58.6
    assert owu["pct_graduate"] == 0
    assert owu["exp_instruction_per_fte"] == 15050  # DFR figure 24
    # Only active four-year public/private nonprofit colleges with a four-year Carnegie class.
    assert set(cands["CONTROL"]) <= {"1", "2"}
    assert set(cands["C21BASIC"]) <= suggest.FOUR_YEAR_CARNEGIE


def test_suggest_ohio_private(cands):
    s = suggest.suggest(cands, "204909", match=["state", "control"], n=10)
    assert len(s) == 10
    assert "204909" not in s.index
    assert set(s["STABBR"]) == {"OH"}
    assert "The College of Wooster" in set(s["INSTNM"])
    assert s["similarity"].is_monotonic_decreasing
    assert s["similarity"].between(0, 100).all()


def test_suggest_identical_twin_scores_100(cands):
    twin = cands.loc[["204909"]].copy()
    twin.index = ["999999"]
    twin["UNITID"] = "999999"
    s = suggest.suggest(pd.concat([cands, twin]), "204909", n=3)
    assert s.index[0] == "999999" and s["similarity"].iloc[0] == 100


def test_suggest_rejects_unknown_measure(cands):
    with pytest.raises(KeyError):
        suggest.suggest(cands, "204909", ["not_a_measure"])


def test_save_build_delete_custom_group(raw_dir, tmp_path, hd):
    gdir = tmp_path / "groups"
    shutil.copytree(PEER_GROUP_DIR, gdir)
    members = {u: hd.at[u, "INSTNM"] for u in ["206589", "203535", "204909"]}  # benchmark is dropped
    path = peers.save_custom("My Ohio peers!", "204909", members, "Picked by hand", group_dir=gdir)
    assert path.name == "custom_my_ohio_peers.yaml"
    g = peers.load_all(gdir)["custom_my_ohio_peers"]
    assert g.type == "fixed" and g.label == "My Ohio peers!"
    assert set(g.members) == {"206589", "203535"}

    out = tmp_path / "processed"
    build.build([2024], 2024, raw_dir=raw_dir, out_dir=out, group_dir=gdir)
    m = pd.read_csv(out / "peer_groups.csv", dtype={"UNITID": str})
    assert set(m.loc[m["group_id"] == "custom_my_ohio_peers", "UNITID"]) == {"206589", "203535"}
    assert (out / "candidates.csv").exists()

    with pytest.raises(ValueError):
        peers.delete_custom("dfr_2025", gdir)  # built-in groups are protected
    peers.delete_custom("custom_my_ohio_peers", gdir)
    assert "custom_my_ohio_peers" not in peers.load_all(gdir)
