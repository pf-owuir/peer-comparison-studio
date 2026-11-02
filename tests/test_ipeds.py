import io
import zipfile

import pytest

from studio import ipeds
from studio.fetch import parse_years


def test_file_names():
    assert ipeds.file_name("HD", 2024) == "HD2024"
    assert ipeds.file_name("EFD", 2024) == "EF2024D"
    assert ipeds.data_url("EF2024D") == "https://nces.ed.gov/ipeds/datacenter/data/EF2024D.zip"
    assert ipeds.dictionary_url("EF2024D") == "https://nces.ed.gov/ipeds/datacenter/data/EF2024D_Dict.zip"


def test_unknown_survey():
    with pytest.raises(ValueError):
        ipeds.file_name("XYZ", 2024)


def test_parse_years():
    assert parse_years("2015-2017") == [2015, 2016, 2017]
    assert parse_years("2019, 2021-2022") == [2019, 2021, 2022]


def test_revised_csv_preferred():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hd2022.csv", "UNITID\n1\n")
        zf.writestr("hd2022_rv.csv", "UNITID\n1\n")
    with zipfile.ZipFile(buf) as zf:
        assert ipeds.pick_csv(zf) == "hd2022_rv.csv"


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("x.csv", "UNITID\n1\n")
        return FakeResponse(buf.getvalue())


def test_download_skips_existing_and_logs(tmp_path):
    s = FakeSession()
    ipeds.download("EF2024D", raw_dir=tmp_path, session=s)
    assert s.urls == [ipeds.data_url("EF2024D"), ipeds.dictionary_url("EF2024D")]
    assert (tmp_path / "EF2024D.zip").exists()
    assert (tmp_path / "manifest.csv").read_text().count("EF2024D") == 4  # 2 rows x (name, url)
    ipeds.download("EF2024D", raw_dir=tmp_path, session=s)
    assert len(s.urls) == 2  # already there, nothing fetched


def test_download_rejects_non_zip(tmp_path):
    class HtmlSession:
        def get(self, url, timeout):
            return FakeResponse(b"<html>Not found</html>")

    with pytest.raises(RuntimeError, match="did not return a ZIP"):
        ipeds.download("EF1900D", raw_dir=tmp_path, session=HtmlSession(), with_dictionary=False)
