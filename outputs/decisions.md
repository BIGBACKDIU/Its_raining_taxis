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
