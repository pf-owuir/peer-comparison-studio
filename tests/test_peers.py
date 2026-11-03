from studio import peers
from studio.paths import PEER_GROUP_DIR

DFR_2025 = {
    "Albion College", "Allegheny College", "Denison University", "DePauw University", "Earlham College",
    "Hope College", "Kalamazoo College", "Kenyon College", "Oberlin College", "The College of Wooster",
    "Wabash College",
}


def test_all_groups_load():
    groups = peers.load_all()
    assert {"dfr_2025", "ohio_private_baccalaureate", "national_liberal_arts_similar_size"} <= set(groups)


def test_dfr_group_matches_report(hd):
    g = peers.PeerGroup.from_file(PEER_GROUP_DIR / "dfr_2025.yaml")
    members = g.resolve(hd)
    assert set(members["INSTNM"]) == DFR_2025
    assert "204909" not in members.index  # benchmark is never its own peer


def test_rule_group_ohio(hd):
    g = peers.PeerGroup.from_file(PEER_GROUP_DIR / "ohio_private_baccalaureate.yaml")
    members = g.resolve(hd)
    assert len(members) > 0
    assert set(members["STABBR"]) == {"OH"}
    assert {"Kenyon College", "Denison University", "The College of Wooster"} <= set(members["INSTNM"])
    assert "204909" not in members.index
    assert members["reason"].str.startswith("Matches rules").all()


def test_rule_group_include_exclude(hd):
    g = peers.PeerGroup(id="t", name="t", type="rules", benchmark="204909",
                        rules={"STABBR": ["OH"], "C21BASIC": [21]},
                        exclude=["203535"], include=["152673"])
    members = g.resolve(hd)
    assert "203535" not in members.index  # Kenyon excluded by hand
    assert "152673" in members.index      # Wabash added by hand
    assert members.at["152673", "reason"] == "Added by hand (include list)"


def test_numeric_range_rule(hd):
    g = peers.PeerGroup(id="t", name="t", type="rules", benchmark="204909",
                        rules={"STABBR": ["OH"], "INSTSIZE": {"min": 2, "max": 2}})
    members = g.resolve(hd)
    assert len(members) > 0
    assert set(hd.loc[members.index, "INSTSIZE"]) == {"2"}


def test_menu_labels_are_short():
    """Sidebar menus cut off long names; every group needs a short label."""
    for g in peers.load_all().values():
        assert g.short_name, g.id
        assert len(g.label) <= 36, g.label
