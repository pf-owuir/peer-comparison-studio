# Peer Comparison Studio

Benchmark Ohio Wesleyan University (IPEDS UNITID 204909) against peer groups you define, using public IPEDS data downloaded directly from NCES.

This is phase 1, the data foundation. It downloads the official files, checks every institution ID against the IPEDS directory, builds one tidy table of metrics, and compares OWU with any peer group from the command line. The interactive app comes in phase 3.

## Setup (VS Code terminal)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest            # should end with "passed"
```

## Use

```bash
# 1. Download the directory and Fall 2024 retention file (plus their dictionaries) from NCES
python -m studio.fetch --surveys HD EFD --years 2024

# 2. Build the tidy tables
python -m studio.build --years 2024

# 3. Compare OWU with a peer group
python -m studio.compare --list
python -m studio.compare --group dfr_2025 --metric ret_ft_rate --year 2024
python -m studio.compare --group ohio_private_baccalaureate --metric student_faculty_ratio
```

For ten years of history: `python -m studio.fetch --surveys HD EFD --years 2015-2024` and then `python -m studio.build --years 2015-2024`. Files you already have are skipped.

## How it works

| Step | Code | Output |
|---|---|---|
| Download official NCES files, unchanged | `studio/fetch.py`, `studio/ipeds.py` | `data/raw/*.zip`, `data/raw/manifest.csv` (what was downloaded and when) |
| Institution directory (HD) | `studio/directory.py` | UNITID checks: every ID must exist and match its expected name |
| Peer groups | `studio/peers.py`, `config/peer_groups/*.yaml` | `data/processed/peer_groups.csv` with each member and the reason it is included |
| Metrics | `studio/metrics.py`, `config/metrics.yaml` | `data/processed/observations.csv`: one row per institution, year, and metric, with the IPEDS flag, source file, and source variable |
| Comparison | `studio/compare.py` | OWU vs. peer mean, median, min, max, and rank |

`data/raw` and `data/processed` are not committed to Git (see `.gitignore`). Anyone can rebuild them with the two commands above.

## Peer groups

Each file in `config/peer_groups/` is one group. Add a group by copying a file and editing it.

**Fixed list:** institutions named in a source document. Every UNITID is checked against the directory, so a wrong ID stops the build instead of attaching data to the wrong school.

```yaml
id: dfr_2025
type: fixed
benchmark: 204909
members:
  - {unitid: 168546, name: Albion College}
```

**Rules:** filters on IPEDS directory (HD) fields, re-evaluated against whichever directory year you build with. A list means "any of these codes"; `{min, max}` is a numeric range. `exclude` and `include` adjust the result by hand.

```yaml
id: ohio_private_baccalaureate
type: rules
benchmark: 204909
rules:
  STABBR: [OH]
  CONTROL: [2]        # private not-for-profit
  C21BASIC: [21, 22]  # 2021 Carnegie: Baccalaureate Arts & Sciences / Diverse Fields
  INSTSIZE: [2]       # 1,000 - 4,999 students
exclude: []
include: []
```

Current groups: `dfr_2025` (the 11 institutions in OWU's 2025 Data Feedback Report), `ohio_private_baccalaureate` (9 institutions), and `national_liberal_arts_similar_size` (138 institutions). Field codes are listed in the HD dictionary (`data/raw/HD2024_Dict.zip` after fetching).

## Metrics so far (Fall Enrollment, part D)

`ret_ft_rate`, `ret_ft_cohort`, `ret_ft_retained`, `ret_pt_rate`, `ret_pt_cohort`, `ret_pt_retained`, `student_faculty_ratio`, `entering_undergrads`, `gr_cohort`. Definitions are in `config/metrics.yaml`. Retention rates are taken as published by IPEDS. Tests check that each published rate equals retained / cohort for every institution.

## Data rules

- UNITIDs come from the IPEDS directory, never from memory. The tests pin OWU (204909) and the two IDs the earlier prototype got wrong (204796 is Ohio State; 152530 is Taylor University, while Wabash is 152673).
- Variables are mapped once, in `config/metrics.yaml`, and checked against the file. `metrics.check_dictionary()` checks them against the NCES dictionary as well.
- IPEDS status flags (`R` reported, `A` not applicable, imputation codes, and so on) are kept with every value.
- When NCES ships a revised file (`*_rv.csv`) inside a ZIP, the revised file is used.
- NCES labels some releases provisional. The manifest records the download date. Re-download (`--force`) after NCES publishes final data.

## Tests

`tests/fixtures` holds small cuts of the real HD2024 and EF2024D files (rebuild with `python scripts/make_fixtures.py`), so the tests run without internet access.

## Roadmap

1. **Data foundation** (this version)
2. Ten-year history, then Graduation Rates, Fall Enrollment demographics, Human Resources (faculty), and Finance
3. Interactive app: peer group manager, comparisons, trends, data dictionary page
4. Excel and PDF exports, executive summary
5. Any benchmark institution, similarity-based peer builder, packaging for outside users

Data source: U.S. Department of Education, National Center for Education Statistics, Integrated Postsecondary Education Data System (IPEDS). This project is not affiliated with or endorsed by NCES.
