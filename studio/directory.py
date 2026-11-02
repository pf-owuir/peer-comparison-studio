"""Institution directory (IPEDS HD file): the source of truth for UNITIDs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from studio import ipeds
from studio.paths import RAW_DIR

# HD fields kept in the directory. Codes are documented in the HD dictionary.
FIELDS = [
    "UNITID", "INSTNM", "IALIAS", "CITY", "STABBR", "OBEREG", "SECTOR", "ICLEVEL", "CONTROL",
    "HLOFFER", "LOCALE", "INSTSIZE", "C21BASIC", "CARNEGIESIZE", "DEGGRANT", "CYACTIVE",
    "LATITUDE", "LONGITUD", "DFRCGID",
]


def load(year: int, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    df, member = ipeds.read(ipeds.file_name("HD", year), raw_dir)
    keep = [c for c in FIELDS if c in df.columns]
    out = df[keep].copy()
    out["INSTNM"] = out["INSTNM"].str.strip()
    out.attrs["source"] = member
    out.attrs["year"] = year
    if out["UNITID"].duplicated().any():
        raise ValueError(f"Duplicate UNITIDs in {member}")
    return out.set_index("UNITID", drop=False)


class UnitidError(ValueError):
    pass


def _norm(name: str) -> str:
    return " ".join(name.lower().replace("&", "and").split())


def verify(directory: pd.DataFrame, expected: dict[str, str]) -> None:
    """Check that every UNITID exists and carries the expected institution name.

    expected maps UNITID -> institution name as written in the source
    (for example the Data Feedback Report). Raises UnitidError listing every
    mismatch, so a wrong ID can never silently attach data to the wrong school.
    """
    problems = []
    for unitid, name in expected.items():
        unitid = str(unitid)
        if unitid not in directory.index:
            problems.append(f"{unitid}: not in {directory.attrs.get('source', 'directory')} (expected {name})")
            continue
        actual = directory.at[unitid, "INSTNM"]
        if _norm(actual) != _norm(name):
            problems.append(f"{unitid}: directory says {actual!r}, expected {name!r}")
    if problems:
        raise UnitidError("UNITID check failed:\n  " + "\n  ".join(problems))


def search(directory: pd.DataFrame, text: str, state: str | None = None) -> pd.DataFrame:
    """Find institutions by name (case-insensitive substring), optionally by state."""
    hits = directory[directory["INSTNM"].str.contains(text, case=False, regex=False)]
    if state:
        hits = hits[hits["STABBR"] == state.upper()]
    return hits[["UNITID", "INSTNM", "CITY", "STABBR"]]
