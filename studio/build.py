"""Command line: build the tidy observations table from files in data/raw.

    python -m studio.build --years 2015-2024
    python -m studio.build --years 2024 --download   # fetch missing files first

Writes:
  data/processed/observations.csv   one row per institution x year x metric x subgroup
  data/processed/peer_groups.csv    every group's members and why they are in it
  data/processed/institutions.csv   names of every institution in the build
  data/processed/build_log.txt      what was built from which files
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from studio import directory, ipeds, metrics, peers
from studio.fetch import parse_years
from studio.paths import PROCESSED_DIR, RAW_DIR

SURVEYS = ["EFD", "GR"]  # grows as metrics for more surveys are added


def build(years: list[int], directory_year: int, raw_dir: Path = RAW_DIR, out_dir: Path = PROCESSED_DIR,
          download: bool = False) -> pd.DataFrame:
    log: list[str] = []
    needed = [ipeds.file_name("HD", directory_year)] + [ipeds.file_name(s, y) for s in SURVEYS for y in years]
    # Note: download() skips files already in raw_dir.
    if download:
        for name in needed:
            ipeds.download(name, raw_dir=raw_dir)

    hd = directory.load(directory_year, raw_dir)
    log.append(f"Directory: {hd.attrs['source']} ({len(hd)} institutions)")

    groups = peers.load_all()
    benchmarks = {g.benchmark for g in groups.values()}
    member_frames = []
    for g in groups.values():
        m = g.resolve(hd).reset_index(drop=True)
        m.insert(0, "group_id", g.id)
        m.insert(1, "group_name", g.name)
        member_frames.append(m)
        log.append(f"Peer group {g.id}: {len(m)} members")
    members = pd.concat(member_frames, ignore_index=True)
    unitids = sorted(benchmarks | set(members["UNITID"]))

    obs_frames = []
    for survey in SURVEYS:
        for year in years:
            name = ipeds.file_name(survey, year)
            if not ipeds.raw_path(name, raw_dir).exists():
                log.append(f"MISSING {name}: run python -m studio.fetch --names {name}")
                continue
            part = metrics.extract(survey, year, unitids, raw_dir)
            obs_frames.append(part)
            log.append(f"{name}: {part['unitid'].nunique()} institutions, {len(part)} observations")
            log.extend(f"  warning: {w}" for w in part.attrs.get("warnings", []))
    obs = pd.concat(obs_frames, ignore_index=True) if obs_frames else pd.DataFrame(columns=metrics.COLUMNS)

    dupes = obs.duplicated(["unitid", "year", "metric", "subgroup"])
    if dupes.any():
        raise ValueError(f"{dupes.sum()} duplicate institution-year-metric-subgroup rows")

    out_dir.mkdir(parents=True, exist_ok=True)
    obs.to_csv(out_dir / "observations.csv", index=False)
    members.to_csv(out_dir / "peer_groups.csv", index=False)
    hd.loc[unitids, ["UNITID", "INSTNM", "CITY", "STABBR"]].to_csv(out_dir / "institutions.csv", index=False)
    (out_dir / "build_log.txt").write_text("\n".join(log) + "\n")
    print("\n".join(log))
    return obs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--years", required=True, help="e.g. 2024 or 2015-2024")
    p.add_argument("--directory-year", type=int, help="HD year used to resolve peer groups (default: latest year)")
    p.add_argument("--download", action="store_true", help="Download missing NCES files first")
    args = p.parse_args(argv)
    years = parse_years(args.years)
    build(years, args.directory_year or max(years), download=args.download)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
