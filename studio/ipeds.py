"""Download and read official IPEDS Complete Data Files from NCES.

Files are stored in data/raw exactly as NCES publishes them (ZIP archives).
Nothing in this module interprets variables; it only fetches and reads.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from pathlib import Path

import pandas as pd

from studio.paths import RAW_DIR

# NCES has used more than one address for Complete Data Files. The current one
# is tried first; the older one is kept as a fallback for files still served there.
NCES_BASE_URLS = [
    "https://nces.ed.gov/ipeds/complete-data-files/{name}.zip",
    "https://nces.ed.gov/ipeds/datacenter/data/{name}.zip",
]

# File-name patterns for the surveys the Studio uses. {year} is the
# collection year that NCES puts in the file name (EF2024D = Fall 2024).
SURVEY_FILES = {
    "HD": "HD{year}",  # Institutional directory
    "EFD": "EF{year}D",  # Entering class, retention, student-to-faculty ratio
    "EFA": "EF{year}A",  # Fall enrollment by race/ethnicity, gender, level
    "GR": "GR{year}",  # Graduation rates
    # Finance (F) and Human Resources (HR) are added in phase 2.
}

MANIFEST = "manifest.csv"


def file_name(survey: str, year: int) -> str:
    """Return the NCES file name, e.g. file_name('EFD', 2024) -> 'EF2024D'."""
    try:
        return SURVEY_FILES[survey].format(year=year)
    except KeyError as exc:
        raise ValueError(f"Unknown survey {survey!r}. Known: {sorted(SURVEY_FILES)}") from exc


def data_urls(name: str) -> list[str]:
    return [base.format(name=name) for base in NCES_BASE_URLS]


def dictionary_urls(name: str) -> list[str]:
    return data_urls(f"{name}_Dict")


def _get_zip(http, urls: list[str]) -> tuple[bytes, str]:
    """Try each address in turn; return (content, url) of the first ZIP found."""
    errors = []
    for url in urls:
        try:
            resp = http.get(url, timeout=120)
            resp.raise_for_status()
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue
        if zipfile.is_zipfile(io.BytesIO(resp.content)):
            return resp.content, url
        errors.append(f"{url}: response was not a ZIP file")
    raise RuntimeError("Could not download from NCES:\n  " + "\n  ".join(errors))


def raw_path(name: str, raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / f"{name}.zip"


def download(name: str, raw_dir: Path = RAW_DIR, force: bool = False, with_dictionary: bool = True,
             session=None) -> Path:
    """Download one NCES data file (and its dictionary) into raw_dir.

    Skips the download if the file is already there, unless force=True.
    Records every download in data/raw/manifest.csv.
    """
    import requests

    raw_dir.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    dest = raw_path(name, raw_dir)
    if force or not dest.exists():
        content, url = _get_zip(http, data_urls(name))
        dest.write_bytes(content)
        _record(raw_dir, name, url, len(content))

    if with_dictionary:
        dict_dest = raw_dir / f"{name}_Dict.zip"
        if force or not dict_dest.exists():
            try:
                content, url = _get_zip(http, dictionary_urls(name))
                dict_dest.write_bytes(content)
                _record(raw_dir, f"{name}_Dict", url, len(content))
            except RuntimeError as exc:
                # The data file is what matters; a missing dictionary is reported, not fatal.
                print(f"warn  {name}_Dict not downloaded: {exc}")
    return dest


def _record(raw_dir: Path, name: str, url: str, size: int) -> None:
    manifest = raw_dir / MANIFEST
    new = not manifest.exists()
    with manifest.open("a", newline="") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(["file", "url", "bytes", "downloaded_at_utc"])
        writer.writerow([name, url, size, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")])


def pick_csv(zf: zipfile.ZipFile) -> str:
    """Choose the CSV inside an NCES ZIP.

    When NCES revises a file it ships both the original and a '_rv' CSV.
    The revised file is the one to use.
    """
    csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csvs:
        raise ValueError(f"No CSV in archive: {zf.namelist()}")
    revised = [n for n in csvs if n.lower().endswith("_rv.csv")]
    return (revised or csvs)[0]


def read(name: str, raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, str]:
    """Read an NCES file from raw_dir. Returns (dataframe, csv name used).

    All columns are read as text so that codes such as '-2' and status flags
    are never silently converted; callers convert the fields they need.
    """
    path = raw_path(name, raw_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python -m studio.fetch {name}")
    with zipfile.ZipFile(path) as zf:
        member = pick_csv(zf)
        raw = zf.read(member)
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    df.columns = [c.strip().upper() for c in df.columns]
    df["UNITID"] = df["UNITID"].str.strip()
    return df, member
