"""Suggest peers: rank institutions by how similar they are to a benchmark.

The build writes data/processed/candidates.csv: one row per active, degree-
granting, four-year public or private nonprofit institution, with directory
fields and a few headline measures for the directory year. `suggest()` ranks
that table by distance from the benchmark on the measures you choose, after
any must-match filters (same state, same Carnegie class, and so on).

Distance: each measure is put on a common scale (z-score across all
candidates; size and dollar measures on a log scale first), then
distance = square root of the average squared difference from the benchmark,
over the measures both institutions report. Similarity = 100 x e^-distance,
so 100 is identical and 60 is about one standard deviation away on average.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from studio import ipeds, metrics
from studio.paths import RAW_DIR

# feature id -> (label, how to compute, log scale?)
FEATURES = {
    "enr_total": ("Fall enrollment", "enr_total", True),
    "pct_graduate": ("% graduate students", ("enr_graduate", "enr_total"), False),
    "pct_fulltime": ("% full-time students", ("enr_fulltime", "enr_total"), False),
    "ret_ft_rate": ("Full-time retention rate", "ret_ft_rate", False),
    "grad_rate_150": ("Graduation rate (150%)", "grad_rate_150", False),
    "student_faculty_ratio": ("Student-to-faculty ratio", "student_faculty_ratio", False),
    "rev_tuition_share": ("Tuition % of core revenue", "rev_tuition_share", False),
    "endowment_per_fte": ("Endowment per FTE", "endowment_per_fte", True),
    "exp_instruction_per_fte": ("Instruction spending per FTE", "exp_instruction_per_fte", True),
}
DEFAULT_FEATURES = ["enr_total", "pct_graduate", "ret_ft_rate", "grad_rate_150",
                    "endowment_per_fte", "exp_instruction_per_fte"]

# must-match filter id -> (label, HD field)
MATCH = {
    "control": ("Same control (public / private)", "CONTROL"),
    "carnegie": ("Same 2021 Carnegie classification", "C21BASIC"),
    "state": ("Same state", "STABBR"),
    "region": ("Same region", "OBEREG"),
    "size": ("Same IPEDS size band", "INSTSIZE"),
}

HD_COLUMNS = ["UNITID", "INSTNM", "CITY", "STABBR", "OBEREG", "CONTROL", "C21BASIC", "INSTSIZE", "LOCALE"]
SURVEYS = ["EFA", "EFD", "GR", "EFIA", "F"]


# 2021 Carnegie basic classes for four-year institutions: doctoral, master's,
# baccalaureate (15-22) and special focus four-year (24-32). Class 23
# (Baccalaureate/Associate's) is left out: mostly two-year colleges that
# award a few bachelor's degrees.
FOUR_YEAR_CARNEGIE = {str(c) for c in [*range(15, 23), *range(24, 33)]}


def universe(hd: pd.DataFrame) -> pd.DataFrame:
    """Active, degree-granting, four-year public and private nonprofit institutions."""
    keep = ((hd["ICLEVEL"] == "1") & (hd["CONTROL"].isin(["1", "2"])) & (hd["CYACTIVE"] == "1")
            & (hd.get("DEGGRANT", pd.Series("1", index=hd.index)) == "1")
            & hd["C21BASIC"].isin(FOUR_YEAR_CARNEGIE))
    return hd[keep]


def candidates(hd: pd.DataFrame, year: int, raw_dir: Path = RAW_DIR,
               extra_ids: set[str] | frozenset = frozenset()) -> pd.DataFrame:
    """Directory fields plus the FEATURES measures for every institution in the universe."""
    pool = universe(hd)
    ids = sorted(set(pool.index) | ({str(i) for i in extra_ids} & set(hd.index)))
    frames = []
    for survey in SURVEYS:
        name = ipeds.file_name(survey, year)
        if ipeds.raw_path(name, raw_dir).exists():
            frames.append(metrics.extract(survey, year, ids, raw_dir))
    obs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=metrics.COLUMNS)
    derived = metrics.derive(obs)
    if len(derived):
        obs = pd.concat([obs, derived], ignore_index=True)
    wide = (obs[obs["subgroup"] == "total"].pivot_table(index="unitid", columns="metric", values="value",
                                                        aggfunc="first"))
    out = hd.loc[ids, [c for c in HD_COLUMNS if c in hd.columns]].copy()
    for fid, (_, how, _) in FEATURES.items():
        if isinstance(how, tuple):
            num, den = (wide.get(c, pd.Series(dtype=float)) for c in how)
            val = (num / den.where(den > 0) * 100).round(1)
        else:
            val = wide.get(how, pd.Series(dtype=float))
        out[fid] = val.reindex(out.index)
    out.attrs["year"] = year
    return out


def _scaled(cands: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    z = pd.DataFrame(index=cands.index)
    for f in features:
        v = pd.to_numeric(cands[f], errors="coerce")
        if FEATURES[f][2]:
            v = np.log(v.where(v > 0))
        sd = v.std()
        z[f] = (v - v.mean()) / sd if sd and not math.isnan(sd) else np.nan
    return z


def suggest(cands: pd.DataFrame, benchmark: str, features: list[str] | None = None,
            match: list[str] | None = None, n: int = 15) -> pd.DataFrame:
    """The n institutions most similar to the benchmark, most similar first.

    Institutions must report at least two thirds of the chosen measures.
    """
    features = features or DEFAULT_FEATURES
    if benchmark not in cands.index:
        raise KeyError(f"{benchmark} is not in the candidate table")
    unknown = [f for f in features if f not in FEATURES]
    if unknown:
        raise KeyError(f"Unknown measures: {unknown}")
    pool = cands.drop(index=benchmark)
    for key in match or []:
        fld = MATCH[key][1]
        pool = pool[pool[fld] == cands.at[benchmark, fld]]

    z = _scaled(cands, features)
    zb = z.loc[benchmark]
    usable = [f for f in features if not pd.isna(zb[f])]
    if not usable:
        raise ValueError(f"{benchmark} reports none of the chosen measures")
    diff = (z.loc[pool.index, usable] - zb[usable]) ** 2
    reported = diff.notna().sum(axis=1)
    dist = np.sqrt(diff.mean(axis=1, skipna=True))
    out = pool[["UNITID", "INSTNM", "CITY", "STABBR"] + features].copy()
    out["measures_compared"] = reported
    out["similarity"] = (100 * np.exp(-dist)).round(1)
    out = out[(reported >= max(1, math.ceil(len(usable) * 2 / 3))) & dist.notna()]
    return out.sort_values(["similarity", "INSTNM"], ascending=[False, True]).head(n)
