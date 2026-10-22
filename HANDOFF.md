# HANDOFF: It's raining taxis

Read this whole file before doing anything. It is the single source of truth for the project's plan,
decisions and next steps. The human owner is Matthew (Heng Fu Rui Matthew), who owns "Data Analysis &
Visualisations" in a 6-person NUS DAO2702 group project. Teammates: Brigette (business problem),
Ben, En, Manda (analysis summary), Nat (recommendation).

Full plan document (for humans, version 3): https://claude.ai/artifact/FDvZw8SNQkwiBnCwHRSjDg
(two tabs: "Rain & Taxis: Project Plan" and "Analysis build plan"). Everything you need is repeated below.

---

## 1. The project in one paragraph

Client: ComfortDelGro (CDG). Research question: **How does rainfall affect the spatial and temporal
availability of taxis in Singapore, and can weather-informed forecasting identify areas at risk of
unusually low availability early enough to support proactive driver repositioning?**
The centrepiece result is **how much weather data improves early warning of unusually low taxi
availability, beyond simply watching current taxi numbers**. Around it: where and when taxis become
unusually scarce in rain, a conditional driver-repositioning policy, and a scenario-based simulation.
The team wants the project to be ambitious ("overkill"), but every claim must be defensible.

## 2. Non-negotiable rules (from two rounds of methodological review)

1. **Vacant taxis are supply, not demand.** Never describe results as unmet demand, lost riders,
   waiting times or revenue unless they come from a clearly labelled simulation scenario or LTA trip data.
2. **Associations, not causes.** The feed cannot tell whether taxis vanish because of more bookings,
   drivers stopping, relocation or congestion. Write "associated with rainfall".
3. **Rain must come before the taxi count it explains.** A snapshot at time t gets the rain from
   (t - 30 min, t]. Earlier windows are lags. Never use rain after t to explain availability at t.
4. **Forecasts as issued.** At time t use only the latest NEA 2-hour forecast issued before t, and only
   taxi and rain data available by t. No look-ahead anywhere in the forecasting.
5. **The test year is touched once.** Fit Apr 2022 - Mar 2025, calibrate/tune Apr - Sep 2025,
   test Oct 2025 - Sep 2026. Log the date you first score on the test year.
6. **Low availability is relative to each cell's own normal level** (see section 5), not a fixed count
   and not a raw percentile (percentiles are often zero in sparse cells).
7. Results apply to **the whole taxi market**. The feed has no company field; CDG is the client.
8. Report what failed or was weak (e.g. if weather adds little over persistence) - that is still a result.

## 3. Data (status and layout)

### 3a. Bulk download (running on GitHub Actions)

Workflow: `.github/workflows/download.yml`, months listed newest first in `pipeline/months.json`
(60 months, Oct 2021 - Sep 2026). Each month is its own job (max 10 in parallel) and commits its files
to `data/raw/` on `main` when done. Re-running skips months already present, so it resumes.

Check progress: `git pull` and `ls data/raw/logs/` (one JSON per finished month), or
`gh run list --workflow download-data` / `gh run view <id> --log-failed`.
If months fail: each job's console output is committed as `data/raw/logs/YYYY-MM.fetchlog.txt`
(even on failure). Read it, fix, then re-run (push a trivial change to `pipeline/months.json`
or `gh workflow run download-data`). A month is complete when `data/raw/logs/YYYY-MM.json` exists.
Status on 22 Oct 2026: first run started 16:36 SGT; ~3-4 min per month, no rate limiting, all 2,688
snapshots present in the first finished month. Four months (2026-05, -06, -07, -09) failed in the first
run for an unknown reason; the parsing was hardened and a second run (queued after the first) retries
any month without a `.json` log. **First task: confirm all 60 months are present.**

Per month (`YYYY-MM`), all readable with numpy/pandas only:

| File | Contents |
| --- | --- |
| `data/raw/taxi/YYYY-MM_cells500.npz` | arrays `snap` (int32), `cell` (int32), `n` (int16): vacant taxis per 500 m cell per snapshot (zero cells omitted) |
| `data/raw/taxi/YYYY-MM_snapshots.csv.gz` | `snap, req_ts, act_ts, taxi_count, n_points, status` (times naive Singapore time) |
| `data/raw/rain/YYYY-MM_readings.csv.gz` | `ts, station_id, mm`: **non-zero** 5-minute totals only; `ts` = end of the 5-minute interval |
| `data/raw/rain/YYYY-MM_completeness.csv.gz` | `date, station_id, n_readings, mm_total`: use to tell "no rain" from "gauge missing" |
| `data/raw/rain/YYYY-MM_stations.csv.gz` | `date, station_id, name, lat, lon` (the gauge network changes: ~68 in 2021, ~90 in 2026) |
| `data/raw/forecast/YYYY-MM_forecast.csv.gz` | `issued, item_ts, valid_start, valid_end, area, forecast` (47 areas) |
| `data/raw/forecast/YYYY-MM_areas.csv.gz` | `area, lat, lon` |
| `data/raw/logs/YYYY-MM.json` | call counts, failures, timings, median offset between requested and returned snapshot time |

