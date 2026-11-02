"""Command line: download IPEDS files from NCES.

    python -m studio.fetch --surveys HD EFD --years 2015-2024
    python -m studio.fetch --names HD2024 EF2024D

Files already in data/raw are skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import sys

from studio import ipeds


def parse_years(text: str) -> list[int]:
    years: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (int(x) for x in part.split("-"))
            years.extend(range(min(a, b), max(a, b) + 1))
        elif part:
            years.append(int(part))
    return sorted(set(years))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--surveys", nargs="*", default=[], help=f"Survey keys: {', '.join(ipeds.SURVEY_FILES)}")
    p.add_argument("--years", default="", help="e.g. 2024 or 2015-2024 or 2019,2021-2024")
    p.add_argument("--names", nargs="*", default=[], help="Exact NCES file names, e.g. HD2024 EF2024D")
    p.add_argument("--force", action="store_true", help="Download again even if the file exists")
    p.add_argument("--no-dictionary", action="store_true", help="Skip the *_Dict.zip dictionary files")
    args = p.parse_args(argv)

    names = list(args.names)
    for survey in args.surveys:
        for year in parse_years(args.years):
            names.append(ipeds.file_name(survey, year))
    if not names:
        p.error("Nothing to download: give --surveys with --years, or --names")

    failed = []
    for name in names:
        try:
            path = ipeds.download(name, force=args.force, with_dictionary=not args.no_dictionary)
            print(f"ok    {name:<12} {path}")
        except Exception as exc:  # report every failure, keep going
            failed.append(name)
            print(f"FAIL  {name:<12} {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
