"""Turn raw IPEDS files into one tidy table of observations.

One row per institution x year x metric x subgroup, with the IPEDS status flag
and the exact source file, so any number can be traced back to NCES.

Kinds of metric defined in config/metrics.yaml:
  * value  - one IPEDS variable (or the sum of several), optionally from rows
             selected by a filter (e.g. GRTYPE = 3 in the Graduation Rates file)
  * ratio  - computed from other metrics of the same file, e.g.
             completers / adjusted cohort x 100. Flag is 'calc'.
  * share  - each subgroup of another metric as a percent of its total, e.g.
             percent of students who are women. Flag is 'calc'.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from studio import ipeds
from studio.paths import METRICS_FILE, RAW_DIR

COLUMNS = ["unitid", "year", "period", "metric", "subgroup", "value", "flag", "unit", "survey",
           "source_file", "source_variable"]

# IPEDS imputation / status flags (X-prefixed columns), plus 'calc' for values
# the Studio computes from IPEDS counts.
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
    "calc": "Calculated by the Studio from IPEDS counts",
}

# Columns holding subgroup counts in files that break totals down by gender and
# race/ethnicity. Keys are the Studio's subgroup names.
def _subgroups(prefix: str) -> dict[str, str]:
    """IPEDS uses the same suffixes in GR, EF A, and HR files: GRTOTLT, EFTOTLT, HRTOTLT, ..."""
    return {
        "total": f"{prefix}TOTLT",
        "men": f"{prefix}TOTLM",
        "women": f"{prefix}TOTLW",
        "american_indian_alaska_native": f"{prefix}AIANT",
        "asian": f"{prefix}ASIAT",
        "black_african_american": f"{prefix}BKAAT",
        "hispanic_latino": f"{prefix}HISPT",
        "native_hawaiian_pacific_islander": f"{prefix}NHPIT",
        "white": f"{prefix}WHITT",
        "two_or_more_races": f"{prefix}2MORT",
        "race_unknown": f"{prefix}UNKNT",
        "us_nonresident": f"{prefix}NRALT",
    }


SUBGROUP_COLUMNS = {"GR": _subgroups("GR"), "EFA": _subgroups("EF"), "HR": _subgroups("HR")}
RACE_SUBGROUPS = [k for k in SUBGROUP_COLUMNS["GR"] if k not in ("total", "men", "women")]


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    survey: str
    unit: str
    definition: str
    period: str = "{year}"
    kind: str = "value"
    variable: str | None = None
    variables: tuple = ()  # value kind: sum of these variables instead of one
    of: str | None = None  # share kind: the metric whose subgroups are shared out
    flag: str | None = None
    filter: dict = field(default_factory=dict)
    missing_row_is_zero: bool = False  # filtered files: no row for an institution means 0 (flag Z)
    subgroups: bool = False
    numerator: tuple = ()
    denominator: str | None = None
    scale: float = 100
    digits: int = 1

    def period_for(self, year: int) -> str:
        return self.period.format(year=year, cohort_6yr=year - 6, prior_year=year - 1)


def catalog(path: Path = METRICS_FILE) -> dict[str, Metric]:
    items = yaml.safe_load(Path(path).read_text())
    out: dict[str, Metric] = {}
    for item in items:
        item = dict(item)
        if "numerator" in item:
            num = item["numerator"]
            item["numerator"] = tuple(num if isinstance(num, list) else [num])
        if "variables" in item:
            item["variables"] = tuple(item["variables"])
        if "filter" in item:
            item["filter"] = {k: str(v) for k, v in item["filter"].items()}
        m = Metric(**item)
        if m.id in out:
            raise ValueError(f"Duplicate metric id {m.id}")
        if m.kind == "ratio":
            for dep in (*m.numerator, m.denominator):
                if dep not in out:
                    raise ValueError(f"Ratio {m.id} uses {dep}, which must be defined earlier in the file")
        elif m.kind == "share":
            if m.of not in out:
                raise ValueError(f"Share {m.id} uses {m.of}, which must be defined earlier in the file")
        elif m.kind == "value":
            if bool(m.variable) == bool(m.variables):
                raise ValueError(f"Metric {m.id}: give exactly one of 'variable' or 'variables'")
        else:
            raise ValueError(f"Metric {m.id}: unknown kind {m.kind!r}")
        out[m.id] = m
    return out


def _value_rows(m: Metric, df: pd.DataFrame, year: int, source: str) -> pd.DataFrame:
    rows = df
    for col, val in m.filter.items():
        rows = rows[rows[col].str.strip() == val]
    if rows["UNITID"].duplicated().any():
        raise ValueError(f"Metric {m.id}: more than one row per UNITID after filter {m.filter}")

    filt = "".join(f" where {k}={v}" for k, v in m.filter.items())
    if m.variables:
        nums = [pd.to_numeric(rows[v].str.strip(), errors="coerce") for v in m.variables]
        total = nums[0]
        for n in nums[1:]:
            total = total.add(n, fill_value=0)
        total[pd.concat(nums, axis=1).isna().all(axis=1)] = float("nan")
        return pd.DataFrame({"unitid": rows["UNITID"], "subgroup": "total", "value": total, "flag": "calc",
                             "source_variable": " + ".join(m.variables) + filt})

    columns = {"total": m.variable}
    if m.subgroups:
        columns = SUBGROUP_COLUMNS[m.survey]
    absent = df.loc[~df["UNITID"].isin(rows["UNITID"]), "UNITID"].drop_duplicates() \
        if m.missing_row_is_zero else pd.Series(dtype=str)
    frames = []
    for subgroup, col in columns.items():
        if len(absent):
            frames.append(pd.DataFrame({"unitid": absent, "subgroup": subgroup, "value": 0.0, "flag": "Z",
                                        "source_variable": col + filt + " (no row: implied zero)"}))
        flag_col = (m.flag if subgroup == "total" and m.flag else f"X{col}")
        frames.append(pd.DataFrame({
            "unitid": rows["UNITID"],
            "subgroup": subgroup,
            "value": pd.to_numeric(rows[col].str.strip(), errors="coerce"),
            "flag": rows[flag_col].str.strip() if flag_col in rows.columns else "",
            "source_variable": col + filt,
        }))
    out = pd.concat(frames, ignore_index=True)
    return out


def _ratio_rows(m: Metric, done: dict[str, pd.DataFrame]) -> pd.DataFrame:
    def series(metric_id):
        d = done[metric_id]
        return d.set_index(["unitid", "subgroup"])["value"]

    den = series(m.denominator)
    num = sum((series(n).reindex(den.index) for n in m.numerator), start=pd.Series(0.0, index=den.index))
    value = (num / den.where(den > 0) * m.scale).round(m.digits)
    out = value.rename("value").reset_index()
    out["flag"] = "calc"
    out["source_variable"] = f"({' + '.join(m.numerator)}) / {m.denominator}"
    return out


def _share_rows(m: Metric, done: dict[str, pd.DataFrame]) -> pd.DataFrame:
    d = done[m.of]
    totals = d[d["subgroup"] == "total"].set_index("unitid")["value"]
    out = d[d["subgroup"] != "total"][["unitid", "subgroup", "value"]].copy()
    den = out["unitid"].map(totals)
    out["value"] = (out["value"] / den.where(den > 0) * m.scale).round(m.digits)
    out["flag"] = "calc"
    out["source_variable"] = f"{m.of} subgroup / {m.of} total"
    return out


def extract(survey: str, year: int, unitids: list[str] | None = None, raw_dir: Path = RAW_DIR,
            metrics: dict[str, Metric] | None = None) -> pd.DataFrame:
    """Extract all catalog metrics for one survey file and year.

    Metrics whose variables are missing from this year's file (IPEDS changes
    layouts over time) are skipped and listed in result.attrs['warnings'].
    """
    metrics = metrics or catalog()
    wanted = [m for m in metrics.values() if m.survey == survey]
    if not wanted:
        return pd.DataFrame(columns=COLUMNS)
    name = ipeds.file_name(survey, year)
    df, member = ipeds.read(name, raw_dir)
    if unitids is not None:
        df = df[df["UNITID"].isin([str(u) for u in unitids])]
    source = f"{name}.zip/{member}"

    done: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for m in wanted:
        if m.kind == "value":
            needed = [*([m.variable] if m.variable else []), *m.variables, *m.filter]
            if m.subgroups:
                needed += list(SUBGROUP_COLUMNS[m.survey].values())
            missing = [c for c in needed if c not in df.columns]
            if missing:
                warnings.append(f"{source}: {m.id} skipped, missing {missing}")
                continue
            part = _value_rows(m, df, year, source)
        else:
            deps = [m.of] if m.kind == "share" else [*m.numerator, m.denominator]
            if any(d not in done for d in deps):
                warnings.append(f"{source}: {m.id} skipped, inputs unavailable")
                continue
            part = _share_rows(m, done) if m.kind == "share" else _ratio_rows(m, done)
        part["year"] = year
        part["period"] = m.period_for(year)
        part["metric"] = m.id
        part["unit"] = m.unit
        part["survey"] = survey
        part["source_file"] = source
        done[m.id] = part

    if not done:
        out = pd.DataFrame(columns=COLUMNS)
    else:
        out = pd.concat(done.values(), ignore_index=True)[COLUMNS]
    out.attrs["warnings"] = warnings
    return out


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
