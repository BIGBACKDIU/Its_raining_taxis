# Decisions log

Choices not fixed by HANDOFF.md, in the order they were made. Each entry says what was decided and why.

## Environment (22 Oct 2026)

- **Python 3.11.9 (python.org build) for `.venv`.** Homebrew Python 3.12 cannot create a virtualenv on this Mac
  (`pyexpat` fails with `Symbol not found: _XML_SetAllocTrackerActivationThreshold`). HANDOFF allows 3.11 or 3.12.
- Added `ruptures` (change-point detection) and `pypdf` (reading LTA fleet PDFs) to `requirements-analysis.txt`.

## Step B: data

1. **Retried every non-ok snapshot, not only the three listed gaps.** 2,671 snapshots (all `empty` or
   `bad_payload` statuses, including 118 in Jun 2024 and 61 in Feb 2025 that HANDOFF did not list) were requested
   once more. **None came back**: the API answers `{"message": "no results found"}` or an empty point list for
   these times, so the archive does not hold them. Raw files are untouched; the retry results are in
   `data/raw/taxi_retry/` (summary: `retry_summary.csv`).
2. **Coverage regimes** (`analysis/prep_feed_regimes.py`): daily index = median over the day's snapshots of
   log(count / median count for that half-hour-of-week). PELT with L2 cost, minimum segment 5 days,
   penalty 40 x sigma^2 x log(n) where sigma is the robust noise level from day-to-day differences. The usual
   BIC-type penalty (2-3 x) gave 60+ segments because the daily index is autocorrelated (weather, holidays).
   Neighbouring segments within 10% merge. Segments under 14 days are an *anomalous spell* (excluded) if they are
   at least 15% (log) away from both neighbours; otherwise they join the closer neighbour. A short segment that
   matches the regime on the far side of a spell gets that regime's label (14-23 Nov 2022 -> R06).
   Result: 18 regimes, 8 spells (41 days).
3. **Single unusual days are flagged, never dropped.** A day can fall 30% below its regime level because of a
   holiday or a storm. Dropping days on the outcome would bias the rain effects. They are kept and listed
   (`anomalous_day` in `data/interim/feed_daily.csv`). Step 0 checks them against rain and holidays.
4. **26 Feb - 7 Mar 2023 spell.** 2-6 Mar is a feed outage: flat ~490 taxis for five days, dry days included.
   26 Feb - 1 Mar overlaps the record rain of 28 Feb 2023 (146 mm per gauge on average). The feed is also
   unstable on those days (single snapshots drop to 23 taxis), so the rain and feed effects cannot be separated.
   It is excluded from main estimates and added back in a robustness check.
5. **No de-duplication of positions.** From Oct 2025 the feed contains exact duplicate coordinates
   (607 of 3,928 points at 03:00 on 15 Oct 2025, vs 6 of 1,537 on 16 Sep 2025). Merging points within 5 m only
   reduces the count to 2,629, still 1.8x September. So the jump is duplicates plus extra vehicles, and the
   panel stores cell counts, not positions. Handled with regime fixed effects and the share-of-citywide model,
   as HANDOFF says. Cell shares are stable across every boundary (correlation 0.91-1.00,
   `outputs/tables/feed_share_stability.csv`), which supports the share model.

## Step B: static data

6. **School holidays are hand-entered** from MOE calendars (2025-2026 checked against the MOE release of
   30 Jul 2025). Public holidays come from data.gov.sg (consolidated dataset).
7. **CDG fleet share = (Comfort + CityCab) / all taxis**, from LTA's monthly P2P statistics PDFs
   (`data/static/sources/`). It is 60-65% over the period. Sep 2026 is not yet published; Aug 2026 is used.
8. **Storm days for the simulation:** rank days by the peak island-mean rain over a 30-minute window between
   07:00 and 23:00 (working gauges only), skip excluded days, keep days at least 7 days apart. Take 20 from the
   fit period (Apr 2022 - Mar 2025) and 10 from the test year. Positions are saved from 3 h before to 4 h after
   the peak, not whole days, to keep the files small (13 MB in total). Five fit-period storms fall in the
   low-coverage regime R05 (Aug-Nov 2022). Superseded by decision 9: they are replaced, not scaled.

## Step B follow-up (agreed with Matthew at the step-B checkpoint)

9. **Simulation storms come only from normal-coverage regimes.** Fit-period storms must lie in a regime with
   coverage level 0.8-1.25x. This replaces the five R05 storms (Aug-Nov 2022) and also 16 Nov 2024, which lies in
   the other half-coverage regime R10 (0.47x); the same reasoning applies. The next-ranked storms replace them
   (20 Sep 2023, 15 Feb 2025, 6 Sep 2023, 22 Jan 2023, 16 Nov 2022, 10 Jan 2025). Still 20 fit + 10 test.
   Test-year storms are unchanged: three fall in the high-coverage regime R14 (Oct 2025 - Jan 2026); their raw
   positions allow de-duplication in step 8 if needed. Storm selection is re-run after step 0 so it skips
   feed-outage days too (no storm changed).

## Step 0: audit

10. **Snapshot glitches.** A snapshot is dropped as a glitch if its citywide count is below 50% of the median of
    the +-2 neighbouring snapshots (at least 3 present, all in adjacent slots) and both the previous and the next
    snapshot are back at >= 80% of that median. Sustained drops are not touched. 462 snapshots dropped
    (0.4%); 109 of them in Dec 2024.
11. **Unusual days: feed outage vs rain-like.** For each unusual day (daily level > 0.35 log from its regime),
    compute the correlation of its cell shares (1 km cells, sqrt shares, eight 3-hour blocks, weighted by taxis)
    with the regime's normal shares for the same block. A day with fewer taxis has noisier shares, so the
    benchmark is a null built from 40 of the regime's normal days, binomially thinned to the day's own level;
    "high correlation" = at least the null's 10th percentile. "Little rain" = island-mean daily rain < 2 mm and
    no working gauge above 20 mm. High correlation AND little rain = feed outage: excluded from the main
    estimates, kept in a robustness set. Result: 87 unusual days, 17 feed outages (2 of them with any rain,
    all <= 2 mm island mean), 70 kept. Of the kept days, 16 are dry but spatially unusual (e.g. Chinese New
    Year 29-30 Jan 2025, 14-16 Mar 2023 right after the outage spell); they stay in by the rule.
12. **Jump z-scores are de-seasoned.** The change in log citywide count between consecutive snapshots is compared
    with the median change for the same quarter-hour of week (separately for 30- and 15-minute data), so the
    morning ramp is not flagged. |z| > 6 is listed in `outputs/tables/audit_jumps.csv` for inspection, not
    dropped.
13. **Stuck gauges** (7+ consecutive complete days at 0 mm while the 3 nearest working gauges record > 1 mm on
    3+ of those days): 20 gauges, 439 gauge-days, treated as missing (`working = complete & ~stuck`).
14. **Exclusion sets** in `data/interim/day_flags.csv`: `exclude_main` = missing days (< 50% of snapshots) +
    spells + feed-outage days (100 days); `exclude_robust` = missing days + spells except 26 Feb - 1 Mar 2023
    (feed-outage days and the ambiguous spell come back in). `covid` flags Oct 2021 - Mar 2022.
15. **Multi-snapshot dips** (agreed at the step-0 checkpoint): runs of 1-3 consecutive snapshots whose citywide
    count is below 25% of the median of the surrounding +-2 hours (the run itself excluded) are dropped as
    glitches; longer runs are kept as sustained drops. 74 snapshots dropped (`glitch_dip`), on top of the 462
    single spikes (`glitch_spike`). Usable snapshots: 118,136. Unusual-day classification re-run on the cleaned
    snapshots: still 17 feed-outage days, now 2 with any rain.

## Step 1: panel

16. **Two panels.** The main panel (`panel30_YYYY.parquet`) uses the :00 and :30 snapshots for all years. A
    15-minute panel (`--grid 15`, Oct 2024 on) is built only when an analysis needs it. Panels are
    per calendar year and stay out of git (~65 MB each).
17. **Eligibility** is computed on 30-minute fit-period snapshots in the main sample: 374 of 639 cells have a mean
    of at least 0.5 vacant taxis; 265 are "not analysed".
18. **Every row carries** `regime_id`, `regime`, `day_missing`, `spell`, `feed_outage`, `glitch`, `covid`,
    `drop_main` (any exclusion) and `drop_robust` (glitches, missing days and spells except 26 Feb - 1 Mar 2023).
    Glitch snapshots stay in the panel, flagged, so models can be re-run with them.
19. **Cell traits** are in `data/interim/cells.parquet` (joined on `cell`), not repeated on every row:
    distance from cell centre to the nearest MRT/LRT exit, taxi stops/stands within 300 m of the cell square,
    MRT exits in the cell, planning area of the cell centre, city-centre flag (URA Central Area planning areas).
20. **Rain to snapshots.** 5-minute readings are summed into 15-minute bins per gauge; prior rain = the two bins in
    (t-30, t] at the nearest working gauge for the snapshot's date, in mm/h. Lags (t-60, t-30] and (t-90, t-60].
    `mmh_3g` = mean of the 3 nearest working gauges. `wet_min` / `dry_min` = length of the current wet / dry run
    at that gauge (15-minute resolution). Bins of a gauge-day that is not working are missing (not dry).
21. **Forecasts as issued.** The latest 2-hour forecast issued strictly before t for the nearest forecast area;
    missing if older than 180 minutes. Codes: 0 fair/cloudy/hazy/windy, 1 light rain/light or passing showers,
    2 showers/moderate rain, 3 thundery or heavy.
22. **Baseline** = Poisson `vacant ~ 1 | cell + how^month + regime` on fit-period main-sample rows, solved exactly
    by iterative proportional fitting on aggregated counts (38 iterations). The regime term gives a level within
    each regime (HANDOFF 3a). Regimes outside the fit period get their level from their own main-sample rows with
    the cell and how^month effects held fixed. Spell rows have no baseline. This regime level uses data from the
    whole regime, so it is fine for description and association models; the forecasting step must not use it as
    an input (only as part of the target definition, to be decided in step 6).
23. **Severity** (baseline >= 4 only): 0 if deficit < 0.25, 1 if < 0.5, 2 if < 0.75, 3 otherwise.
24. **Panel checks** (`outputs/tables/panel_checks_30.csv`): rows = 374 cells x snapshots in every year, no duplicate
    (cell, ts) keys. Hand check (`panel_handcheck_30.csv`): 5 random rows plus 3 extra rows drawn from rainy
    snapshots (random rows are almost always dry); vacant, citywide count and prior rain all match the raw files.

## Step 2: description

25. **Availability is shown relative to the baseline** (sum of vacant / sum of baseline), so feed coverage changes
    are not mistaken for rain effects. Profiles use 2-hour blocks (hourly blocks for heavy rain are too thin),
    weekday vs weekend-or-holiday, with 95% day-bootstrap bands (200 draws). Map counts (mean vacant per cell)
    use normal-coverage regimes only (0.8-1.25x); the % change map uses all fit-period regimes via the
    baseline ratio and needs >= 100 heavy-rain snapshots per cell.
26. **Trend vs fleet** is indexed (Apr 2022 = 100) on one axis instead of using two y-axes.

## Step 3: rain associations

27. **Own Poisson fixed-effects estimator** (`analysis/fepois_hd.py`). pyfixest needs ~550 bytes per row, about
    10 GB for the 18 million fit-period rows. The replacement implements the same estimator (IRLS with weighted
    alternating projections, CRV1 by day, G/(G-1)(N-1)/(N-K) correction) with plain numpy arrays. On 2023 it
    reproduces pyfixest's coefficients to 6 decimals and its standard errors to within 0.04%
    (`outputs/tables/effects_validation.csv`).
28. **ym^regime instead of separate ym and regime effects.** Separate effects are nearly collinear and make the
    demeaning 25x slower. The interaction contains both (it is more flexible) and gave identical coefficients
    on 2023.
29. **Event study**: the estimation reference is all cell-snapshots outside any event window; coefficients are
    then expressed relative to -30 min (HANDOFF), with delta-method standard errors.
30. **Association models use the fit period only** (Apr 2022 - Mar 2025), to keep the test year untouched
    (rule 5). The high-coverage regime (Oct 2025 - Jan 2026) exists only in the test year, so the by-regime
    check covers half-coverage (R05, R10) and normal-coverage regimes, not the high-coverage one.
31. **Reading the three main models.** The absolute model compares a wet cell with the same cell at the same
    time of week when dry; the share and offset models also remove whatever happens to the citywide count at
    that snapshot. Rain usually covers many cells at once and the citywide count falls with it, so the share
    and offset effects (local, relative) are smaller than the absolute one. Both are reported; neither is
    "the" effect.
