"""Rebuild the small test fixtures in tests/fixtures from full NCES files in data/raw.

    python scripts/make_fixtures.py

Keeps OWU, its DFR peers, every Ohio institution, every 2021 Carnegie
Baccalaureate Arts & Sciences college, and two IDs ChatGPT once mistook for
OWU and Wabash (204796, 152530), so tests catch that mistake.
"""

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import directory, ipeds  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "tests" / "fixtures"
KEEP_IDS = {"204909", "168546", "210669", "202523", "150400", "150455", "170301", "170532", "203535",
            "204501", "206589", "152673", "204796", "152530"}


def write_zip(name: str, member: str, df) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    with zipfile.ZipFile(OUT / f"{name}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, buf.getvalue())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hd, hd_member = ipeds.read("HD2024", RAW)
    keep = hd[hd["UNITID"].isin(KEEP_IDS) | (hd["STABBR"] == "OH") | (hd["C21BASIC"] == "21")]
    keep = keep[[c for c in directory.FIELDS if c in keep.columns]]
    write_zip("HD2024", hd_member, keep)
    ef, ef_member = ipeds.read("EF2024D", RAW)
    write_zip("EF2024D", ef_member, ef[ef["UNITID"].isin(set(keep["UNITID"]))])
    print(f"HD2024 fixture: {len(keep)} rows")


if __name__ == "__main__":
    main()
