# Forecasting tables: how to read them

- `forecast_*.csv` = primary step-6 analysis, pre-specified. Test year (Oct 2025 - Sep 2026) first scored
  2026-10-23 00:08:41; no model was refitted afterwards.
- Subsets marked `post-hoc subset (added after first test scoring)` in `forecast_metrics.csv` and
  `forecast_weather_gain.csv` ("rain starts between issue and target", "heavy rain at target time",
  "cell dry at issue, heavier rain 2-5 km away") were added after the first test scoring. Read them as
  exploratory.
- `s1_*.csv` = secondary analysis S1, added after first test scoring and pre-registered in
  `outputs/decisions.md` (items 55-64) before it was run.
- **Test-year labels.** The baseline that defines "low" in the test year uses each test regime's own level,
  estimated from that regime's own rows: the fit period contains no data from those regimes. Model inputs never
  use that baseline.
- **Base-rate shift.** The primary 1 km deficit label occurs in 18.4% of eligible cell-snapshots in the
  calibration period (Apr - Sep 2025) and 26.5% in the test year. Precision and recall at a fixed alert
  workload, and calibrated probabilities, are affected by this shift; PR-AUC values should be compared with
  each period's base rate.