32. **By-regime check.** The share-model effect is negative in 9 of 10 fit-period regimes, but its size differs
    more than chance allows for moderate and heavy rain (heavy: Cochran Q = 32.8, df 9, p < 0.001, I^2 73%;
    without R10 p = 0.004). The differences do not line up with coverage level (half-coverage R05 -4.0%,
    R10 +2.2%; normal-coverage regimes -3.9% to -11.7%). `outputs/tables/effects_by_regime_heterogeneity.csv`.

## Step 3 follow-up (agreed with Matthew at the step-3 checkpoint)

33. **Neighbouring-rain features** (panel, all from data up to t): `rain_2km` (mean mm/h over (t-30, t] in cells
    whose centres are within 2 km, the cell itself excluded), `rain_ring` (2-5 km ring), `wet5_min` (minutes
    since rain first appeared within 5 km in the current spell; 0 if none now), `dry5_min` (minutes since rain
    was last seen within 5 km, capped at 1440), `gauges_wet_share` (island share of working gauges with rain).
    Every 1 km cell seen in the feed (639, eligible or not) carries the rain of its nearest working gauge, so the
    means are area-weighted gauge readings.
34. **"Rain approaching" model**: dummies for ring rain (light <= 2.5 / heavier > 2.5 mm/h) and 2 km rain while
    the cell itself has had no rain for 90 minutes, added to the main specification.
35. **Season and time band**: NE monsoon = Dec-Mar, SW monsoon = Jun-Sep, inter-monsoon = Apr-May and Oct-Nov;
    time bands night 00-07, AM peak 07-10, day 10-17, PM peak 17-20, evening 20-24. Tested as heavy x season and
    heavy x time band terms in the share model, before and after heavy x regime terms (reference regime R09).
    Result: they do not explain the regime differences (heavy x regime Wald 35.5 -> 27.9, df 9, p 0.001).
36. **Interactions** are run one at a time (heavy x rush hour / city centre / weekend-or-holiday / fiscal year),
    each in the absolute and share models. Rush hour = weekday 07-10 and 17-20.
37. **Forecast value**: rows where the cell has had no rain for 90 minutes and a forecast is available; dummies for
    the forecast category (reference fair/cloudy), with and without neighbouring-rain controls.
38. **Robustness**: 3-gauge mean rain; fiscal-year splits; robustness sample; COVID months; 15-minute panel vs
    30-minute panel over the same months (Oct 2024 - Mar 2025); 500 m grid vs 1 km over FY2024 (500 m eligibility
    by the same >= 0.5 rule: 793 of 2,160 cells); Poisson and NB2 GLMs on a table aggregated to planning area x
    3-hour block of week x ym^regime x band (NB2 alpha by method of moments from the Poisson fit, HC1 errors);
    event-study onset thresholds 0.5 and 2 mm/h.

## Step 4: inference

39. **fit0** (no-rain model) = Poisson cell + how^month + ym^regime fitted by IPF on dry rows (no rain at the cell
    for 90 minutes), predictions for all rows. Day bootstrap: 2,000 draws. Storm blocks: consecutive days with
    heavy rain anywhere form one block (507 blocks, 131 multi-day). Permutation: 1,000 draws, rain patterns
    (band per cell and half hour) swapped between days in the same year-month and weekday/weekend group.
40. **Hotspots**: per-cell ratio statistic for heavy rain with day-bootstrap standard errors, normal p-values,
    Benjamini-Hochberg at 10%, cells with >= 100 heavy-rain rows.

## Step 5: risk

41. **Logit with fixed effects** via the same estimator (logit family checked against pyfixest in tests/).
    Rows where the fixed-effect group has no variation in the outcome are dropped (reported in the table).
42. **Vulnerability** = percentage-point difference P(low | heavy) - P(low | dry) per cell, 1,000 day-bootstrap
    draws; shown only where the 95% CI excludes 0 and the cell has >= 50 heavy-rain rows with baseline >= 4.
43. **Severity multinomial** on a 1,000,000-row random sample with controls (city centre, peaks, night, weekend,
    regime level, log baseline) instead of fixed effects, errors clustered by day; appendix only.
44. **Rain-response types**: k-means on four log ratios (light, moderate, heavy, just after rain, each relative
    to dry), k chosen by silhouette (k = 2); 200 day-bootstrap re-clusterings, mean adjusted Rand index 0.65
    (5th-95th percentile 0.49-0.76): moderately stable, so the types are described, not relied on.

## Step 6: forecasting

45. **Target and inputs.** Targets are the vacant count and low availability at t+h (h = 30, 60 min), using the
    panel's regime-level baseline (HANDOFF 5). That baseline uses the whole regime, so it is never an input.
    Inputs replace it with what is known at t: the fit-period pattern (cell + how^month effects, no regime level),
    the current coverage level (sum of vacant / sum of pattern over eligible cells at t) and its trailing 1-day
    and 7-day medians, a feasible deficit at t (pattern x 7-day level vs taxis at t), the climatology of low
    availability (fit period, cell x hour x day type, lightly shrunk; 0.17 where undefined) and calendar and cell
    traits. Weather inputs (with-weather models only): rain at the cell and lags, 3-gauge rain, wet/dry
    durations, 2 km and 2-5 km ring rain, minutes since rain appeared within 5 km, island rain and wet-gauge
    share, the latest issued forecast for the cell's area and the highest forecast category within 5 km.
46. **Samples.** Training uses 35% of fit-period issue snapshots (all cells at each kept snapshot), and LightGBM
    a further random 3 million rows (count) / all ~2.6 million defined rows (low); regression models 2 million
    rows. Calibration (Apr - Sep 2025) and test (Oct 2025 - Sep 2026) use every snapshot.
47. **Tuning.** Optuna (8 trials, TPE, seed 2702) on three time-ordered expanding folds inside the fit period,
    400k rows per fold, h = 60 with weather; the chosen settings are reused for all LightGBM models (with and
    without weather, both horizons) so the weather comparison is not confounded by tuning effort.
48. **Persistence and seasonal scores for "low".** Persistence ranks by the feasible deficit at t; the seasonal
    baseline ranks by the climatology of low availability. Count persistence = taxis at t; count seasonal =
    pattern at t+h x 7-day level.