Snapshots are every **15 min from Oct 2024**, every **30 min before**. Snapshot `req_ts` is the requested
time; `act_ts` is what the API returned (typically 1 s earlier). Drop snapshots more than 10 min off.

Grid: `pipeline/grid.py`. Local metric projection (equirectangular around Singapore, <0.1% distortion),
cell id = `cx * 1000 + cy`. **1 km cells nest exactly**: `grid.coarsen(cell500)`. 1 km is the main unit,
500 m is a robustness check.

### 3b. Static data already in the repo

- `data/static/sg_map.json`: coastline (`land`) and 55 URA 2014 planning areas (lon/lat rings).
- `data/static/sg_mrt.json`: 184 stations (`[name, code, network, lat, lon]`), 609 exits, line geometries.

### 3c. Still to fetch (small; do these locally)

- LTA Taxi Stop / taxi stands: data.gov.sg dataset `d_fa1896e73ded89dd513788d501d45033` (GeoJSON).
- Passenger pick-up bays and road sections (LTA DataMall static, optional).
- LTA monthly taxi population by company, latest available (for CDG's fleet share).
- Raw taxi GPS positions for ~30 selected storm days (training + test) for the simulation's start states:
  `pipeline.sources.taxi_snapshot` already returns lon/lat; save to `data/raw/storm_positions/`.
- Public and school holidays 2021-2026 (hand-made CSV in `data/static/`).
- DataMall API key is NOT available. Skip MRT passenger volumes and live feeds unless one turns up.
  Use MRT station/exit density and land use as station-activity proxies instead.
- LTA on-request trip data has been requested; it may never arrive. Plan without it.

## 4. Environment

Work in Python scripts under `analysis/` (one per step, runnable top to bottom) plus a final
`report_figures.ipynb` if useful. Create `requirements-analysis.txt` with roughly:
pandas, numpy, scipy, pyarrow, statsmodels, pyfixest, scikit-learn, lightgbm, shap, matplotlib,
pulp, optuna. Use a virtualenv. Save intermediate tables as Parquet under `data/interim/`
(large interim files may stay out of git; add them to `.gitignore` if over ~50 MB) and outputs under
`outputs/figures/` and `outputs/tables/`. Fixed seed `SEED = 2702`. Commit code and outputs regularly.

## 5. Key definitions

- **Unit:** 1 km cell x snapshot. 30-minute snapshots for 5-year analyses (thin the 15-minute years to
  :00 and :30); 15-minute snapshots only for analyses restricted to Oct 2024 - Sep 2026.
- **Cell eligibility (fixed before results):** mean vacant count over training snapshots >= 0.5.
  Report the excluded count; show excluded cells as "not analysed" (grey) on every map.
- **Prior rain:** mm/h in (t - 30, t] at the nearest working gauge (3-gauge mean as a check).
  Bands: dry = 0, light (0, 2.5], moderate (2.5, 10], heavy > 10 mm/h. Lags: (t-60, t-30], (t-90, t-60].
  A gauge-day with < 80% of readings is missing, not dry.
- **Expected baseline:** predicted vacant taxis from a Poisson model `vacant ~ 1 | cell + how^month`
  fitted on training data only (how = half-hour of week).
- **Availability deficit:** D = (baseline - vacant) / max(1, baseline).
- **Low availability:** D >= 0.5 (0.4 and 0.6 as checks), only where baseline >= 4.
  **Zero taxis:** vacant == 0, only where baseline >= 4. Always report absolute counts next to deficits.
- **Rain onset (event study):** first 30-min window >= 1 mm/h after 2 hours with no rain in that cell;
  onsets within 3 hours of the previous onset are merged; window -60 to +180 min; reference -30 min;
  thresholds 0.5 and 2 mm/h as checks.

## 6. Analysis steps (in order)

0. **Audit** (`analysis/00_audit.py`): per month, share of expected snapshots present, offsets,
   robust z-score of citywide jumps (inspect z > 6), gauge completeness, stuck gauges (0 for 7+ days
   while neighbours record rain). Decide usable periods before looking at rain results. Output an
   appendix table. Flag COVID months Oct 2021 - Mar 2022.
1. **Build the panel** (`01_panel.py`): 500 m counts -> 1 km, fill zeros for eligible cells, rain to
   snapshots (rule 3), forecasts as issued (rule 4), time features (how, month, year-month, holidays,
   day type), cell traits (distance to nearest MRT exit, taxi stands within 300 m, city-centre flag,
   planning area), baseline, deficit, low, zero, severity, lags. Save per year as Parquet.
   Check: rows = cells x snapshots, no duplicate keys, 5 rows hand-checked against raw files.
2. **Describe** (`02_describe.py`): hour-of-week profiles dry vs rain bands with 95% bands; cell maps
   dry vs heavy and % change; one storm animation; yearly trend vs fleet size; rain-band frequency.
   Poster-style blue palette, units and sources on every chart.
3. **Rain associations** (`03_effects.py`, pyfixest): main
   `fepois('vacant ~ i(rain_band, ref="dry") + mmh_lag1 + mmh_lag2 | cell + how^month + ym', vcov={'CRV1':'day'})`
   reported as 100*(exp(b)-1)%; share version with slot fixed effects (+ log(citywide) offset check);
   interactions (heavy x rush, x city centre, x weekend, x year); event study; forecast value (forecast
   rain before any rain falls); robustness (negative binomial on an aggregated table, 3-gauge rain,
   500 m grid, with COVID, by year, 15-min panel).
4. **Inference** (`04_inference.py`): clustered errors are primary. Day-block bootstrap with a fast
   ratio statistic T = log(sum vacant / sum fit0) over heavy-rain slots (fit0 = no-rain model);
   multi-day storm blocks as a check. Permutation test as supporting evidence only: swap whole days'
   rain patterns within month x day type (weekday/weekend/holiday). Cell hotspots with
   Benjamini-Hochberg FDR at 10%.
5. **Risk** (`05_risk.py`): logistic models for low and zero (odds ratios, day-clustered); vulnerability
   map; severity multinomial (appendix); optional k-means rain-response types with a bootstrap
   stability check (adjusted Rand index).
6. **Forecasting - the centrepiece** (`06_forecast.py`): horizons 30 and 60 min. Models: persistence,
   seasonal baseline, regression (Poisson / logistic), LightGBM (poisson objective / binary), each
   **with and without weather** (prior rain, lags, wet duration, issued forecast). Tune with
   time-ordered expanding folds inside the fit period. Measures: MAE; PR-AUC, ROC-AUC, calibration;
   precision and recall at a fixed alert workload; precision in the top-20 risk cells; **warning lead
   time** (minutes from first alert to the start of a low-availability run). Report overall and rainy
   slots. SHAP for LightGBM. Split-conformal count ranges calibrated on Apr-Sep 2025; report achieved
   coverage on the test year (no "guarantee" wording).
7. **Repositioning policy** (`07_policy.py`, PuLP): maximise sum_j w_j sum_k r_jk y_jk - lambda sum t_ij x_ij,
   where r_jk = S_j(k-1) - S_j(k) and S_j(m) = E[max(0, base_j - (Y_j + m))] / max(1, base_j),
   Y_j ~ Poisson(mu_j) from the step-6 count forecast. Movable supply = floor(CDG share x max(0,
   vacant_i - base_i)). Destinations need base >= 4 and a staging point. x_ij = 0 if travel time >
   lead time. Travel time = 1.3 x straight-line distance / speed under dry or rain congestion
   scenarios (modelled, not historical). Weights w_j are explicit demand-priority scenarios (equal,
   station activity, land use). Outputs: ranked staging plans per scenario, a targeting check on the
   test year (how often targeted cells really had low availability), sensitivity (N = 50/200/500,
   lambda, lead 30/60, rain band, congestion, weights).
8. **Simulation** (`08_simulation.py` + `sim/index.html`): agent-based, 1-minute steps, numpy.
   It is a **scenario-based operational model**, never "validation". Scenario grid: mechanism in rain
   (demand surge / supply drop / mix), demand level (0.8x, 1x, 1.2x), destinations (MRT-pattern vs
   distance-decay from land use), travel times (dry / rain congestion), dispatch (nearest within 3 km /
   widening radius), policy (as usual / step-7 repositioning). Tune each scenario with optuna to
   resemble observed vacant counts on ~20 training storms; plausibility check on ~10 held-out storms
   with a pass rule fixed in advance. 50 seeds per cell of the grid; report ranges labelled
   "simulated, conditional on scenario X" and a sensitivity table. Then a self-contained HTML page
   (canvas, own map files, seeded RNG, JS port of the same rules) with storm picker, rain slider,
   scenario picker, policy toggle, side-by-side view, click-to-request, risk layer and move arrows.
   Check: page averages within 5% of the Python engine over 50 seeds.
9. **If LTA trip data arrives:** served-demand count models, pickups per vacant taxi, fare per km by
   rain x channel, empty distance and idle time per vehicle, taxi vs private-hire share; recalibrate the
   simulation. Pickups are served demand, not unmet requests.

## 7. Deliverables for the team

- `outputs/figures/`: ~10-12 report-ready charts (PNG + SVG), consistent style.
- `outputs/tables/`: every number used in the report traces to a file here.
- `outputs/summary.md`: plain-English results for Ben, En and Manda (what was found, how sure, caveats).
- `outputs/recommendation_inputs.md`: staging plan and simulation ranges for Nat.
- `sim/index.html`: the interactive simulation.
- Final checks: rerun everything from raw, seeds fixed, `pip freeze > outputs/requirements-lock.txt`,
  wording check against section 2.
