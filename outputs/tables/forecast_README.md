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

## Changes after the independent review of commit aac26fe

- **Retrospective labels.** Every forecasting table that does not say otherwise is evaluated against
  retrospective labels (test-regime levels estimated from test-year rows; change points found on all five
  years). `forecast_eval_both_labels.csv` and `forecast_eval_lead_both_labels.csv` add an issue-time-knowable
  label (baseline = pattern at t+h x trailing 7-day level known at t), scored without refitting.
- **Fixed workload.** The main operational metric is now top-K per issue time (K = 19 of 374 cells, 6 of 129
  blocks, 2 of 49 planning areas = 5% of eligible units), identical for every model. For the deficit label the
  ranking set is the cells with expected >= 4 known at issue time (the label is undefined elsewhere); for the NB
  label all units. The earlier calibration-threshold metrics (thresholds on labelled rows, so about 2% of
  eligible cell-snapshots and different alert rates per model) are kept only in
  `forecast_calibration_threshold.csv` and `forecast_lead_times_calibration_threshold.csv`.
  `*_allcells_ranking.csv` keep a first corrected run that ranked all cells, including cells whose label is
  undefined; it penalised scores that rank such cells (persistence 5% precision) and is superseded.
- **Lead time.** A run counts as warned only if an alert was issued before the run started (lead > 0).
  Detection at or after onset and missed runs are reported separately.
- **Scoring log.** `outputs/test_scoring_log.csv` lists every script run that scored or used outcomes from the
  test year (rows before this review reconstructed from file times).
