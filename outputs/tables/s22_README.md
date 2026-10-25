# Step 22: regional storm forecasting on a fresh holdout

This is separate from the frozen analyses. Decision 150 was committed before the October download.

- `s22_audit_*.csv`: step-0 input checks only, performed before model development. Two requested taxi
  snapshots have offsets over 10 minutes and are excluded; low counts do not trigger new exclusions.
- `s22_unit_cells.csv`: keyed cell membership. Central Area overlaps Central Region. Seven coastal cell
  centres outside MP2019 polygons inherit their frozen planning-area region; Central Area keeps the 16
  centre-within cells. Regions have 118/67/53/57/79 cells (Central/East/North/North-East/West).
- `s22_development.csv`: every time-fold setting and the two calibration finalists per model. Positive
  regression loss is MAE; negative classification loss is minus average precision (lower is better).
- `s22_selected.csv`: final settings and calibration-chosen tree counts, unchanged in the final refit.
- `s22_alert_rates.csv`: calibration base rates fixing alert workload before final refitting. Actual
  October base rates are reported separately; they never determine alert fractions or model settings.
- `s22_environment.csv`, `s22_model_manifest.csv`: software versions and SHA-256 hashes of model bytes,
  transforms, settings, code, processed fitting inputs, geography, audit and unopened October raw files.
- `s22_storm_onsets.csv`: all registered October onsets; the power rule uses their count, not a model score.
- `s22_metrics.csv`: every model x weather x horizon x target x unit x subset combination, with 1,000-draw
  day-block 95% CIs. `weather=0/1` means without/with weather. T1 is a log-relative count, not taxi counts;
  `mae_skill = 1 - MAE / no-weather-persistence MAE`. T2_15 is primary; T2_10/20 are checks. PR-AUC is exact
  average precision with tied scores grouped. Undefined empty-class metrics stay missing. Alert ranking
  is within the reported subset, with chronological tie-breaking and ceil(calibration_rate * n) alerts.
- `s22_weather_gains.csv`: paired weather differences. Positive favours weather; T1 is PERCENT lower MAE,
  T2 is an ABSOLUTE PR-AUC difference. All four model families appear, including losses from weather.
- `s22_materiality.csv`: only the registered pooled LightGBM storm comparison, at 30/60 minutes, T1/15% T2.
  It separates numerical threshold crossings, the eight-onset power requirement and confirmed materiality.
- `s22_support.csv`: sample days/rows, observed and expected vacant counts, event base rates and workloads.

The figure shows LightGBM's primary contrasts for all times and storm windows, by unit/horizon/target.
All model families and both threshold checks remain in the tables. Central Area and Central Region overlap;
pooled CIs resample their issue days together. Intervals are pointwise, conditional on this short holdout,
and day blocks do not fully represent multi-day dependence.

Expected levels use the step-5 Poisson structure, with calendar shape and regional shares fitted inside
each training window and refitted at the final freeze. Historical labels and future targets use the
seven-day coverage factor frozen at the forecast issue, not the target-time factor or an October regime
level. Current citywide counts refer to the 374 analysed cells. The balanced-panel aggregate Poisson fit
reproduces the frozen training-only seasonal pattern to within 0.005% relative difference.

Persistence carries the current log-relative count forward; seasonal predicts zero log deviation. Their
T2 risks use training residual distributions. Their weather variants add the registered weather-only ridge
residual adjustment. Linear and LightGBM weather comparisons use identical rows and base features, with
only the registered weather columns added; imputation/scaling are fitted on training data and saved.

Gauge depths are 5-minute interval totals ending at their timestamp. Six depths in (t-30,t] become mm/h.
Only preceding-day completeness determines gauge health, to avoid future information. Sparse historical
archives retain only positive depths, so they cannot prove intraday observation availability; this is a
measurement limitation. Unknown midnight intervals are missing, not dry. NEA uses one latest issue strictly
before t for all areas, with issue validity checked at t. Storm membership is retrospective evaluation
stratification, never a model feature. No models, thresholds, labels or exclusions change after scoring.
