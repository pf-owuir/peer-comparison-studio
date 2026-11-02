import pytest

from studio import directory


def test_owu_unitid(hd):
    assert hd.at["204909", "INSTNM"] == "Ohio Wesleyan University"
    assert hd.at["204909", "STABBR"] == "OH"


def test_ids_chatgpt_got_wrong(hd):
    # 204796 was used for OWU and 152530 for Wabash in the earlier prototype.
    assert hd.at["204796", "INSTNM"] == "Ohio State University-Main Campus"
    assert hd.at["152530", "INSTNM"] == "Taylor University"
    assert hd.at["152673", "INSTNM"] == "Wabash College"


def test_verify_rejects_wrong_name(hd):
    with pytest.raises(directory.UnitidError, match="152530"):
        directory.verify(hd, {"152530": "Wabash College"})


def test_verify_rejects_unknown_id(hd):
    with pytest.raises(directory.UnitidError, match="not in"):
        directory.verify(hd, {"999999": "Nowhere College"})


def test_search(hd):
    hits = directory.search(hd, "ohio wesleyan", state="OH")
    assert list(hits["UNITID"]) == ["204909"]
