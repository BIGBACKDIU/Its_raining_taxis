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