49. **Calibration and alerts.** Isotonic calibration and alert thresholds are fitted on Apr - Sep 2025. Fixed
    workload = 5% of eligible cell-snapshots (the threshold is the calibration-period 95th percentile of each
    model's score). Precision in the top-20 risk cells is averaged over snapshots.
50. **Lead time.** A low-availability run is a sequence of consecutive low snapshots in a cell. Its warning lead
    time is h minus (target time of the first alert that falls inside the run minus the run start); runs with no
    such alert are "not warned".
51. **Weather gain uncertainty.** 1,000 day-block bootstrap draws of the PR-AUC difference on the test year,
    computed from per-day counts in 2,000 score bins (checked against exact average precision: 0.3032 vs 0.3035
    on synthetic data; observed binned vs exact gains agree to 4 decimals).
52. **Conformal ranges** use scaled residuals |y - yhat| / sqrt(yhat + 1), 90% level, quantile from the
    calibration period; achieved coverage is reported, not guaranteed.
53. **Test year first scored: 2026-10-23 00:08:41 SGT** (`data/interim/test_year_first_scored.txt`). After that,
    only evaluation code and new subsets of the same frozen predictions were added; no model was refitted.
54. **High-coverage regime check (after test scoring, as agreed).** Share model per test-year regime
    (`outputs/tables/effects_test_year_by_regime.csv`). [Corrected after review: R13 was NOT skipped; it has
    269,226 rows.] R13 (1-15 Oct 2025, high coverage 2.0x) heavy rain: share -14.0%, absolute -17.6%; R14 (high
    coverage, 1.8x): share -10.2% (CI -14.0 to -6.2), absolute -16.1%; other test-year regimes: share -8.5% to
    -24.9%. The direction matches the fit period; sizes are larger in the test year, in line with the trend across
    fiscal years (FY2024 share -7.7%).

## Secondary forecasting analysis S1 - PRE-REGISTERED (written and committed before any S1 code was run)

Added after the first test-year scoring (2026-10-23 00:08:41), at Matthew's request at the step-6 checkpoint.
Every S1 output is labelled "secondary analysis (S1), added after first test scoring". The primary step-6
results stay as they are and remain the pre-specified result.

55. **Why.** At 1 km the 50%-deficit label is dominated by count noise (rain moves expected counts by 5-15%;
    typical counts are 4-10). S1 asks whether weather adds more when the label is noise-aware and when counts
    are aggregated to larger units.
56. **Units (scales).** (a) 1 km cells (374 eligible); (b) 2 km blocks: non-overlapping 2 x 2 groups of eligible
    1 km cells (cx // 2, cy // 2), 129 blocks; (c) URA planning areas of the eligible cells' centres, 49 areas.
    Counts, baselines and patterns are summed over member cells first; labels are defined on the sums.
57. **Labels.** (i) deficit: (B - Y) / max(1, B) >= 0.5 where B >= 4 (as primary), B = summed panel baseline;
    (ii) noise-aware: Y below the 5th percentile of a negative binomial with mean B and dispersion alpha,
    i.e. Y < q, where q is the smallest k with NB-CDF(k) >= 0.05. One NB2 alpha per scale (Var = mu + alpha mu^2),
    fitted by maximum likelihood on fit-period main-sample unit-snapshots (random 2 million if more).
    Base rates of both labels are reported for fit, calibration and test periods at every scale.
58. **Horizons.** 30, 60 and 120 minutes.
59. **Models.** Persistence (feasible score known at t: deficit label - feasible deficit at t; NB label -
    1 - NB-CDF(Y_t) with mean = pattern_t x trailing 7-day level) and LightGBM binary with and without weather.
    Hyperparameters = the primary tuned binary settings (outputs/tables/forecast_tuning.json); the only choice
    made per model is the number of boosting rounds, by early stopping on calibration-period log loss
    (patience 50, maximum 2,000 rounds). No other tuning, no feature selection. No regression models in S1.
60. **Features.** As primary, built at unit level from data available by t. Count features are unit sums;
    coverage level is citywide (as primary); climatology of both labels per unit x hour x day type from the fit
    period. Weather: unit mean and max of prior rain, mean lags, mean 3-gauge rain, mean 2 km and ring rain,
    max wet duration within 5 km, min dry duration within 5 km, mean wet/dry duration at the gauges, island rain
    and wet-gauge share, max issued forecast code in the unit and within 5 km, mean forecast age.
61. **Training rows.** 1 km and 2 km: 35% of fit-period issue snapshots (all units at kept snapshots), capped at
    3 million rows for LightGBM; planning areas: all fit-period snapshots. Calibration and test: all snapshots.
62. **Evaluation (test year scored once more, for S1 only).** For each scale x horizon x label: PR-AUC without and
    with weather, gain with 95% CI from 1,000 day-block bootstrap draws (binned average precision as in
    decision 51), overall and in rainy slots (any rain at target time in the unit: unit mean prior rain > 0);
    lead time and share of runs warned at a fixed 5% alert workload (thresholds from the calibration period).
    Calibration-period PR-AUC is reported next to the test-year values.
63. **Pre-specified reading.** Weather is called "materially useful" for a scale x horizon x label only if the
    test-year gain is >= 0.01 PR-AUC AND its 95% CI excludes 0. Smaller significant gains are "detectable but
    small". 18 comparisons (3 scales x 3 horizons x 2 labels) x 2 subsets are made; no multiplicity correction
    is applied, so isolated hits are read with caution.
64. **Notes stated in all S1 outputs.** The test-year label baseline uses each test regime's own level, estimated
    from that regime's own rows (no fit data exist for those regimes). The primary 1 km deficit label's base rate
    rose from 18.4% (calibration) to 26.5% (test). Subsets added to the primary evaluation after first scoring
    ("rain starts between issue and target", "heavy rain at target time", "cell dry at issue, heavier rain
    2-5 km away") are post-hoc.
65. **S1 result (test year scored for S1 on 2026-10-23 00:46:42, `data/interim/s1_test_scored.txt`).** None of the
    36 scale x horizon x label x subset comparisons meets the pre-registered "materially useful" rule (gain
    >= 0.01 with CI excluding 0). Largest test-year gain +0.0021 (1 km, 60 min, deficit, rainy; CI -0.0001 to
    +0.0046). At 2 km and planning-area scale the weather models are often slightly worse on the test year
    (e.g. planning areas, 30 min, NB label, rainy: -0.0074, CI -0.0109 to -0.0037), although they were slightly
    better on the calibration period (+0.002 to +0.009). The NB label's base rate jumps between calibration and
    test (1 km 1.3% -> 5.1%; 2 km 2.2% -> 7.0%; planning areas 2.8% -> 7.5%): the fit-period dispersion is too
    small for the test-year feed (duplicated records and a shrinking fleet within each test regime), so the
    "5th percentile" is not a 5% event in the test year. Outputs: `outputs/tables/s1_*.csv`,
    `outputs/figures/s1_weather_gain.*`.
66. **POST-HOC check (after S1): normal-coverage months only.** On the test-year subset from 11 Jan 2026, the
    weather gain stays negligible: primary 1 km LightGBM +0.0007 (30 min, CI +0.0004 to +0.0010) and +0.0008
    (60 min); S1 planning areas -0.0020 to +0.0015 overall, -0.0073 to +0.0021 in rainy slots. The null is not
    driven by the high-coverage months. `outputs/tables/posthoc_weather_gain_from_11jan.csv`.

## Step 7: repositioning policy (rules fixed before running)

67. **Framing.** The policy runs on availability forecasts made at t (step 6). [Wording corrected after review:]
    there was no material weather gain (all 36 S1 comparisons below the pre-registered 0.01 PR-AUC threshold;
    largest +0.002) for the tested labels, models and horizons, so weather enters the step-7 count forecast only if it helps on the calibration period by BOTH:
    lower calibration Poisson deviance of the count forecast (weather 1.1950 vs no weather 1.1981 at 30 min;
    1.2695 vs 1.2734 at 60 min: met) AND higher calibration targeting precision of the policy (share of
    targeted cells that are really low at t+h) on the same calibration sample. Otherwise the no-weather
    forecast is used.
68. **Policy inputs (all known at t).** base_j = pattern at t+h x trailing 7-day level (the feasible baseline);
    mu_j = LightGBM count forecast; movable supply at origin i = floor(CDG share x max(0, vacant_i - base_i(t)))
    with base_i(t) = pattern at t x 7-day level and the CDG share of the month (Aug 2026 for Sep 2026);
    destinations need base_j >= 4, a taxi stop or stand within 300 m of the cell, and S_j(0) >= 0.05.
    Travel time = 1.3 x straight-line distance / speed, speed 30 km/h (dry scenario) or 20 km/h (rain congestion
    scenario, used when the island has rain at t); both are modelled assumptions, not observed speeds.
    x_ij = 0 if travel time > lead time (= horizon). Marginal values r_jk for k <= min(ceil(base_j), 20).
69. **Base case and sensitivity.** Base: N = 200 taxis per decision, lambda = 0.005 per taxi-minute, lead 60 min,
    congestion by observed island rain, equal weights. One-at-a-time sensitivity: N 50 / 500; lambda 0.001 / 0.02;
    lead 30; congestion always dry / always rain; weights station activity (1 + MRT exits in cell) and land-use
    proxy (city-centre cells 2, others 1), both rescaled to mean 1. No land-use data are available, so the
    "land use" weight is a proxy and is labelled as such.
70. **Samples.** Calibration choice: 150 snapshots (75 with island rain at t, 75 without), seed 2702. Test-year
    evaluation: 300 snapshots (150 rainy, 150 dry) for the base case and the ranked plans; 100 snapshots (50/50)
    for each sensitivity setting. Expected shortfall reduction is a model quantity; the targeting check uses the
    observed low-availability label at t+h.
71. **Planning layer** (rain associations, fit period, no forecasting): for each planning area x time band x
    weekday/weekend, availability under (a) an issued NEA forecast of showers or thundery rain (code >= 2) and
    (b) observed heavy rain, against the no-rain model fit0 (step 4): absolute loss (vacant taxis per half hour,
    summed over the area's eligible cells), % loss (sum vacant / sum fit0 - 1) and share loss (fit0 rescaled to the
    observed citywide total over eligible cells at each snapshot). 500 day-bootstrap draws for CIs; groups with
    fewer than 200 cell-snapshots are not ranked.

## Step 8: simulation (rules fixed before running)

72. **Model type.** A scenario-based operational model, never "validation". Cell-based agent model on the 374
    eligible 1 km cells, 1-minute steps, seeds vectorised (numpy). Each cell holds integer counts of vacant and
    offline taxis; occupied and repositioning taxis are tracked by arrival minute and destination cell, so the
    fleet is conserved exactly. Requests are Poisson per cell per minute; waiting requests abandon with a
    geometric patience (mean 6 minutes). Matching uses the taxi's own cell first, then rings of cells by centre
    distance (<= 1.5, 2.5, 3.2 km; widening dispatch adds <= 5 and 8 km for requests that have already waited).
    A matched taxi's pickup is approximated by its own cell plus an approach time; destinations are drawn from the
    scenario's destination matrix. Trip time = approach + 1.3 x distance / speed + 2 minutes.
73. **Scenario grid.** Mechanism in rain (demand surge / supply drop / mix) x demand level (0.8, 1.0, 1.2) x
    destinations (MRT pattern: weight 0.5 + MRT exits, gravity exp(-d / 10 km); distance decay from a land-use
    proxy: city-centre 2, other 1, x taxi stops + 1, exp(-d / 4 km)) x travel times (dry 30 km/h everywhere /
    rain congestion 20 km/h in raining cells) x dispatch (nearest within 3.2 km / widening radius) x policy
    (as usual / step-7 repositioning every 30 minutes, LP relaxation solved with HiGHS, persistence forecast).
    No land-use data are available; the land-use destination pattern is a labelled proxy.
74. **Normal time-of-day path.** At each 30-minute boundary the number of taxis on the road is set to follow the
    citywide panel baseline (expected vacant level without rain) relative to the storm start; taxis are added
    at cells in proportion to the cell baseline and removed in proportion to current vacant taxis. Rain effects
    are therefore relative to the expected path.
75. **Calibration.** For each of the 24 mechanism x destinations x travel x dispatch combinations, Optuna (12
    trials, TPE, seed 2702) tunes the initial occupied share (0.2-0.7), a demand scale around equilibrium
    (0.7-1.3) and the rain response (demand surge per 10 mm/h 0-2; offline probability per minute at 30 mm/h
    0-0.05; mix tunes both), on the 20 fit-period storms, 2 seeds, to minimise: RMSE of simulated vs observed
    citywide vacant taxis (each relative to its value at the storm start) + 0.5 x (1 - correlation of cell
    mean vacant over the window). Demand level 0.8 / 1.2 is applied after tuning.
76. **Plausibility rule (fixed in advance)** on the 10 held-out test-year storms (positions de-duplicated within
    5 m; relative series, so coverage level cancels): a storm passes if the simulated relative citywide vacant
    series is within +-20% of the observed relative series at >= 70% of snapshot times; a combination passes if
    >= 7 of 10 storms pass AND the sign of the change from start to rain peak matches the observed sign in >= 7 of
    10 storms. Results are reported for all combinations, with pass / fail shown.
77. **Grid runs.** 50 seeds per grid cell on the 10 held-out storms. Reported ranges (5th-95th percentile over
    seeds and storms) are labelled "simulated, conditional on scenario X": vacant taxis at the rain peak relative
    to start, share of requests abandoned during rain, mean wait of served requests, share of cells with no
    vacant taxi. Requests, waits and abandonments are simulation quantities, never observed demand.
78. **Web page check.** `sim/index.html` runs a JavaScript port of the same rules with a seeded RNG; the page
    averages (50 seeds) must be within 5% of the Python engine for the same scenario and storm (checked in node
    on 3 scenario x storm pairs).
79. **Policy solver inside the simulation.** The step-7 objective is solved by a greedy marginal-value heuristic
    in both the Python engine and the web page (no LP solver in the browser), instead of HiGHS as first written
    in item 73. Its objective is compared with the PuLP optimum on 60 step-7 test decisions
    (`outputs/tables/sim_greedy_vs_pulp.csv`). The simulation's policy forecast is persistence (current vacant
    taxis), and the plan is computed once per decision from the seed-mean state and applied to every seed
    (capped by each seed's available taxis).
80. **Step 7 results.** Weather was not kept for step 7: on the calibration sample its targeting precision was
    no better (23.20% with vs 23.20% without; candidates 18.7%). Test year, base case (N = 200, lambda 0.005,
    60 min): 149-166 taxis moved per decision, 73-78 cells targeted, targeted cells really low 31-32% vs 28% of
    all candidate cells; modelled expected shortfall reduced by 34-39%. Smaller budgets target better (N = 50:
    38-39%), larger budgets remove more modelled shortfall (N = 500: 39-43%) at lower precision (31-32%).
    Planning layer: across all area x time groups, an issued NEA showers/thundery forecast goes with 6.6% fewer
    vacant taxis than the no-rain model and observed heavy rain with 13.8% fewer (consistent with step 4); small
    areas at specific hours show larger swings with wide day-level uncertainty.
81. **Parity tolerance near zero.** Item 78's 5% rule is undefined when a value is close to zero (one check case
    empties the fleet at the rain peak in both engines: 0.0017 vs 0). The peak comparison also passes if the
    absolute gap is <= 0.01 of the start level. Mean paths differ by <= 0.32% in all three cases.
82. **Step 8 results.** Tuning (12 trials per combination, pre-registered) left several combinations at the same
    values near the lower bounds of the occupied share and demand scale; without rain effects the tuned setting
    tracks the observed pre-rain path (mean bias +0.014), so this is not a broken model, but 12 trials is a
    thin search. **No combination passes the pre-registered plausibility rule** (best: 5 of 10 held-out storms
    within +-20% at 70% of times; the sign of the change at the rain peak matches in 7-9 of 10). All grid ranges
    are therefore reported as "simulated, conditional on scenario X" AND "scenario did not pass the held-out
    plausibility check". The greedy policy solver reaches 97.4% of the PuLP optimum on 60 step-7 decisions
    (minimum 94.5%). The JavaScript page matches the Python engine (mean paths within 0.32%, peaks within 1.7%
    or both near zero).

## Changes after the independent review of commit aac26fe (reviewer's items 1-9)

83. **Retrospective labels (item 1).** All forecasting results before this point are evaluated against
    RETROSPECTIVE labels: the test-year baseline uses each test regime's level estimated from that regime's own
    test-year rows (`01_panel.py`, regime levels outside the fit period), and the regime change points were
    detected on all five years. A disclosed additional scoring of the test year (no refitting,
    `analysis/06d_label_versions.py`) adds an ISSUE-TIME-KNOWABLE label: baseline = pattern at t+h x trailing
    7-day coverage level known at t (= the seasonal_h input), same deficit >= 0.5 (baseline >= 4) and NB rules.
    Results (`forecast_eval_both_labels.csv`): base rates barely move (1 km deficit 26.5% -> 26.4%); PR-AUC and
    the weather gain are nearly identical; largest weather gain +0.0024 (issue-time) vs +0.0021 (retrospective);
    no comparison meets the pre-registered materiality rule under either label.
84. **Fixed workload (item 3).** The earlier "5% workload" used thresholds set on rows with a defined label, so it
    alerted about 2.2% of eligible cell-snapshots, at different rates per model. Main metric now: top-K per issue
    time, K = 19 / 6 / 2 (5% of 374 cells / 129 blocks / 49 planning areas), same K for every model. A first
    corrected run ranked all cells and gave persistence 5% precision because its top scores fall on cells with
    expected < 4, where the deficit label is undefined (never low). After seeing that, the ranking set for the
    deficit label was restricted to cells with expected >= 4 known at issue time (the same condition as the
    label and the step-7 destinations); the NB label ranks all units. Both runs are kept
    (`*_allcells_ranking.csv` = superseded first run). Calibration-threshold results are kept separately
    (`forecast_calibration_threshold.csv`). Main numbers, 1 km, retrospective label: top-19 precision 30 min
    LightGBM 52.9% (with weather 52.9%), persistence 46.1%, climatology 42.6%; 60 min 50.8% / 50.7% / 42.9% /
    42.6%.
85. **Lead time (item 4).** `fc_eval.lead_times` now counts a run as warned only if an alert targeting it was
    issued before the run started (lead > 0); alerts first issued at or after onset are reported as "detected at
    or after onset". With top-19 alerts, 1 km: warned before onset 6.2% (30 min) and 13.2% (60 min) of runs for
    LightGBM, 12.7% / 14.2% for the climatology ranking, 0.8% / 11.6% for persistence; detected at or after onset
    9.4% / 3.3% (LightGBM); the rest are missed. Before the fix, "warned" included alerts after onset.
86. **Wording (item 5).** "Weather adds no early-warning value" is replaced everywhere by "no material weather gain
    (all 36 comparisons below the pre-registered 0.01 PR-AUC threshold; largest +0.002) for the tested labels,
    models and horizons".
87. **Robustness sample bug (item 2).** `03_effects_more.load()` and `03_effects.sample()` no longer require a
    baseline (association fits do not use it). The robustness sample now contains the 26 Feb - 1 Mar 2023 spell
    (70,686 rows): heavy rain -12.5% (absolute, CI -13.9 to -11.0) and -5.8% (share) - unchanged at one decimal.
    The main sample is unchanged (spells are excluded there anyway).
88. **Rain timing (item 6).** Sensitivity with the rain window lagged one 15-minute bin, (t-45, t-15], lags
    shifted the same way: heavy rain -13.1% absolute (main -12.9%), -4.3% share (main -5.7%); light and moderate
    also slightly smaller in the share model. Limitation: snapshots are taken ~19 seconds before the requested
    time, so the last 5-minute rain reading in (t-30, t] can end up to ~19 s after the snapshot; the lagged
    window removes this and the conclusions hold.
89. **Permutation (item 7).** p-values are reported as "< 0.001" (1,000 draws; none as extreme as observed). The
    test assumes rain patterns are exchangeable between days within the same year-month and weekday/weekend group.
90. **Titles and log (item 8).** "Rain raises the odds" -> "Rain is associated with higher odds" (05_risk);
    "cells lose vacant taxis" -> "cells have fewer vacant taxis" (02_describe); item 54 corrected (R13 was
    included, heavy-rain share effect -14.0%).
91. **Scoring log (item 9).** `outputs/test_scoring_log.csv` gets a row from every script run that scores or uses
    outcomes from the test year (`common.log_test_scoring`). Rows before this review are reconstructed from file
    times. This review added five rows: primary evaluation re-run twice (corrected definitions; then the
    ranking-set change) and two runs of 06d, plus the step-7 label re-scoring.
92. **Step 7.** No alert thresholds or lead times are used in step 7. Its targeting check now reports both labels
    (`policy_sensitivity.csv`): base case 31-32% (retrospective) and 30-32% (issue-time) of targeted cells low,
    vs 27-28% of all candidate cells.

## Step 7 follow-up: why the policy dilutes the forecast (rule fixed before running)

93. **Question.** Targeted cells are low 31-32% of the time, while the forecast's top-19 ranking reaches about
    53%. Variants compared per decision time: (a) policy as designed (equal weights); (b) the same policy with
    destination weights = forecast risk (LightGBM probability of low availability at t+h, no weather); (c) top-19
    forecast ranking among cells with expected >= 4, ignoring all policy constraints. Diagnostics: (c) restricted
    step by step to cells with a staging point, then with modelled shortfall S_j(0) >= 0.05, then reachable from a
    surplus cell within the lead time; and the policy's 19 destinations that receive the most taxis.
    **Choice rule (calibration period only, 150 decision times):** adopt (b) for the test year if its targeting
    precision (retrospective label, all targeted cells) is at least 2 percentage points higher than (a); otherwise
    keep (a). The test year is then scored once for (a), (b) and (c) and logged.
94. **Step 7 follow-up result.** Calibration (150 decision times): risk weights (b) 38.9% of targeted cells low vs
    23.2% as designed (a) - rule met, (b) adopted. Test year, scored once (`policy_diagnosis.csv`; retrospective /
    issue-time label): (a) 30.6% / 31.0% over ~76 cells per decision; (b) 43.4% / 44.2% over ~16 cells; (c) top-19
    forecast ranking without constraints 50.8% / 51.5%; requiring a staging point 47.8% / 48.1%; adding the
    shortfall and 60-minute reachability limits changes nothing further. Diagnosis: most of the dilution comes from
    equal weights, which spread taxis over many large-baseline cells by expected shortfall; the staging-point
    requirement costs about 3 points; the remaining gap between (b) and the constrained ranking (about 4 points)
    comes from the LP's travel cost and supply allocation. Trade-off: on 40 calibration decisions (b) moves about
    38 taxis to about 20 cells per decision (183 taxi-minutes), (a) about 118 taxis to 66 cells (659 taxi-minutes).
    Ranked staging plans for (b) are built from the calibration period only
    (`policy_staging_plans_risk_weights.csv`), so the test year is not scored again. Precision here counts cells
    with an undefined label as not low (slightly lower than in decision 92, which dropped them).
95. **Final checks.** `analysis/99_rerun_check.py` reruns the core pipeline from the raw files (feed regimes, audit,
    30-minute panel, main association models and event study, inference) and compares key numbers with the
    committed values (`outputs/rerun_check.csv`). Not rerun: the downloads (raw data fixed in git), the 15-minute
    and 500 m robustness panels, `03_effects_more`, `05_risk`, and steps 6-8 (rerunning the forecasting would score
    the test year again; the simulation is seeded and its Python/JS parity is checked separately).
    `outputs/requirements-lock.txt` = pip freeze of the analysis environment (Python 3.11.9, macOS arm64).
    `analysis/99_wording_check.py` lists every risky phrase in the deliverables and chart titles for a manual check
    (`outputs/wording_check.txt`).
96. **Final check results.** Rerun from raw (`outputs/rerun_check.csv`): all 21 key quantities identical (regimes,
    audit counts, panel rows and keys, nine main effects, event study, ratio statistic, hotspot count). The
    by-regime heterogeneity statistics differ only in the 4th decimal (heavy Q 32.7521 vs 32.7516) from the
    estimator's convergence tolerance. Wording check: 49 hits, all disclaimers, the labelled simulation scenario
    "demand surge", or software validation; none describes results as demand, waits, revenue or causes.
    Final figure set: 14 charts in `outputs/figures/report/` (PNG + SVG, index in README.md).

# Phase 2 (steps 10-20)

97. **Data for phase 2** (`analysis/prep_phase2_data.py`, `data/static/phase2/SOURCES.csv`): URA MP2019 subzones
    and land use; Census of Population 2020 residents by subzone and age group and by dwelling type (SingStat's
    June 2025 subzone tables returned HTTP 404 from this machine, so the 2020 census is the latest usable source);
    HDB property information geocoded with the OneMap search API; HDB resale prices (Jan 2017 on); private
    transactions 2020-2025 (earlier repo, SHA-256 checked) with project coordinates; destinations from data.gov.sg
    (hotels, tourist attractions, hawker centres, LTA bus stops) and OpenStreetMap (malls, hospitals, offices,
    schools, nightlife / food, taxi points); OSM drivable road network (osmnx); NEA 24-hour forecasts by date.
    Pick-up bays: LTA DataMall needs an API key we do not have; OSM `amenity=taxi` points are used as a partial
    proxy next to the 371 LTA taxi stops / stands.

## Step 10 pre-registration: names and supply geography

98. **Land grid and names.** Land cells = 1 km cells whose centre lies inside an MP2019 subzone (the 374 eligible
    cells are a subset). Each cell gets the planning area and subzone containing its centre (nearest subzone if
    the centre is on a boundary gap), the two nearest MRT/LRT stations with distances, and up to 3 landmarks:
    named destinations within 700 m of the centre, chosen by category priority (tourist attraction, mall,
    hospital, university, hotel, hawker centre) and then by distance.
99. **Rain-hit rankings (fit period, main sample, cells with >= 100 heavy-rain rows).** Absolute: heavy-rain
    ratio statistic per cell against the no-rain model fit0 (step 4) as % change and as taxis per heavy-rain half
    hour (sum fit0 - sum vacant, divided by heavy-rain half hours). Share: the same with fit0 rescaled to the
    observed citywide total at each snapshot. 95% CIs from 1,000 day-bootstrap draws. Top 30 by taxis lost
    (absolute) and by share % change. "Rain-sensitive areas" = rain-response type 0 (step 5); "areas that gain" =
    cells whose share % change CI lies above 0 (and the absolute hotspots "significantly higher").
100. **Dry-weather supply maps.** Mean vacant taxis per cell with no rain at the cell for the past 90 minutes, fit
    period, normal-coverage regimes (0.8-1.25x), by time band 07-10, 10-17, 17-20, 20-24, 00-07 (all days). Maps
    label the 8 highest-supply cells per band by landmark or subzone.
101. **Taxi deserts.** Residents per land cell: Census 2020 subzone residents allocated to cells in proportion to
    MP2019 residential land-use area (subzone x cell intersection); HDB dwelling units per cell from geocoded
    blocks. Supply = mean vacant taxis over all fit-period snapshots (cells never seen in the feed = 0). Taxi
    desert ranking: cells with >= 5,000 residents or >= 2,000 HDB units, ranked by vacant taxis per 10,000
    residents (lowest first); top 25 named.

## Step 11 pre-registration: road network and minutes to the nearest vacant taxi

102. **Graph.** OSM drivable network (osmnx, network_type "drive"), largest strongly connected component. Edge
    speed = OSM maxspeed where tagged, else by road class: motorway 80, trunk 70, primary 60, secondary 50,
    tertiary 40, *_link 40, unclassified / residential 30, service / living street 20 km/h. Dry travel time =
    length / speed x 1.25 (signals and normal congestion); rain-congestion scenario = dry time x 1.25 (speeds 20%
    lower). Both are modelled assumptions, not observed speeds.
103. **Matrices.** 500 m land cells (centre inside an MP2019 subzone) snapped to their nearest graph node; drive-time
    matrices 500 m x 500 m (dry, rain) saved for the simulation (not in git); and from every eligible 1 km cell
    centre to every 500 m cell.
104. **Minutes to the nearest vacant taxi.** For every main-sample snapshot in the fit period: taxi locations = 500 m
    cells with >= 1 vacant taxi (cells off the land grid snap to the nearest land 500 m cell); outcome = dry drive
    time (minutes) from each eligible 1 km cell centre to the nearest such cell (0.5 minute floor). Dry times are
    used so the outcome reflects where taxis are, not assumed congestion. Model: Poisson PML with the main
    specification (light / moderate / heavy + lags | cell + how^month + ym^regime, CRV1 by day), reported as %
    change in minutes; check with log(citywide count) added (coverage). Per-cell heavy-rain effects on minutes
    (ratio of observed to no-rain-model minutes, day bootstrap, as in step 10), named. Processed year by year.

## Step 12 pre-registration: why some areas lose more vacant taxis in heavy rain

105. **Characteristics** (all land cells + other cells seen in the feed; `cell_characteristics.csv`): MRT - distance
    to the nearest station, exits within 500 m of the cell centre, distinct lines and interchange within 800 m,
    a station opened Oct 2021 - Sep 2026 within 800 m (opening dates are only known for those, so "years since
    opening" is replaced by this flag); bus stops in the cell; housing - HDB dwelling units, private projects and
    private transactions 2020-2025 in the cell, share private = private projects' transactions / (that + HDB units)
    as a rough mix indicator, HDB resale median price per sq ft (Jan 2017 on) and private median psf in the cell;
    residents and share 65+ (Census 2020, step 10 allocation); MP2019 land-use shares (residential, commercial incl.
    hotel / white, business, institution, park) and URA Central Area flag; destinations in the cell (malls,
    hospitals, hotels, offices, schools incl. tertiary, nightlife, food outlets, attractions); LTA taxi stops /
    stands and OSM taxi points within 300 m of the cell square; road length per km2 by class (expressway,
    arterial = trunk / primary, other), distance to the nearest expressway node, betweenness (networkx sampled
    betweenness, k = 500 sources, on the expressway-to-secondary skeleton; cell value = max over its nodes);
    distance to Raffles Place and to Changi Airport.
106. **Outcome.** Per eligible cell, the step-10 heavy-rain effects as log ratios: abs = log(1 + abs_pct/100),
    share = log(1 + share_pct/100), with SE = (log upper - log lower) / 3.92 from the day-bootstrap CI.
107. **Design (i), cell level.** Weighted least squares of each outcome on standardised characteristics (count
    variables as log(1 + x)); variables with VIF > 10 are dropped one at a time (highest first); weights =
    1 / (SE^2 + tau^2), tau^2 by method of moments. Moran's I of residuals with 8-nearest-neighbour weights; if
    p < 0.05, a spatial error model (spreg, ML) is reported next to WLS. Random forest (500 trees, min leaf 5,
    seed 2702) with spatial block cross-validation (5 km blocks, 5 folds) and SHAP values for the importance
    ranking. Rain-response type (step 5: type 0 vs 1) predicted by logistic regression and random forest with the
    same spatial CV (AUC).
108. **Design (ii), panel.** Poisson FE (main specification, fit period, CRV1 by day) with heavy rain interacted
    with: MRT distance bands (< 300 m, 300-1000 m; reference >= 1000 m), URA Central Area, taxi stop / stand within
    300 m, any mall in the cell, log HDB units (standardised), distance to Raffles Place (standardised). Absolute and
    share versions. Plain-English contrasts are computed from these coefficients with delta-method CIs.

## Step 13 pre-registration: natural experiment from new MRT stations

109. **Cohorts.** Station openings with at least 9 months of panel data before and after: TEL3 (13 Nov 2022), TEL4
    (23 Jun 2024), Punggol Coast (10 Dec 2024), Hume (28 Feb 2025). TEL2 (Aug 2021) has no pre-period in the data
    and CCL6 (12 Jul 2026) only 2.5 months after; both are excluded. Treated cells: eligible 1 km cells whose centre
    is within 800 m of a station of the cohort. Controls: eligible cells more than 2 km from any station opened
    Oct 2021 - Sep 2026, 3 nearest neighbours per treated cell (Mahalanobis, without replacement within a cohort)
    on the pre-period (12 months) mean log dry vacant taxis, distance to Raffles Place, URA Central Area and distance
    to the nearest existing MRT station.
110. **Outcomes and models (stacked by cohort, window -12 to +12 months around opening).**
    (a) Dry-weather supply: cell-month log(mean vacant + 0.1) in dry snapshots (no rain for 90 minutes); event study
    with event-month bins (-12 ... -2, 0 ... +12; reference -1) x treated, FE cell x cohort and month x cohort, SE
    clustered by cell; pre-trend test = joint Wald test of the pre-period coefficients; DiD = average post minus
    pre. (b) Heavy-rain effect: Poisson FE on the stacked cell-snapshot panel (main sample rows of treated and
    control cells), regressors light, moderate, heavy and heavy x post, heavy x treated, heavy x treated x post, FE
    cell x cohort, how^month x cohort, ym^regime x cohort, CRV1 by day. The triple interaction is the DiD in the
    heavy-rain effect. Post-period months after Sep 2025 are in the test year: that use is logged.
111. **What it can show.** Whether vacant supply near a new station, and its drop in heavy rain, changed after
    opening relative to similar cells. It cannot separate taxi supply from changes in rider demand, other
    contemporaneous changes near the stations, or feed-coverage changes that differ by area; few treated cells.

## Step 14 pre-registration: taxi stands and planning map

112. (a) Poisson FE panel (fit period, main specification, abs and share, CRV1 by day) with heavy rain x "LTA taxi
    stop / stand or OSM taxi point within 300 m of the cell" and the step-12 controls (heavy x MRT distance bands,
    Central Area, mall, HDB units, distance to Raffles Place). (b) Candidate stand locations: eligible cells with no
    LTA stop / stand and no OSM taxi point within 300 m that are either among the 100 most rain-hit cells (taxis
    lost per heavy half hour) or taxi deserts (step 10 list), ranked by taxis lost per heavy half hour (rain-hit)
    and by residents (deserts); feasibility notes are qualitative only (arterial road in the cell, MRT exit within
    300 m, mall / hospital in the cell, residential share) - no cost or kerb-space data. (c) Predicted heavy-rain
    effect for every land cell from the step-12 random forest (absolute version); cells outside the 374 analysed
    cells are marked "predicted"; summarised by planning area and subzone (resident-weighted mean).

## Step 15 pre-registration: planning value of morning forecasts

113. Unit: planning area x time band (10-17, 17-20, 20-24) x day; outcome = number of low-availability
    cell-half-hours (deficit >= 0.5, baseline >= 4, retrospective label; the issue-time label as a check).
    Information by 09:00: weekday / day type / month, climatology (fit-period mean for area x band x day type), the
    area-band mean over the previous 7 days and the previous day's value, citywide trailing coverage level; forecast
    features = the latest NEA 24-hour forecast issued before 09:00 that day: general forecast category and the
    category for the area's region in the 12-18 and 18-06 periods (codes: fair 0, cloudy 1, showers 2, thundery 3),
    max relative humidity and temperature. Models: Poisson GLM and LightGBM (poisson) with and without the forecast
    features; fit Apr 2022 - Mar 2025; LightGBM rounds by early stopping on Apr - Sep 2025; test year scored once
    and logged. Material if the test-year Poisson deviance falls by >= 2% with the forecast AND the 95% day-block
    bootstrap CI of the improvement excludes 0.

## Step 16 pre-registration: dose, duration and after-effects

114. (a) Intensity-response: natural cubic spline of mm/h (knots 1, 2.5, 5, 10, 20, 40; boundary 0 and 80, values
    above 80 capped) replacing the bands in the main abs and share models, plus lags; curve relative to dry with
    delta-method CIs. (b) Duration: current band x wet-spell length bins (<= 30, 31-60, 61-120, > 120 min at the
    nearest gauge). (c) Hangover: in rows with no rain now, dummies for minutes since rain ended at the cell (bins
    of 30 min up to 180) against rows dry for >= 6 hours; current rain bands kept, lags dropped (they overlap).
    (d) Recovery by rain-response type: the step-3 event study run separately for type 0 and type 1 cells; recovery
    time = first event bin after onset from which every later bin's CI includes 0.

## Step 17 pre-registration: redistribution and spillovers

115. (a) Island-wide rain = at least half of the working gauges record rain in (t-30, t]. Per-cell share change
    during island-wide rain vs the share benchmark (step 10 method), day-bootstrap CIs; named gainers and losers
    (CI excludes 0) and their characteristics compared with WLS on the step-12 kept characteristics. (b) Spillover
    model: own band + rain within 2 km (dry / light / heavier, cut at 2.5 mm/h) + 2-5 km ring (same bins) together,
    abs and share.

## Step 18 pre-registration: rain measurement error

116. Distance from each cell centre to its nearest working gauge, per day. Main abs and share models estimated
    separately for cell-days <= 1 km and > 1 km from the nearest working gauge, and with heavy x far
    interactions. Attenuation indicator = far / near coefficient ratio. Reliability ratio of the cell rain measure
    = cov(nearest gauge, second-nearest gauge) / var(nearest gauge) over cell-snapshots (classical error
    assumption); headline effects divided by it give an indicative corrected size (log-linear approximation).

## Step 19 pre-registration: fleet trend

117. Heavy-rain effect per calendar month, Oct 2021 - Sep 2026 (test-year months included, logged; association
    only): abs model (cell + how + regime FE) and share model (cell + snapshot FE) per month, months with >= 2,000
    heavy-rain cell-snapshots. Meta-regression of the monthly log effect on the LTA total taxi fleet (thousands),
    log feed coverage level (regime), and season, weights 1 / (SE^2 + tau^2), HC1 errors; slope reported as the
    change in the heavy-rain effect per 1,000 fewer taxis.

## Phase-2 data note: HDB block locations

118. OneMap's public search allows about one request per second and returned repeated 429 responses, so neither
    per-block (13,393 requests) nor per-street (657) geocoding was practical. HDB Property Information blocks are
    instead matched to the data.gov.sg HDB Existing Building footprints by block number inside the block's HDB
    town (town code mapped to URA planning areas); where a street geocode had already been collected (75
    streets) the footprint nearest that street is used; where several footprints with the same block number lie
    in the town, the one nearest the median of the street's already-matched blocks is taken. Result: 10,187 town
    matches, 1,701 street matches, 1,067 street-median matches, 437 unmatched; 1,142,558 of 1,179,156 dwelling
    units (96.9%) located. Steps 10 and 12 are rerun with these units.

## Step 20 pre-registration: simulation v2 (written before any v2 run)

119. **Diagnosis of the step-8 failure.** For each of the 24 tuned step-8 combinations, on the 20 fit-period
    storms (no test-year data) and, for reporting only, on the 10 held-out storms (logged): (a) level - mean of
    simulated minus observed relative citywide vacant series; (b) timing - correlation over time of the two
    relative series and the gap between the minutes of their minima; (c) spatial pattern - correlation across
    cells of mean vacant taxis over the window and of the change from start to rain peak. (d) Noise floor - the
    same +-20% / 70% rule applied to two references that are not simulations: the normal path (citywide panel
    baseline relative to the start) and the statistical path (each cell's baseline times exp(main-model band
    effect for its rain band), summed). If the references also fail most storms, the rule is stricter than
    storm-day feed variation allows; this is reported, and the rule itself is NOT changed.
120. **v2 model changes (all else as items 72-79).** (1) Travel: drive times between the 374 eligible 1 km cells
    from the step-11 OSM matrices (each 1 km cell represented by the 500 m land cell nearest its centre); trip
    time = approach + drive time + 2 minutes; "rain congestion" uses the step-11 rain matrix for trips starting in
    a raining cell. (2) Dispatch rings by drive time from the taxi's cell: <= 4, 4-7, 7-10 minutes (nearest);
    widening adds 10-15 and 15-20 minutes. (3) Requests and destinations: cell weights from a Poisson regression,
    on fit-period dry daytime (07-24) snapshots, of mean vacant taxis per cell on the step-12 kept
    characteristics ("characteristics" pattern), or the observed fit-period dry mean vacant taxis per cell
    ("observed" pattern, an empirical benchmark); destination choice = weight x exp(-drive minutes / 15). (4)
    Supply response in rain scaled per cell by the step-12 random-forest predicted heavy-rain effect (cells with
    predicted gains get no extra offline probability; scale normalised to mean 1). Grid: mechanism (demand,
    supply, mix) x pattern (characteristics, observed) x travel (dry roads, rain-congested roads) x dispatch
    (nearest, widening) = 24 combinations; tuning exactly as item 75 (Optuna, 12 trials, seed 2702, 20 fit
    storms, same loss).
121. **v2 plausibility.** Same rule as item 76 on the same 10 held-out storms (logged). If no v2 combination passes,
    the page presents the simulation only as an illustration and says why (using the item-119 diagnosis).
122. **Dispatcher panel.** On the page, at every 30-minute decision of a replayed storm, list the top staging moves
    of the step-7 greedy plan (from area -> named place, taxis, reason). Reason rules, fixed: "rain approaching"
    if the destination cell is dry now but rain is recorded within 5 km in the current slot; "rain-sensitive
    area" if the destination is a step-3 type-0 cell or its step-12 predicted heavy-rain effect is below -20%;
    otherwise "forecast risk" (expected shortfall from the persistence forecast). Labelled throughout:
    "demonstration on historical replays, not a live system".

## Fixes after the second independent review of phase 2 (commit 37081c1)

123. **HDB block matching (review item 4).** The earlier match (decision 118) could take a footprint from a
    different street with the same block number, used the nearest footprint outside the town as a fallback and
    left 54 postal codes claimed by blocks of different streets. Now: candidates must lie inside the block's
    HDB town (never outside); each street's footprint street code (ST_COD) is the consensus (>= 80%) of its
    blocks with exactly one candidate in the town; a block is accepted only if exactly one candidate footprint
    carries that street code and its postal code is not claimed by another street. The street-geocode and
    street-median rules are dropped. Result: 12,929 of 13,392 blocks located (1,139,610 of 1,179,156 dwelling
    units, 96.6%); rejected: 380 blocks on streets without a clear street code, 79 with no footprint of that
    block number in the town, 4 blocks on 2 postal codes claimed by different streets. "Located" is coverage, not
    verified accuracy. Steps 10, 12 and everything downstream are rerun.
124. **MRT lines and exits (review item 5).** Station codes such as "NS24-NE6-CC1" were parsed to their first
    prefix only, so no station counted as an interchange and `interchange_800m` was constant (dropped as such in
    the VIF step). All prefixes are now used (27 interchange stations; 24 with two lines, 3 with three), lines
    within 800 m are counted over all prefixes, and interchange goes through the VIF step like any other
    characteristic. The "exit" variables now use the 545 MRT exits in `sg_mrt.json` (LRT-only exits excluded):
    `dist_mrt_exit_m` (distance to the nearest MRT exit) replaces the station distance, and MRT exits within
    500 m count exits only. The step-12 panel bands (< 300 m, 300-1,000 m, >= 1 km) and step 14 use exit distance.
125. **Prediction transform (review item 2).** The random forest's imputation (median) and standardisation (mean,
    sd) are fitted on the 374 training cells and stored with the model; step 14 (all 778 land cells) and the
    simulation-v2 inputs apply that stored transform unchanged instead of re-standardising on the new rows.
