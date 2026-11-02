"""Turn raw IPEDS files into one tidy table of observations.

One row per institution x year x metric, with the IPEDS status flag and the
exact source file, so any number can be traced back to NCES.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from studio import ipeds
from studio.paths import METRICS_FILE, RAW_DIR

COLUMNS = ["unitid", "year", "metric", "value", "flag", "unit", "survey", "source_file", "source_variable"]

# IPEDS imputation / status flags (X-prefixed columns).
FLAG_MEANINGS = {
    "R": "Reported",
    "A": "Not applicable",
    "B": "Institution left item blank",
    "C": "Analyst corrected reported value",
    "D": "Do not know",
    "G": "Data generated from other data values",
    "H": "Value not derived, data not usable",
    "J": "Logical imputation",
    "K": "Ratio adjustment",
    "L": "Imputed using Group Median procedure",
    "N": "Imputed using Nearest Neighbor procedure",
    "P": "Imputed using Carry Forward procedure",
    "Y": "Specific professional practice program not applicable",
    "Z": "Implied zero",
}


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    survey: str
    variable: str
    flag: str | None
    unit: str
    definition: str


def catalog(path: Path = METRICS_FILE) -> dict[str, Metric]:
    items = yaml.safe_load(Path(path).read_text())
    out = {}
    for item in items:
        m = Metric(**{k: item.get(k) for k in Metric.__dataclass_fields__})
        if m.id in out:
            raise ValueError(f"Duplicate metric id {m.id}")
        out[m.id] = m
    return out


def extract(survey: str, year: int, unitids: list[str] | None = None, raw_dir: Path = RAW_DIR,
            metrics: dict[str, Metric] | None = None) -> pd.DataFrame:
    """Extract all catalog metrics for one survey file and year."""
    metrics = metrics or catalog()
    wanted = [m for m in metrics.values() if m.survey == survey]
    if not wanted:
        return pd.DataFrame(columns=COLUMNS)
    name = ipeds.file_name(survey, year)
    df, member = ipeds.read(name, raw_dir)
    if df["UNITID"].duplicated().any():
        raise ValueError(f"{member} has more than one row per UNITID; it needs a subgroup filter.")
    if unitids is not None:
        df = df[df["UNITID"].isin([str(u) for u in unitids])]

    frames = []
    for m in wanted:
        if m.variable not in df.columns:
            raise KeyError(f"{m.variable} (metric {m.id}) not found in {member}")
        part = pd.DataFrame({
            "unitid": df["UNITID"],
            "year": year,
            "metric": m.id,
            "value": pd.to_numeric(df[m.variable].str.strip(), errors="coerce"),
            "flag": df[m.flag].str.strip() if m.flag and m.flag in df.columns else "",
            "unit": m.unit,
            "survey": survey,
            "source_file": f"{name}.zip/{member}",
            "source_variable": m.variable,
        })
        frames.append(part)
    return pd.concat(frames, ignore_index=True)[COLUMNS]


def check_dictionary(name: str, variables: list[str], raw_dir: Path = RAW_DIR) -> dict[str, str]:
    """Look up variables in the NCES dictionary that ships with a data file.

    Returns {variable: official title}. Raises KeyError for any variable the
    dictionary does not list. Needs {name}_Dict.zip in raw_dir.
    """
    path = raw_dir / f"{name}_Dict.zip"
    with zipfile.ZipFile(path) as zf:
        xlsx = [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls"))]
        if not xlsx:
            raise ValueError(f"No Excel dictionary in {path}")
        with zf.open(xlsx[0]) as fh:
            sheets = pd.read_excel(fh, sheet_name=None, dtype=str)
    varlist = next((s for k, s in sheets.items() if k.strip().lower() == "varlist"), None)
    if varlist is None:
        raise ValueError(f"No 'varlist' sheet in {xlsx[0]}; sheets: {list(sheets)}")
    cols = {c.lower(): c for c in varlist.columns}
    names = varlist[cols["varname"]].str.strip().str.upper()
    titles = varlist[cols.get("vartitle", cols["varname"])]
    lookup = dict(zip(names, titles))
    missing = [v for v in variables if v.upper() not in lookup]
    if missing:
        raise KeyError(f"Not in {name} dictionary: {missing}")
    return {v: lookup[v.upper()] for v in variables}
