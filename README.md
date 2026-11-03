# Peer Comparison Studio

Benchmark Ohio Wesleyan University (IPEDS UNITID 204909) against peer groups you define, using public IPEDS data downloaded directly from NCES.

Current version (0.5): downloads the official files, checks every institution ID against the IPEDS directory, and builds one tidy table. The table covers enrollment and demographics, retention, graduation, full-time faculty, and finance, with gender and race/ethnicity breakdowns where IPEDS provides them. It compares OWU with any peer group for one year or across years from the command line. The interactive app comes in phase 3.

## Setup (VS Code terminal)

```bash
py -m pip install -r requirements.txt
py -m pytest                # should end with "passed"
```

## Use

On Windows, `py` runs Python. On macOS or Linux, use `python` instead.

```bash
# 1. Download from NCES (files you already have are skipped)
py -m studio.fetch --surveys HD --years 2024
py -m studio.fetch --surveys EFD EFA GR HR F --years 2015-2024

# 2. Build the tidy tables (peer groups resolved with the 2024 directory)
py -m studio.build --years 2015-2024

# 3. Compare OWU with a peer group
py -m studio.compare --list
py -m studio.compare --group dfr_2025 --metric ret_ft_rate --year 2024
py -m studio.compare --group dfr_2025 --metric grad_rate_150 --subgroup women
py -m studio.compare --group ohio_private_baccalaureate --metric bach_grad_rate_4yr --trend
```

`--trend` shows OWU against the peer median for every year built. Peer group membership is fixed to the directory year, so the same institutions are compared across years.

## How it works

| Step | Code | Output |
|---|---|---|
| Download official NCES files, unchanged | `studio/fetch.py`, `studio/ipeds.py` | `data/raw/*.zip`, `data/raw/manifest.csv` (what was downloaded and when) |
| Institution directory (HD) | `studio/directory.py` | UNITID checks: every ID must exist and match its expected name |
| Peer groups | `studio/peers.py`, `config/peer_groups/*.yaml` | `data/processed/peer_groups.csv` with each member and the reason it is included |
| Metrics | `studio/metrics.py`, `config/metrics.yaml` | `data/processed/observations.csv`: one row per institution, year, metric, and subgroup, with the period, IPEDS flag, source file, and source variable |
| Comparison | `studio/compare.py` | OWU vs. peer mean, median, min, max, and rank, for one year or as a trend |
| Build log | `studio/build.py` | `data/processed/build_log.txt`, including warnings when an older file lacks a variable |

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

## Metrics so far

Definitions, source variables, and period labels are in `config/metrics.yaml`. `py -m studio.compare --list` prints them.

**Fall Enrollment, part D (EF D):** `ret_ft_rate`, `ret_ft_cohort`, `ret_ft_retained`, `ret_pt_rate`, `ret_pt_cohort`, `ret_pt_retained`, `student_faculty_ratio`, `entering_undergrads`, `entering_grs_cohort`. Retention rates are used as published by IPEDS. The tests check each one against retained / cohort.

**Graduation Rates (GR):** the GR file for year Y follows the fall Y-6 cohort to August 31 of year Y.
- `grad_rate_150` is the Student Right-to-Know rate shown in the Data Feedback Report: completers of any award within 150% of normal time / adjusted cohort. `transfer_out_rate` works the same way.
- `bach_grad_rate_4yr`, `bach_grad_rate_5yr`, and `bach_grad_rate_6yr` cover the bachelor's-seeking subcohort.
- Every count and rate is also available by subgroup: `men`, `women`, `asian`, `black_african_american`, `hispanic_latino`, `white`, `two_or_more_races`, `american_indian_alaska_native`, `native_hawaiian_pacific_islander`, `race_unknown`, `us_nonresident`.
- Rates are calculated from IPEDS counts and flagged `calc`.

**Fall Enrollment, part A (EF A):** `enr_total`, `enr_undergrad`, `enr_graduate`, `enr_fulltime`, `enr_parttime`, `enr_ft_first_time`, `enr_ft_transfer_in`. The share metrics `enr_share`, `enr_undergrad_share`, and `enr_ft_first_time_share` give each gender and race/ethnicity group as a percent; pick a group with `--subgroup`. When IPEDS has no row for a level (for example, no part-time students), the value is 0 with flag `Z`.

**Full-time instructional staff (HR, `S{year}_IS`):**
- Counts: `fac_ft_instructional` (with subgroups), `fac_with_faculty_status`, `fac_tenured`, `fac_tenure_track`, `fac_non_tenure_track`, `fac_professors`, `fac_associate_professors`, and `fac_assistant_professors`.
- Rates: `fac_pct_tenured`, `fac_pct_tenure_line`, and `fac_ft_instructional_share` by gender and race/ethnicity.

**Finance (F, `F{yy}{yy}_F2`, private nonprofit/FASB reporters only):**
- Revenues: `rev_tuition`, `rev_government`, `rev_private_gifts`, `rev_investment`, `rev_other_core`, and `rev_core`, plus each one's `_share` of core revenues.
- Expenses: `exp_instruction`, `exp_academic_support`, `exp_student_services`, `exp_institutional_support`, `exp_total`, and `exp_instruction_share`.
- Other: `endowment_eoy` and `discount_rate_estimate`.

Year is the fiscal year end. Public (GASB) institutions are not covered yet.

**Validation:** the tests reproduce OWU's 2025 Data Feedback Report figures 3, 4, 16 to 18, and 23. That covers retention (85% vs. a peer median of 88%), graduation (59% vs. 76%), transfer-out (27%), graduation by race/ethnicity, enrollment and its race/ethnicity and gender mix, and the core revenue mix.

## Data rules

- UNITIDs come from the IPEDS directory, never from memory. The tests pin OWU (204909) and the two IDs the earlier prototype got wrong (204796 is Ohio State; 152530 is Taylor University, while Wabash is 152673).
- Variables are mapped once, in `config/metrics.yaml`, and checked against the file. `metrics.check_dictionary()` checks them against the NCES dictionary as well.
- IPEDS status flags (`R` reported, `A` not applicable, imputation codes, and so on) are kept with every value.
- When NCES ships a revised file (`*_rv.csv`) inside a ZIP, the revised file is used.
- NCES labels some releases provisional. The manifest records the download date. Re-download (`--force`) after NCES publishes final data.

## Tests

`tests/fixtures` holds small cuts of the real HD2024, EF2024D, EF2024A, GR2024, S2024_IS, and F2324_F2 files (rebuild with `python scripts/make_fixtures.py`), so the tests run without internet access.

## Roadmap

1. **Data foundation** (done)
2. Ten-year history, graduation rates, enrollment demographics, faculty, and finance (this version). Next: expenses and endowment per FTE (needs the 12-month enrollment file), faculty salaries, public-institution finance
3. Interactive app: peer group manager, comparisons, trends, data dictionary page
4. Excel and PDF exports, executive summary
5. Any benchmark institution, similarity-based peer builder, packaging for outside users

Data source: U.S. Department of Education, National Center for Education Statistics, Integrated Postsecondary Education Data System (IPEDS). This project is not affiliated with or endorsed by NCES.
