"""Compare the benchmark institution with a peer group on one metric.

    python -m studio.compare --group dfr_2025 --metric ret_ft_rate --year 2024
    python -m studio.compare --list
"""

from __future__ import annotations

import argparse

import pandas as pd

from studio import metrics, peers
from studio.paths import PROCESSED_DIR


def compare(obs: pd.DataFrame, members: pd.DataFrame, names: dict[str, str], group_id: str, benchmark: str,
            metric: str, year: int) -> tuple[pd.DataFrame, dict]:
    """Return (table of benchmark + peers ranked, summary stats)."""
    ids = set(members.loc[members["group_id"] == group_id, "UNITID"].astype(str)) | {str(benchmark)}
    sel = obs[(obs["metric"] == metric) & (obs["year"] == year) & (obs["unitid"].astype(str).isin(ids))].copy()
    sel["unitid"] = sel["unitid"].astype(str)
    sel["institution"] = sel["unitid"].map(names)
    sel["role"] = sel["unitid"].map(lambda u: "benchmark" if u == str(benchmark) else "peer")
    sel = sel.sort_values("value", ascending=False, na_position="last").reset_index(drop=True)
    sel["rank"] = sel["value"].rank(ascending=False, method="min")

    peer_vals = sel.loc[sel["role"] == "peer", "value"].dropna()
    bench = sel.loc[sel["role"] == "benchmark", "value"]
    def num(x):
        return None if x is None or pd.isna(x) else float(x)

    summary = {
        "benchmark_value": num(bench.iloc[0]) if len(bench) else None,
        "peer_n": int(peer_vals.size),
        "peer_mean": round(float(peer_vals.mean()), 1) if peer_vals.size else None,
        "peer_median": num(peer_vals.median()) if peer_vals.size else None,
        "peer_min": num(peer_vals.min()) if peer_vals.size else None,
        "peer_max": num(peer_vals.max()) if peer_vals.size else None,
        "benchmark_rank": f"{int(sel.loc[sel['role'] == 'benchmark', 'rank'].iloc[0])} of {len(sel)}"
        if len(bench) and pd.notna(bench.iloc[0]) else None,
    }
    return sel[["rank", "institution", "unitid", "role", "value", "flag", "source_file"]], summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--group", default="dfr_2025")
    p.add_argument("--metric", default="ret_ft_rate")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--list", action="store_true", help="List peer groups and metrics")
    args = p.parse_args(argv)

    groups = peers.load_all()
    cat = metrics.catalog()
    if args.list:
        print("Peer groups:")
        for g in groups.values():
            print(f"  {g.id:<40} {g.name}")
        print("Metrics:")
        for m in cat.values():
            print(f"  {m.id:<25} {m.label}")
        return 0

    obs = pd.read_csv(PROCESSED_DIR / "observations.csv", dtype={"unitid": str})
    members = pd.read_csv(PROCESSED_DIR / "peer_groups.csv", dtype={"UNITID": str})
    g = groups[args.group]
    inst = pd.read_csv(PROCESSED_DIR / "institutions.csv", dtype={"UNITID": str})
    names = dict(zip(inst["UNITID"], inst["INSTNM"]))
    table, summary = compare(obs, members, names, g.id, g.benchmark, args.metric, args.year)
    m = cat[args.metric]
    print(f"{m.label}, {args.year} ({m.unit})  |  Peer group: {g.name}")
    print(table.to_string(index=False))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
