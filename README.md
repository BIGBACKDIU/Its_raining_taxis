# It's raining taxis

NUS DAO2702 group project: how rainfall affects the availability of vacant taxis in Singapore, whether weather data gives useful early warning of unusually low availability, and where free drivers could be positioned ahead of it.

## Layout

- `pipeline/sources.py` – download helpers for data.gov.sg taxi availability, NEA rainfall and NEA 2-hour forecasts (pandas, numpy, requests only)
- `pipeline/grid.py` – metric 500 m / 1 km grid over Singapore (1 km cells nest exactly in 500 m cells)
- `pipeline/fetch_month.py` – downloads one month: `python -m pipeline.fetch_month --month 2026-09 --out out`
- `tests/test_fetch_mock.py` – offline test with fake API payloads: `python tests/test_fetch_mock.py`

Data sources: data.gov.sg (Singapore Open Data Licence), NEA, LTA.

### Step 21: radar rainfall measurement check

Zhuang, Q., Peleg, N., Prein, A., Babovic, V., & Fatichi, S. (2026).
*High-Resolution Radar–Gauge Merged Rainfall Dataset over Singapore (100 m, 5-min and hourly)* (v1).
Zenodo. https://doi.org/10.5281/zenodo.19642566.
Licensed under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
The 2020–2024 five-minute product combines radar and gauges; comparisons with gauges are not independent validation.
Step 21 aggregates its 100 m pixels to the project grid and compares measurements on an identical sample.
Frozen gauge results remain the headline. The 10.1 GB archive and derived data are local, gitignored files.

## Data and plan

- **Start here:** [HANDOFF.md](HANDOFF.md) – full plan, decisions and next steps.
- `.github/workflows/download.yml` downloads Oct 2021 – Sep 2026 (months in `pipeline/months.json`) on GitHub Actions and commits each month to `data/raw/`.
- `data/static/` – Singapore coastline and planning areas (URA 2014, via yinshanyang/singapore) and MRT/LRT stations, exits and lines (cheeaun/sgraildata).
### Step 22: regional storm forecasting on a fresh holdout

Decision 150 registers a separate analysis of the Central Area and five URA regions. Development stops at
September 2025. Only after settings are fixed are models refitted through September 2026; model and code
hashes are committed and pushed before 1-24 October 2026 is scored once. Frozen analyses remain unchanged.

Execution order (the last command must never be rerun):

```sh
.venv/bin/python -m pipeline.fetch_month --month 2026-10 --end-date 2026-10-24 --out data/raw
.venv/bin/python analysis/s22_audit.py
.venv/bin/python analysis/22_regional.py --part develop
.venv/bin/python analysis/22_regional.py --part freeze
# Run tests/wording checks, commit and push the freeze before proceeding.
.venv/bin/python analysis/22_regional.py --part score
```

Local derived inputs, fitted models, preprocessing and saved predictions are in `data/interim/s22/` (ignored).
Tracked `outputs/tables/s22_model_manifest.csv` records their SHA-256 hashes alongside executable sources and
fixed inputs. Scoring verifies hashes, a clean committed tree and the pushed commit, then creates a write-once
marker before opening holdout targets. Outputs are `s22_*.csv` and `s22_weather_gain.png/.svg`. The weather
adjustments to persistence/seasonal benchmarks and the primary pooled materiality rule are explicit in decision
150. Calibration base rates fix alert fractions; October base rates do not set the workload.

### Step 22b: confirmatory backward holdout in 2019

Decision 152 is committed and pushed before download. This analysis applies the unchanged step-22 models
from cc12a0e to 2019, without fitting or tuning. It reuses their seasonal pattern, transformations, residual
CDFs and calibration workloads. The primary outcome is pooled 60-minute storm PR-AUC weather gain for the
15% shortfall label; the original omnibus rule is also reported, with at least eight storm onsets required.

Download January-December 2019 with `pipeline.fetch_month` (30-minute taxi snapshots by default for 2019),
then execute `analysis/22b_backward.py --part audit`. Commit and push the audit and adapter/input hashes
before the single `--part score` invocation. The scorer verifies all original 72 freeze hashes and every
new input hash, then writes a marker before accessing targets. It never fits a forecast model.

Forecast validity is not evidence of availability: late updates are not backdated. Audit tables show the
four registered sample days, every issue's timing, naive future-issue rejections and unavailable slots.
The date/calendar adapter supplies unknown depths for wholly missing rain days and preserves the frozen feature mathematics; 2019 calendar sources and retrieval
limitations are recorded under `data/static/phase3/s22b/`. All results use the separate `s22b_` prefix.
2019 had a different fleet and market; a failed confirmation may reflect an era shift.

### Storm Builder — presentation only

[`sim/v3/index.html`](sim/v3/index.html) is a self-contained interactive synthetic-storm presentation:
real OpenStreetMap road paths, animated model taxis, storm controls and a same-seed policy comparison.
It retains the failed-realism-check banner and the frozen v2 model numbers and parameters.
The original simulation pages remain unchanged. See [`sim/v3/README.md`](sim/v3/README.md) for the build,
checks, road attribution (OpenStreetMap contributors, ODbL) and presentation simplifications.

### Interactive research story — presentation only

Open [`outputs/story/index.html`](outputs/story/index.html) in a browser for a self-contained scrolling
presentation: 15 main graphs, interactive maps and controls, and all 44 saved figures in a searchable
appendix. Fonts, data and images are embedded for offline use. See [`outputs/story/README.md`](outputs/story/README.md)
for presenter controls, rebuild instructions and provenance. Frozen results and models are unchanged.
