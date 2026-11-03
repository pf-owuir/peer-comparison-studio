"""Smoke test: the app runs on every tab and every topic without errors."""

import os
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from studio import build  # noqa: E402

APP = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture(scope="module")
def processed(tmp_path_factory):
    out = tmp_path_factory.mktemp("processed")
    build.build([2024], 2024, raw_dir=Path(__file__).parent / "fixtures", out_dir=out)
    os.environ["PCS_PROCESSED_DIR"] = str(out)
    yield out
    del os.environ["PCS_PROCESSED_DIR"]


def test_app_runs_every_topic(processed):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.metric[0].value == "1,525"  # OWU fall enrollment 2024
    topics = at.sidebar.radio[0].options
    assert topics == ["Enrollment", "Retention", "Graduation", "Faculty", "Finance", "Finance (per student)"]
    for topic in topics:
        at.sidebar.radio[0].set_value(topic).run()
        assert not at.exception, topic


def test_app_graduation_by_subgroup(processed):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[0].set_value("Graduation").run()
    at.sidebar.selectbox[1].set_value("grad_rate_150").run()
    assert at.metric[0].value == "58.6%"
    at.sidebar.selectbox[2].set_value("asian").run()
    assert not at.exception
    assert at.metric[0].value == "43.8%"  # DFR figure 18: 44%


def test_app_other_peer_group(processed):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.selectbox[0].set_value("ohio_private_baccalaureate").run()
    assert not at.exception
    assert "9 institutions" in at.sidebar.caption[0].value
