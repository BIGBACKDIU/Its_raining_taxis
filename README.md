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