126. **Registration timing for steps 10-11 (review note).** The step-10 and step-11 specifications (decisions
    98-104) and their first outputs were committed together (commit 00be15d), so the order "registered before
    run" cannot be verified from the repository for those two steps. Steps 12 onwards were registered in earlier
    commits than their results, except where a later fix is recorded as such.
127. **Simulation request/taxi conservation (review item 1, Critical).** In both engines (step 8 `sim_engine.py`,
    step 20 `sim_engine_v2.py`) and both JavaScript ports, every taxi cell in a dispatch ring could take the same
    waiting requests (each source took up to all requests in its ring), so trips exceeded requests (for example
    11,469 requests and 21,486 trips on one storm), and request removal used outgoing instead of incoming
    adjacency (wrong for the asymmetric drive-time rings). Fix: requests are integers (abandonment is binomial
    with probability 1/6 per minute, the same geometric patience with mean 6 minutes); within each ring, taxi cell
    i offers min(V_i, P_i) over the requests it reaches, request cell j accepts at most its Q_j of the offers it
    receives through incoming adjacency, and both sides are rounded with one systematic offset, so taxis
    dispatched equal requests served, no request is served twice and no taxi leaves twice. Every simulated minute
    asserts that vacant + offline + in-flight taxis equal the fleet and that trips do not exceed requests;
    `tests/test_sim_conservation.py` fails on the old rule. All step-8 and step-20 simulation results produced
    before this fix are void and are replaced by reruns with unchanged tuning settings and the unchanged
    plausibility rule (items 75-77, 119-121). Parity tolerance, as checked: mean within 5% and peak within 5% or
    0.01 absolute.
