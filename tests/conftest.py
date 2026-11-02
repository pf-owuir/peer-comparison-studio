from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_dir():
    """NCES-format ZIPs cut down from the real HD2024 and EF2024D files."""
    return FIXTURES


@pytest.fixture
def hd(raw_dir):
    from studio import directory
    return directory.load(2024, raw_dir)
