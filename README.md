# It's raining taxis

NUS DAO2702 group project: how rainfall affects the availability of vacant taxis in Singapore, whether weather data gives useful early warning of unusually low availability, and where free drivers could be positioned ahead of it.

## Layout

- `pipeline/sources.py` – download helpers for data.gov.sg taxi availability, NEA rainfall and NEA 2-hour forecasts (pandas, numpy, requests only)
- `pipeline/grid.py` – metric 500 m / 1 km grid over Singapore (1 km cells nest exactly in 500 m cells)
- `pipeline/fetch_month.py` – downloads one month: `python -m pipeline.fetch_month --month 2026-09 --out out`
- `tests/test_fetch_mock.py` – offline test with fake API payloads: `python tests/test_fetch_mock.py`

Data sources: data.gov.sg (Singapore Open Data Licence), NEA, LTA.