128. **Simulation reruns.** Steps 8 and 20 are retuned (Optuna, 12 trials, seed 2702, same ranges and loss), the
    plausibility rule is re-run unchanged on the same 10 held-out storms (logged), the diagnosis (item 119) is
    redone, and the step-8 grid (50 seeds) is re-run.
129. **Step 13 corrections (review item 6).** Matching now uses the registered cohort-specific distance to the
    nearest MRT station already open before each cohort's opening date (it used today's station network). The
    heavy-rain DiD adds the missing lower-order term treated x post (treated and post are absorbed by the cell x
    cohort and ym^regime x cohort effects; heavy, heavy x post and heavy x treated were already in).
130. **Step 19 corrections (review item 8).** The coverage control is now the registered regime coverage level
    (feed_regimes.csv log level, averaged over the month's days) instead of the daily level, and the
    meta-regression uses Newey-West HAC errors with 3 lags (rule of thumb floor(4 (n/100)^(2/9)), n = 55
    months) on months in calendar order. Monthly effects are reused unchanged. Extrapolations about future
    fleet sizes are removed.
131. **Step 15 timing corrections (review item 3).** Everything in the morning model is now knowable at 09:00:
    previous-day and previous-7-day history come from the issue-time label only (never the retrospective label);
    exposure is the scheduled exposure (eligible cells in the planning area x half-hours in the band) instead
    of the realised later-day count of observed cell-half-hours; the GLM's missing-value imputation uses
    training-row medians only; and per day the single latest NEA 24-hour forecast issue before 09:00 is used (all
    of its periods), not the latest row per period. Climatology uses the fit-period rows of the modelled label.
    The test year is re-scored once (logged); all model x label results are reported.
132. **Step 18 wording (review item 7).** The "corrected" effect (-17.5%) and the claim that the headline is
    understated are withdrawn: the reliability ratio rests on a classical-error assumption the near/far
    comparison does not support. Gauge agreement and the near/far comparison are reported as sensitivity
    diagnostics only.
133. **Named lists for presentation (review item 9).** Every cell effect gets a two-sided day-bootstrap p-value
    and a Benjamini-Hochberg q-value across the 374 tested cells (abs and share separately). Lists used in the
    summary, recommendations and map labels show only cells with >= 4 expected vacant taxis in heavy rain and
    q < 0.10; full sorted lists stay as appendix tables (`*_all.csv`, `rain_gainers.csv`,
    `spillover_islandwide_share.csv`). Every share percentage is shown with the absolute change in taxis per
    heavy-rain half-hour and its CI. "Gather" or "more taxis" is used only where the absolute change has a CI
    above 0; otherwise "gains share". The minutes-to-taxi result is described as associated with the citywide
    drop (a conditional association), not "explained" by it.
134. **Taxi deserts (review item 11).** Recomputed on dry snapshots only (no rain at the cell for 90 minutes,
    normal-coverage regimes, all hours, Apr 2022 - Mar 2025) per resident, analysed cells only, so the
    "dry-weather" wording is kept. The earlier ranking used the all-weather model mean and included cells
    without reliable taxi data.
135. **Recovery wording (review item 12).** Recovery times are reported as the registered statistical recovery
    criterion (from 120 / 150 minutes after onset every later event-study CI includes zero), not as "back to
    normal".
136. **Step 12 reporting (review item 10).** WLS, spatial-error and panel-interaction results are reported
    separately; only characteristics supported in all designs that test them are called robust.

## Follow-ups after the review fixes

137. **MRT line rule.** Lines are MRT lines only. Every prefix in a station code counts, with or without a number
    ("NE17-PTC", "EW4-CG"); LRT codes (BP, PTC, STC, SW, SE, PE, PW) are not lines; the Changi Airport branch CG
    counts as EW. Result: 25 interchange stations (Bukit Panjang and Choa Chu Kang are no longer interchanges;
    Punggol, Sengkang and Tanah Merah stay single-line). The interchange flag changed for 4 eligible cells
    (Gombak, Keat Hong, Senja, Choa Chu Kang North) and MRT lines within 800 m for 29, so step 12 (cell-level
    designs, charts) and the step-14 prediction map were rerun; the step-12 panel does not use these variables
    and the step-17 regression and simulation-v2 inputs were not rerun.
138. **Trip origin in the simulators.** After the allocation in a ring, trips now start at the request cells
    (the cells whose requests were served) instead of at the taxis' cells; the approach time is unchanged. Both
    Python engines and both JavaScript ports. The change moved the training loss of 5 of 48 tuned combinations by
    more than 1% (largest 1.44%; seed-to-seed noise at most 0.45%), so, as agreed, both versions were retuned
    with unchanged settings and the unchanged plausibility rule was re-run (logged), followed by the step-8
    grid, the step-20 diagnosis, charts, pages and parity.

## Third independent review (of commit 078c8bc)

139. **Allocation by integer edge flows (review item 1).** The decision-127 allocation rounded taxis dispatched
    and requests served separately, so its totals were sometimes not achievable by any matching within the ring
    (the reviewer found 121 of 3,000 small cases, shortfall up to 2). Now (`analysis/sim_alloc.py`, same algorithm
    in `sim/engine.js` and `sim/v2/engine_v2.js`): the proportional fluid flow on every permitted taxi-cell ->
    request-cell edge is floored (feasible by construction); the remaining units, as many as the summed fractional
    parts rounded with one uniform offset, are placed one at a time along permitted edges in a seeded random order
    weighted by the fractional parts, never exceeding the taxis left at i or the requests left at j. Taxis
    dispatched and requests served are the row and column sums of these integer edge flows. Tests: 3,000 random
    asymmetric rings checked against an exact max-flow (scipy maximum_flow), a per-ring partner check, and a
    constructed five-cell world with overlapping rings that fails on the 37081c1 engine (745 requests, 823 trips
    on seed 1) and passes now; the old real-data integration test, which passed on the old engine, is removed.
140. **Simulation-v2 inputs from the final step-12 bundle.** `sim/v2/data.json` (characteristic weights through the
    stored training transform, per-cell offline scales from the step-14 predictions of the final random forest)
    is rebuilt after decision 137's step-12 rerun.
141. **Parity runs are logged.** Python/JavaScript parity runs use held-out (test-year) storm inputs only, no
    observed outcomes; they are now logged in `test_scoring_log.csv`, and the six earlier parity runs are added
    with times reconstructed from the commits that changed the parity tables.
142. **Benchmark wording.** The non-simulation path (baseline x estimated rain effects) that passes 3 of 10
    held-out storms is a benchmark that also fails the rule. It is not called a noise floor and is not taken as
    proof that the rule is too strict (table renamed `sim2_benchmark_paths.csv`).
143. **Final simulation iteration.** Both versions retuned with unchanged settings, the unchanged plausibility rule
    re-run, then the diagnosis, step-8 grid, parity and both pages. These are the reported simulation results;
    no further simulation changes follow.
144. **Step 17 characteristic regression regenerated** with the final characteristics (decision 137) and the
    current share results; MRT lines within 800 m is no longer significant there (it was p = 0.039 in the review-B
    run), so no wording relies on it.
145. **Step 15 block-bootstrap sensitivity.** The registered day-bootstrap CIs stay the reported ones. Daily
    deviance gains are correlated across adjacent days (lag-1 autocorrelation 0.37 retrospective / 0.24 issue-time
    for the flexible model), so a moving-block bootstrap with 7-day blocks is added as a sensitivity. Point
    estimates are unchanged (same models and seeds); the re-run is logged as a test-year use.
146. **Wording after the third review.** The withdrawn measurement-error correction is reduced to one line in the
    progress log; stands are described as supported in both cell-level designs but not the panel, hence not
    robust; recovery uses the registered statistical criterion; the summary states that the morning models were
    refitted once after the reviewer-required feature fixes (corrective refit) and that no model was tuned on
    test-year outcomes.

## Step 21 pre-registration: radar rainfall measurement check (25 Oct 2026)

147. **Separate analysis; frozen results unchanged.** The requested number 139 is already occupied by the final
    simulation fixes, so this specification uses the next free number, 147. This entry and the step-21 code are
    committed before any step-21 taxi outcome model is fitted. No frozen model is retuned or re-scored, and no
    test-year data are read. The frozen gauge-based estimates remain the headline.

    **Data and attribution.** Zhuang, Q., Peleg, N., Prein, A., Babovic, V., & Fatichi, S. (2026),
    *High-Resolution Radar–Gauge Merged Rainfall Dataset over Singapore (100 m, 5-min and hourly)*, v1, Zenodo,
    https://doi.org/10.5281/zenodo.19642566, Creative Commons Attribution 4.0 International (CC BY 4.0).
    Archive `5min_SG.zip`, 10,087,581,305 bytes, expected MD5 `5d97d0700c23d028fa6e6977485359f7`, stored in
    gitignored `data/static/phase3/radar/`. The entire archive checksum must match before production preparation
    and fitting. This is a radar–gauge merged KED product, not independent radar truth: agreement with gauges
    can partly reflect the gauges used to build it. Frozen gauge processing is not changed.

    **Inspection before fitting.** Selected daily files contain `rainfall(time, lat, lon)` float32, `lat`, `lon`,
    and `time`; 288 steps/day, 311 latitudes and 532 longitudes. Rainfall has NaN `_FillValue` and no units
    attribute; the publisher specifies mm per five-minute interval and UTC+8. Time units are minutes since
    local midnight, values 0, 5, ..., 1435. Latitude decreases by 0.000904356172 degrees and longitude increases
    by 0.000909397338 degrees (nominal 100 m pixels). No CRS/datum or EPSG metadata are supplied; coordinates
    are geographic longitude/latitude over Singapore and are compared directly to gauge coordinates, without
    inventing a native projected CRS. Range inspection lists all 1,827 calendar days, 2020-01-01 to 2024-12-31;
    full-archive inventory and in-scope missing-value/day audits will be saved before fitting.

    **Clock identification, not a guess.** Fix five storm days spanning the sample: 2022-12-11, 2023-07-20,
    2023-12-25, 2024-05-14, 2024-12-29 (existing fit-storm list, no taxi outcomes used in this check). Compare
    nearest gauge pixels with our five-minute gauge depths, shifting radar labels by -10/-5/0/+5/+10 minutes.
    Initial checks give the largest correlation at zero shift on all five days (0.969-0.994; adjacent shifts
    0.826-0.874). This supports interpreting radar labels as interval ends, aligned with gauge end labels.
    Repeat and save the checks from the checksum-verified archive; stop rather than fit if alignment disagrees.

    **Preparation.** `analysis/prep_radar.py` averages equally weighted nominal 100 m pixel centres inside
    each of the same 374 eligible 1 km cells. Land support is the intersection of the repaired existing
    Singapore coastline polygons and the product's fixed finite footprint; no sea-pixel rainfall is used.
    Prepare the four nested 500 m subcells of each eligible 1 km cell, plus a 2-5 km annulus and a within-2-km
    neighbouring-land control (own 1 km cell excluded), using the project's existing metric grid. Save land
    pixel counts and zero-support cells. Require all selected land pixels per step and all six five-minute
    depths per half hour; any missing value gives a missing window, never zero. Include 31 Mar 2022 as warm-up
    only. mm/h = 2 times summed depths in (t-30, t]; lag windows (t-60, t-30] and (t-90, t-60]. Save local
    five-minute means and half-hour Parquet files under `data/interim/`, gitignored.

    **Sample and paired fits.** Apr 2022-Dec 2024 inclusive, same eligible cells, regimes and main exclusions
    as step 3. Use the intersection of finite gauge/radar current and lagged own rain, annulus rain and
    neighbouring rain, and report all sample losses. Every source/model pair uses identical taxi observations;
    all five model designs use this common sample. No calibration or test-year files are loaded. Standard
    errors cluster by calendar day. Main absolute Poisson FE: cell + half-hour-of-week x month + year-month x
    regime; share model: cell + snapshot FE. Both include current light/moderate/heavy dummies and two
    continuous source-specific own-rain lags. Bands: dry 0; light (0,2.5]; moderate (2.5,10]; heavy >10 mm/h.
    Repeat all designs with values <=0.1 mm/h recoded dry in current/lagged rain and onset dry histories;
    thresholds are not selected from outcome results.

    **Other registered designs, each gauge vs radar.** (c) Absolute main model plus heavy x URA MP2019 Central
    Area flag from frozen step-12 characteristics; report inside/outside contrasts and interaction with their
    covariance. (d) Absolute approaching-rain model: own cell dry for 90 minutes, interacted with annulus
    light/moderate/heavy bands, controlling the analogous within-2-km bands and main regressors. The requested
    annulus-heavy term is >10 mm/h (not the older >2.5 mm/h combined category). (e) Absolute event study with
    the frozen onset algorithm separately on each source: >=1 mm/h after four dry half-hours, merge onsets
    within 180 min; bins -60 to +180 min, reported relative to -30 min. Radar defines the radar onsets; gauge
    defines the gauge onsets. Otherwise identical outcome rows and FE; holding onsets fixed across both would
    give identical regressions and would not test the rainfall measurements.

    **Measurement agreement.** At nearest grid pixels to available gauge coordinates, report correlation,
    additive bias, total ratio, wet/dry agreement and heavy-rain agreement, with confusion counts, sensitivity
    and precision. Report five-minute rates and half-hour rates (>10 mm/h heavy), wet thresholds 0 and 0.1.
    Restrict to working, non-stuck gauge-days with >=287 archived readings. Midnight, generally absent from
    the gauge daily archive, is missing rather than assumed dry; half-hour comparisons require all six bins.
    This diagnostic is not an independent validation of a gauge-merged product.

    **Interpretation and outputs fixed now.** Report all designs and the dry-threshold check side by side,
    regardless of sign or significance, in `outputs/tables/radar_*.csv`; one effect/CI figure covers rain bands,
    share and Central Area. Gauge/radar differences also reflect spatial averaging and the merging procedure.
    Absolute-model effects are also expressed as a change per 10 no-rain expected vacant taxis, with observed
    counts by source and rain band in a separate frequency table; share changes are not relabelled count gains.
    A larger radar association is consistent with gauge measurement error weakening estimates, but does not
    identify attenuation or justify a correction. Append results to the progress log and a labelled radar
    subsection under summary uncertainty; do not replace any frozen table, figure, threshold or conclusion.

148. **Verified radar data audit, before taxi model fitting.** The complete 10,087,581,305-byte archive matches
    MD5 `5d97d0700c23d028fa6e6977485359f7`. All 1,827 daily NetCDF files from 2020-01-01 through 2024-12-31 are
    present; there are no absent archive dates. All 1,007 daily coordinate arrays and shapes in the analysis
    period plus the 31 Mar warm-up match exactly. Variable, axis, fill-value, units and CRS details are in
    `radar_metadata.csv`; no undocumented projected CRS has been assigned. NaN encodes the fixed offshore
    mask and potentially missing values, never dry weather. The fixed product footprint has 71,558 pixels;
    intersecting it with the repaired frozen coastline leaves 71,209 land pixels. Each of the 374 eligible
    1 km cells has 4-100 land pixels. Eight of their 1,496 nested 500 m cells have no land pixels, so their
    rainfall is missing, not imputed; this includes one of the 793 frozen eligible 500 m cells (60024).
    Pixel counts are in `radar_land_pixel_coverage.csv`; all 793 eligible 500 m cells are included in preparation.

    The checksum-verified archive repeats the five-day clock check using the registered near-complete,
    working-gauge restriction: zero-shift correlations are 0.9882, 0.9956, 0.9679, 0.9902 and 0.9790 in date
    order; all exceed both adjacent shifts (0.8173-0.8718) and the +/-10-minute shifts. Five-minute radar/gauge
    total ratios are 1.007, 1.004, 1.051, 1.002 and 1.038, also consistent with the publisher's mm-depth units
    rather than rates in mm/h. Accordingly labels are treated as interval ends, with no clock adjustment.
    `radar_clock_check.csv` preserves all shifts, including the losing ones. Full daily missing-value coverage
    is audited during preparation before fitting. Additional code guards check daily grid coordinates on
    rerun; direct script execution is supported. These are input checks, not choices based on taxi outcomes.
    The completed daily audit finds no missing files, all-missing five-minute steps, or missing selected land
    values on any of the 1,007 prepared dates (including warm-up). The zero-support 500 m cells remain missing
    by definition; they are not missing-data days. The gauge-pixel comparison is retained as a non-independent
    measurement diagnostic: half-hour r = 0.98864, radar/gauge total ratio 1.01820, wet agreement 97.70% at zero
    and 99.17% at 0.1 mm/h, heavy agreement 99.9278% (sensitivity 96.30%, precision 95.74%).

149. **Post-fit support diagnostic, labelled as such.** The primary radar approaching-heavy-rain CI is wide,
    so the existing registered contrast was counted by source and both registered dry thresholds, with no
    additional model or sample filter. At zero there are 5,708 gauge cell-snapshots on 375 days but only 52
    radar cell-snapshots on 29 days; at 0.1 mm/h there are 210 radar rows on 78 days. All counts are reported
    in `radar_approach_support.csv`, rather than omitting this imprecise contrast or choosing a dry threshold
    after seeing it. The point estimates, estimator, controls and full common sample are unchanged.

## Step 22: regional storm forecasting on a fresh holdout (registered before download)

150. **Specification and execution order, fixed before downloading October 2026 or fitting step-22 models.**
    Why: steps 6 and S1 found no material weather gain for individual cells, 2 km cells or planning areas.
    Step 3 found about 7% fewer vacant taxis when rain was 2-5 km away before local rain arrived, and most
    of the drop is regional or citywide. Step 22 tests regional targets, approaching-rain features and storm
    windows on genuinely new data, 1-24 October 2026. It is a separate analysis; all frozen results remain.

    **Order and boundaries.** Commit this specification first. Then download only 1-24 October 2026 with
    `pipeline.fetch_month` and audit snapshot presence, timestamp offsets and gauge completeness; do not
    construct October targets, labels or scores. Develop using April 2022-March 2025 for fitting and
    April-September 2025 for calibration/model choice. October 2025-September 2026 outcomes cannot inform
    any choice. After all settings and scoring code are fixed, refit on April 2022-September 2026, save
    models and preprocessing, record SHA-256 hashes here, and commit AND push the freeze before opening
    October targets. Score October once, log "fresh holdout, scored once", and report every registered
    combination without changing methods or models after seeing its results. Log the final fixed-setting
    refit on the old test year separately; it is training for this new analysis, not a new tuning sample.

    **Units and timing.** Six overlapping units: URA Central Area and the five URA regions (Central, East,
    North, North-East, West), using the same 374 analysed 1 km cells, joined by cell ID to URA geography.
    The Central Area is also part of Central Region; do not treat the six results as independent.
    Use only :00/:30 snapshots. Historical taxi exclusions stay as registered. On October use only the
    audit's missing/invalid timestamp exclusions, without estimating new regimes or dropping low counts.
    The final model uses recent levels to adapt to a possible new coverage regime. An evaluation pair
    needs valid issue and target snapshots and exact 30/60/90-minute count lags. Targets must lie inside
    their split (no training targets in calibration and no targets beyond 24 October).

    **Issue-time expected levels and targets.** Fit the step-5 Poisson baseline structure (cell +
    half-hour-of-week x month + training feed-regime effects) using each fitting window only. Strip regime
    levels to obtain the seasonal pattern; sum cells for each unit. Refit this baseline inside every
    time-ordered fold, and refit it again at the final freeze. With complete common cell panels its
    balanced-data Poisson fit can be computed from cell totals and citywide slot/regime totals, which
    is algebraically the same model. The coverage factor at issue time t is the trailing 7-calendar-day
    median of eligible-cell citywide count divided by its seasonal pattern, using only snapshots <=t.
    Expected count at t+h is seasonal pattern(t+h) times that factor FROZEN AT t, never a future
    regime level or target-time rolling estimate. Use at least 48 valid trailing snapshots; unavailable
    patterns/history mean missing, not zero. T1 = log(max(Y(t+h),1)/max(expected(t+h|t),1)); the floor
    prevents undefined logs and its use count is reported. T2 = Y(t+h) <= (1-d)*expected(t+h|t), with
    d=0.15 primary and d=0.10,0.20 checks. Horizons are 30 and 60 minutes. Historical training labels are
    built by the same issue-time rule, with no target-time level. Calendar baselines are fitted using
    training data only, including during folds; no future regime levels, dispersion or thresholds enter.

    **Features.** Without weather: current regional and eligible-cell citywide counts, their deviations
    from expected, exact 30/60/90-minute lags, half-hour of week (cyclic plus categorical time indicators),
    month, day type, public/school holidays, the trailing 7-day level, and known target calendar/pattern.
    With weather adds regional rain now and 30/60/90-minute lags, regional gauge wet share, gauge-mean
    rain 2-5 km and 5-10 km OUTSIDE the unit's URA boundary in EPSG:3414, island-wide wet-share change
    over 30 minutes, and summaries of the SINGLE latest NEA 2-hour issue strictly before t over areas
    assigned to the unit (mean/max rain category and issue age; require forecast validity at t).
    Gauge depths become mm/h over (t-30,t], with exact earlier windows as lags. Gauge coordinates and
    membership are keyed by station ID; no row-order joins. Gauge health uses preceding-day completeness,
    not future readings in the current day; sparse raw readings encode reported zeros, with gauge gaps
    documented. Missing weather is imputed using fitting-window medians and missing indicators, unchanged
    on calibration and holdout. Empty geographic rings remain missing. No radar data are used.

    **Models and choices.** Report persistence, seasonal, linear and LightGBM, each without/with weather,
    for T1 and all three T2 thresholds at both horizons. Pool units with unit indicators and report each
    unit as well as the pooled sample. Persistence T1 carries the current log-relative level forward;
    seasonal T1 predicts zero. Their T2 risks use empirical training residual CDFs around those forecasts.
    Their weather versions add a ridge-fitted weather-only residual adjustment (T2 uses the same training
    residual CDF); this makes the two weather-adjusted benchmarks explicit rather than duplicating them.
    Linear means ridge for T1 and logistic regression for T2, with training-only median imputation and
    standardisation. LightGBM uses regression L1/binary objectives, seed 2702, fixed single-threaded
    deterministic settings. Tune small, disclosed grids of ridge/logistic penalties and LightGBM leaf/
    minimum-leaf settings with expanding time folds ending March and September 2024 and March 2025
    (validation is the preceding six months, training is everything earlier). Compare mean fold MAE
    or PR-AUC, not holdout performance. Calibration April-September 2025 supplies early stopping and
    final choice among the two best fold settings; minimise MAE/maximise PR-AUC, ties prefer simpler.
    The final refit uses the chosen penalties/tree counts unchanged; no early stopping on the old test
    year or October. Probability calibration is not added. Baseline residual distributions are training
    only. All preprocessing, baseline coefficients, features, settings and model bytes are hash-frozen.

    **Storms and evaluation.** At each half-hour, compare the same gauges' (t-60,t-30] and (t-30,t]
    rates: an onset candidate has >=25% of working island-wide gauges change from exactly dry to
    >=1 mm/h. Require at least 20 working gauges in both windows; merge candidates within 180 minutes
    of the preceding retained onset. Count onsets dated 1-24 October; storm issue windows extend from
    -60 to +120 minutes around those onsets and are clipped to the holdout. Storm detection is an
    evaluation subset only, not a future-known predictor. Report onsets, working gauges, sample sizes,
    vacant counts, expected counts and event base rates. All times and storm windows: T1 MAE and
    MAE skill versus corresponding no-weather persistence; T2 PR-AUC (average precision), precision
    and recall at an alert fraction equal to that unit/horizon/threshold's CALIBRATION base rate,
    fixed before final refitting (pooled workload is the pooled calibration rate). Report actual
    holdout base rates too. Rank scores within each reported evaluation subset, with chronological
    tie-breaking, and ceil(rate*n) alerts; this evaluates fixed workload without tuning on October.
    Confidence intervals are paired 1,000-draw day-block percentile bootstraps, resampling issue days
    with every unit/time/model together. AP uses exact score ranks (ties grouped), with day-frequency
    weights; no score binning. Report undefined metrics rather than replacing empty classes with zero.

    **Decision rule and power.** The primary materiality comparison pools the six units at each horizon:
    in storm windows LightGBM-with-weather must lower T1 MAE by >=5% or raise primary (15%) T2 PR-AUC
    by >=0.02, with the paired 95% CI excluding zero. Either horizon qualifies. Report all six unit
    contrasts and both threshold checks regardless of direction; these do not create additional primary
    success criteria. Pooled observations overlap through Central Area and Central Region, so bootstrap
    them jointly. If October has fewer than EIGHT onsets, storm-window results are DESCRIPTIVE ONLY:
    report numerical threshold crossings but do not claim confirmed materiality. These are pointwise
    CIs over a short period, not a general guarantee. Vacant taxis measure supply, not passenger demand.

    **Deliverables.** `outputs/tables/s22_*.csv`; one new figure (PNG/SVG) showing paired weather gains
    with CIs by region, horizon and target, all times versus storm windows; append progress and a short
    "Regional storm forecasting (fresh holdout)" summary item. Run wording check and tests before
    each commit. No frozen tables, figures, registered thresholds or models are changed.

151. **Step-22 audit, development and frozen refit (before fresh-holdout scoring).**
    October audit: 2,304/2,304 requested snapshots present; 2,302 have offsets within 10 minutes.
    There are 2,130 complete gauge-days of 2,143 across all 24 dates. No October labels, storm
    counts or scores were computed during this audit or development. Seven coastal cell centres
    use their frozen planning-area name to join URA regions; Central Area remains the 16 cells
    whose centres fall within URA Central Area. Due to the sparse archive,
    unknown midnight gauge intervals are missing, not treated as dry; current-day gauge health
    uses only previous-day completeness. This limitation is retained in all periods.
    Settings in s22_development.csv and calibration alert fractions in s22_alert_rates.csv were
    chosen using data through September 2025 only. Final refitting uses April 2022-September 2026
    with no further selection or early stopping; this old-test-year use is logged. The baseline
    is refitted with the same registered step-5 structure; no October regime level is fitted.
    All models, transforms and executable source are frozen by the following SHA-256 hashes.
    s22_model_manifest.csv repeats the hashes and byte lengths. This commit must be pushed before scoring.
    - `data/interim/s22/30_0_persistence.joblib`: `96e785615e93df181222d59cef4a75c7e837c384061ab08e789ba502959cae3c`
    - `data/interim/s22/30_0_seasonal.joblib`: `5027eeb45d014fb0e73e7349662791d787c51bba9b84b776ce82a6f5e8ede647`
    - `data/interim/s22/30_1_persistence.joblib`: `8682018e3e2f15337ae3a203582b06c807881286a367dc1fb0aa01d0b774b464`
    - `data/interim/s22/30_1_seasonal.joblib`: `a58cf0059258aae9c513fb9c66c25510d5356c5cb3f4983a051aef9a3826f2c7`
    - `data/interim/s22/30_T1_0_lightgbm.joblib`: `cfd7f81198d563d317233b22e8259e30309d8adf0a1725f18db826bd60e12c41`
    - `data/interim/s22/30_T1_0_linear.joblib`: `18aaaa6e95f748636caa15a4a635e80d339bf2bcb4ebee60c0fabd609490f542`
    - `data/interim/s22/30_T1_1_lightgbm.joblib`: `97b12211e95a4c34abc216c5df7e4fbe73ec2b584b2a3a8a69c36e71994fd7db`
    - `data/interim/s22/30_T1_1_linear.joblib`: `18d040da1ce4c5ab8679f60fcb29c37218a3ae4654cbdef5e979bfb79e5d8d74`
    - `data/interim/s22/30_T2_10_0_lightgbm.joblib`: `242e5c1ec4e586475163a1664bea6b78e74f268d6df5a9fe6718f3541c9444fa`
    - `data/interim/s22/30_T2_10_0_linear.joblib`: `25e67691d5896822d968762f6a19992f22cb7dc1cf3883ecb17ff57e36720e4a`
    - `data/interim/s22/30_T2_10_1_lightgbm.joblib`: `f452c7fead7fe41fabd7beb43d83a0484e461e2a93acb5fa1e2410117417e7c5`
    - `data/interim/s22/30_T2_10_1_linear.joblib`: `50e1a2ca5de7d362897b62460a4d6e804b347c74073c0c3986295bcc3a039b4f`
    - `data/interim/s22/30_T2_15_0_lightgbm.joblib`: `8d10100d9fc7586035bdf54eca5d0ac915cbeb0e66b8b9615fc153f7a6037c0b`
    - `data/interim/s22/30_T2_15_0_linear.joblib`: `ed3074a6e74bd487a8221a1006a1f5e0c47741cbf47413bd58818358a60981aa`
    - `data/interim/s22/30_T2_15_1_lightgbm.joblib`: `cbf382bbe2d67cc5b1dd00505434b33bfda4f931410e3ea28f0a928bc88260b3`
    - `data/interim/s22/30_T2_15_1_linear.joblib`: `ab2ca584d7ed3b0df40fa113849cde2798742a986c35556b55dc5d1ce4f0936e`
    - `data/interim/s22/30_T2_20_0_lightgbm.joblib`: `c6f6dbac947ed9ed99b4b961e7d5c354621d957887570e048217cc4ea1bd31a1`
    - `data/interim/s22/30_T2_20_0_linear.joblib`: `d74a146b5e259bd4ff50d704e45bd5e912704be935cb780cd5a5f3d6b897682e`
    - `data/interim/s22/30_T2_20_1_lightgbm.joblib`: `1a232203bb53ab11326823034c4e22fc11893b3e7ece2541de0625fc7560ce71`
    - `data/interim/s22/30_T2_20_1_linear.joblib`: `72a503c428897c50856c704e25922d5f8eca5138acd25364fc844579b2e40cd5`
    - `data/interim/s22/60_0_persistence.joblib`: `8a801e7850a757a34531b0c60fe05b5c844820c0523cc7a5a1faea922ec403aa`
    - `data/interim/s22/60_0_seasonal.joblib`: `7784d465c9ef069e8aceb20c5ce1679c2f489b391b04cc194a383044210170b0`
    - `data/interim/s22/60_1_persistence.joblib`: `73d9db5080f04fabd38a02a13687ecea10fc65873dc0346c8d7176e9e44035b3`
    - `data/interim/s22/60_1_seasonal.joblib`: `2bae1fe568cd7211c376eac9d6134a284c3efc5e976b701899b6723c17ac981f`
    - `data/interim/s22/60_T1_0_lightgbm.joblib`: `f551c6dd0cdb3b30c3d03424306fecd1650e6db7dd1b8ca93fac1fb775e63138`
    - `data/interim/s22/60_T1_0_linear.joblib`: `eda31b49a9f6e5d266177023274f00e08c1ec1b0a46a63453e03c735f93513a9`
    - `data/interim/s22/60_T1_1_lightgbm.joblib`: `6b75cd3c61fe862afb44ab5accdf13f237debad54f32d28bc5b55185555f521e`
    - `data/interim/s22/60_T1_1_linear.joblib`: `f07ea4d50d36b68522fd7a87218f0acaea1c8b2a5304a067276b17ff29ef6df1`
    - `data/interim/s22/60_T2_10_0_lightgbm.joblib`: `eb1efd81b00f57edb7945048b2b40415012d7ea9174922e502cdf7c6da15acc4`
    - `data/interim/s22/60_T2_10_0_linear.joblib`: `a23664641670c26e1850a7f5ffcc19730b9a8bc99f2a0b17218a4e7ccf66f8b6`
    - `data/interim/s22/60_T2_10_1_lightgbm.joblib`: `8072f92c631d8da922c6f03563583c0ee31bb9cbfef707c4d5fd5cac64a356db`
    - `data/interim/s22/60_T2_10_1_linear.joblib`: `74a37584dbb15b0b8c64c21b35d0eb0f3649432ec94cf3b711088798ccaae6fb`
    - `data/interim/s22/60_T2_15_0_lightgbm.joblib`: `5378739e50039c4957fe288ee0a882edc30044f0af272d1b60f578b80c04981e`
    - `data/interim/s22/60_T2_15_0_linear.joblib`: `d409bde499912d16c79a09233516cec7bde760086e9aad691b99fbd589243ab1`
    - `data/interim/s22/60_T2_15_1_lightgbm.joblib`: `a3e6207935443d6786ad5f3a2d425184920ef8748626aef12cd2ae94f69fec3b`
    - `data/interim/s22/60_T2_15_1_linear.joblib`: `28d93d2a42eee485405371538ed4064ab61e859a51ad99ea90a239eb41b6591c`
    - `data/interim/s22/60_T2_20_0_lightgbm.joblib`: `de0dc860c68361b4a0001ba40db8d45142d3389f8ddd7d78cf50050d5e121ee6`
    - `data/interim/s22/60_T2_20_0_linear.joblib`: `36e5c3f7d4f6eb8ba5ad206c081a6210760510c1797ceea04afc1d5353e2e5e5`
    - `data/interim/s22/60_T2_20_1_lightgbm.joblib`: `1b0242b72c76f6ace136caaae2246471a8ca60c92426461ca120b896cdef0c60`
    - `data/interim/s22/60_T2_20_1_linear.joblib`: `db528c5966fd87e28b19e50dd6feaf684679c61605bda61e1908b0b15ff396da`
    - `data/interim/s22/pattern.joblib`: `d2d3c2b9478365fb9c751bbf9bf67887d53e1714289f2aa3ad78afea4ecbb691`
    - `data/interim/s22/selection.json`: `863307d081f5a2ba869aadd80b43ca191321d0070f70bf304876fd11dbfb1622`
    - `outputs/tables/s22_alert_rates.csv`: `fabcbfaaf60377ee6de42f50d35c94a3112b10ac0b40c9f78eb3deffbbadb25c`
    - `outputs/tables/s22_environment.csv`: `7e31c2fa05506d7f1d3b3b9b5bc214f1c77080533e6ed1405243658594c32799`
    - `outputs/tables/s22_selected.csv`: `996dc510dd89931819f0886132e24215f764699c4c6f4265e40859705c0c6955`
    - `data/interim/s22/counts_20260930.parquet`: `ed5cc9f26f6f3fc88484c6f7de572a06a165844c1642ccc7ecc54d735399456f`
    - `data/interim/s22/weather_20260930.parquet`: `37642ed6d71e7643ef04885fa9f8817dfb6e48be3fbfb5e45239d8b827defe88`
    - `analysis/s22_data.py`: `156d8588c197b7e048e826900001af62fa92f446deb72ee4ae1b681a0467ed61`
    - `analysis/22_regional.py`: `1d1fa7477435d8d23f7126f7d4995b32a0c1e4d69d76f110a18d5bb3ccc4a73a`
    - `analysis/s22_metrics.py`: `f53e1b5bdf2b343b816f0c344a5d582527c11f33fbc0945a11d574c0fd3fa157`
    - `pipeline/fetch_month.py`: `4cf9dc6102971c14961b404f96ec7841c7f8857ddcb770b1289695e2cf4030d2`
    - `analysis/common.py`: `bc3ed7bec15283308009c9afd3e3e2e6fde3cfc61405c9652b8a2fd9f6f76cd3`
    - `analysis/geo.py`: `1e9775229541a730d8a162ffd9497718e8480e5ea0d75e354827a7961f602ca1`
    - `analysis/01_panel.py`: `a2691e305ad024d42c40f00f7b49554146da1f4c8b92f3fd0c94d3e0b6759e23`
    - `pipeline/grid.py`: `99ef2697c94182853ec2113a84273d165c73611b9abc3182ede342cfbfcb8b41`
    - `data/static/holidays.csv`: `08b42727c7362a3b63fe690b85cbe2b5c2271b6ae93c74e58a84101729bd4cdd`
    - `data/static/phase2/subzone.geojson`: `77e30aa02b1784b649d9b6f23e3b2ebb825af787de554f3a3fb76bbee3013c42`
    - `outputs/tables/s22_unit_cells.csv`: `55791d66e6a6d1bcba6b28e29f94b465b1f45946d06f4c64b1e5324563aec9d2`
    - `data/interim/cells.parquet`: `d3ea92fb1ff80b3ab31df627f98d0fafb8a7cfaeffba60b569d75919b3f8bb96`
    - `analysis/s22_audit.py`: `177c289d66394e45323491b49c10f0f43f0a3477ec677528a899e99cb7744e19`
    - `outputs/tables/s22_audit_snapshots.csv`: `b20ee3094721ea8866410cb27796d8a500f3e11151214fe70108ce165c5b3e4c`
    - `outputs/tables/s22_audit_summary.csv`: `a14595e30b888f77c7dc9e6f66eac81723dd4d744d241cbe5a21ae012b0a097c`
    - `outputs/tables/s22_audit_gauges.csv`: `32b3eef0e7296d6f76062e8dbd33a095c93ecd516e00f6fc77eb9bda8f813119`
    - `outputs/tables/s22_audit_gauge_days.csv`: `d44c592133e3f4a107ac14f2cf04bb20ffd3c335b7bf414099663007229bb239`
    - `data/raw/forecast/2026-10_areas.csv.gz`: `b27e3ac868c256b8ca1798a62b8929cddd45ad40c0b945bf466e6e16a870b311`
    - `data/raw/forecast/2026-10_forecast.csv.gz`: `58fe5ac140d9903bd31e10d4c3b8762e8e2cc8beb084765ea0c84eb4d83ccdd4`
    - `data/raw/logs/2026-10.json`: `cd07fc3e1247aebb67752ff4b8964e710afc980d90235684a98639a8914bffd9`
    - `data/raw/rain/2026-10_completeness.csv.gz`: `141ed1f5ec0c3e6104839fb530aaf1fe3144ca6cb17a8f6d1e1c095db9361c0a`
    - `data/raw/rain/2026-10_readings.csv.gz`: `3942a39dd1084c2aa1c87e37803bbddb101d8441cb2d9bfa80c26528814e80aa`
    - `data/raw/rain/2026-10_stations.csv.gz`: `f6f2c42937e9fc12bf1705063dc5cab7aa2c4b1fdee5f5ef85a7459a9f66a835`
    - `data/raw/taxi/2026-10_cells500.npz`: `559463ef2addff4a696a5f4100b0d691093dd2f82f41248e5c90ca22539ce237`
    - `data/raw/taxi/2026-10_snapshots.csv.gz`: `0a823604dcc579e22414b43cc7c0e22a48670ecf555a1b8e0c51b1bcfae752e7`
