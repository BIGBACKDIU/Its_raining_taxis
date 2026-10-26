# Phase 2 progress log

Plain-English summary after each phase-2 step (steps 10-20). Numbers trace to `outputs/tables/`; specifications
were pre-registered in `outputs/decisions.md` (items 97 onwards) before each step was run.

## Data (23 Oct 2026)

- Fetched URA MP2019 subzones (332) and land use (113,213 polygons), Census 2020 residents by subzone and age
  (SingStat's 2025 subzone tables were not downloadable: 404), HDB property information and resale prices,
  private transactions 2020-2025 from the earlier repo (SHA-256 checked; 2,298 projects with coordinates),
  data.gov.sg hotels / tourist attractions / hawker centres / LTA bus stops, NEA 24-hour forecasts (14,458 issues,
  Oct 2021 - Sep 2026).
- The public OpenStreetMap Overpass servers timed out or refused requests, so destinations (16,093 named features,
  incl. 522 OSM taxi points) and the drivable road network (332k nodes) come from the Geofabrik extract, parsed
  locally. LTA pick-up bays need a DataMall key we do not have; OSM taxi points are a partial proxy.

## Step 10 - Names and supply geography (decisions 98-101)

- Every 1 km cell (778 land cells plus 55 off-land cells seen in the feed) now carries its URA planning area and
  subzone, its two nearest MRT stations with distances, and up to three landmarks within 700 m (attractions,
  malls, hospitals, universities, hotels, hawker centres, schools; 83% of the 374 analysed cells have one).
  HDB blocks were located by matching block numbers to HDB building footprints within each HDB town (decision
  118; 96.9% of 1.18 million dwelling units located) because OneMap throttled geocoding.
- Heavy rain vs the no-rain model, all 374 analysed cells: median cell -14.9% vacant taxis (293 cells with a
  CI below zero); median change in the cell's share of citywide vacant taxis -3.0% (118 cells lose share
  clearly, 40 gain share clearly).
- Most taxis lost per heavy-rain half-hour: Changi Airport T3/T2 (7.1 taxis, -8.5%, CI -15.6 to -0.6), Changi
  T1/Jewel (6.9, -15.9%), Raffles Place / Lau Pa Sat (4.9, -30.8%), Bayfront / Marina Bay Sands (4.8, -36.4%),
  Dhoby Ghaut / Fort Canning (3.7, -34.9%), then Lavender, Victoria (Bugis), Nicoll (Kampong Glam), City Hall
  and Chinatown. Largest share losses: Plab (Paya Lebar Air Base edge) -47.9%, Marina South -34.0%, Seletar
  Aerospace Park -30.9%, Lower Seletar -29.2%, Swiss Club -28.6%, Sembawang North -28.4%.
- Areas that gain share in heavy rain: Xilin (Tampines, Changi City Point side) +50%, Senoko West +37%, Tuas
  View +34%, Changi Airport T2 +31%, Yio Chu Kang East (Nanyang Polytechnic) +24%.
- 121 type-0 (rain-sensitive) cells, most in Yishun, Bukit Timah, Downtown Core and Queenstown (6-7 each).
- Taxi deserts (>= 5,000 residents or >= 2,000 HDB units, fewest dry-weather vacant taxis per resident): Upper
  Thomson, Waterway East (Punggol), Pasir Ris Park, Sembawang Straits, Punggol Town Centre (23,600 residents,
  0.67 vacant taxis per 10,000 residents), Punggol Canal, Simpang South, Brickland and Gombak.
- Charts: `names_rain_hit_map`, `dry_supply_by_band` (07-10, 10-17, 17-20, 20-24, 00-07), `taxi_deserts_map`;
  map labels are numbered with a key so names never overlap. Tables: `names_cells.csv`, `cell_rain_effects.csv`,
  `rain_hit_top30_absolute.csv`, `rain_hit_top30_share.csv`, `rain_sensitive_type0.csv`, `rain_gainers.csv`,
  `dry_supply_by_band.csv`, `taxi_deserts.csv`.
- Problems fixed: garbled attraction names (encoding), long hawker-centre names, OSM "Block E"-type names
  dropped from landmarks. One oddity kept: a desert cell is named "Central Water Catchment" because its centre
  falls in that subzone although its residents live at its Upper Thomson edge.

## Step 11 - Road network and minutes to the nearest vacant taxi (decisions 102-104)

- OpenStreetMap drivable network from the Geofabrik extract (largest strongly connected part: 262,387 nodes),
  speeds by road class and speed limit; rain congestion = travel times x 1.25. Checks: Raffles Place to Changi
  19.2 min, Orchard to Woodlands 21.2 min, Jurong East to Tampines 27.2 min. Drive-time matrices between all
  3,132 500 m land cells (dry and rain) are kept outside git.
- Rider-centric availability for every 30-minute snapshot Apr 2022 - Mar 2025 (19.2 million cell-snapshots):
  median 1.6 drive minutes from an eligible cell centre to the nearest vacant taxi in dry weather.
- Heavy rain goes with a 2.5% longer drive (CI 1.9 to 3.0%; light 2.0%, moderate 2.2%). With the citywide
  vacant count added as a regressor the effect is about zero (heavy +0.05%, CI -0.26 to +0.37%): the longer drive in rain goes with
  the citywide drop in vacant taxis, not with a separate local gap.
- Most extra minutes in heavy rain (named): Changi Airport (+0.8 min, +22.6%), Plab / Paya Lebar (+12.5%),
  Swiss Club / Chatsworth International School (+16.1%), Changi Point / Changi Village (+14.3%), Sentosa
  (Quayside Isle, +8.5%; S.E.A. Aquarium, +6.3%), Seletar Aerospace Park (+13.4%).
- Chart: `minutes_to_taxi_maps`. Tables: `minutes_effects.csv`, `minutes_cells_named.csv`.

## Step 12 - Why some areas lose more (decisions 105-108)

- 35 characteristics per cell (MRT, bus stops, HDB units and resale psf, private housing, residents and share
  65+, URA land-use shares, destinations, taxi stands and OSM taxi points, road access, distances to Raffles
  Place and Changi Airport); one dropped for collinearity (MRT interchange within 800 m).
- Design (i), cell-level heavy-rain effects on standardised characteristics (inverse-variance weights, 374
  cells): R2 0.25 (abs) / 0.27 (share). Residuals were spatially clustered (Moran's I 0.074, p = 0.003), so a
  spatial error model was fitted (lambda 0.47; residual Moran's I then -0.004, p = 0.49). Robust to both:
  - Cells in the URA Central Area lose 9.2% more vacant taxis in heavy rain than otherwise similar cells (CI
    0.4 to 17.2% more; share 9.5%, CI 1.0 to 17.3%).
  - Each SD more business/industrial land goes with a 3.5% smaller loss (CI 1.5 to 5.5); each SD more HDB
    dwelling units with a 4.0% smaller loss (spatial model, CI 0.9 to 7.1); each SD more taxi stops/stands
    within 300 m with a 2.5% smaller loss (CI 0.2 to 4.9).
  - Each SD further from Changi Airport goes with a 2.6% larger loss of share (CI 0.9 to 4.3).
  - HDB resale price, share 65+, hospitals and offices were significant in plain weighted regression but not
    once spatial clustering was modelled.
- Random forest + SHAP with 5 km spatial-block cross-validation predicts the cell effects only weakly out of
  area (R2 0.12 abs, 0.15 share). Most important: distance to the airport, HDB units, distance to Raffles Place,
  residential and park land. Rain-response type 0 vs 1 is predictable from characteristics with spatial-CV AUC
  0.69 (logistic) / 0.70 (random forest): characteristics explain some, not most, of where rain bites.
- Design (ii), interactions inside the Poisson FE panel (day-clustered CIs): heavy rain goes with -24.3% vacant
  taxis in the Central Area (CI -27.4 to -21.1) vs -11.9% elsewhere (CI -13.4 to -10.4); in share terms -18.7%
  vs -4.9%. Cells within 300 m of an MRT exit: -12.9% (CI -14.7 to -11.0) vs -11.9% for cells 1 km or more
  away - no clear difference (interaction -1.1%, CI -2.9 to +0.6). A taxi stand within 300 m (-11.5%), a mall
  (-12.1%), HDB density and distance to the city show no clear difference either.
- Chart: `factors_shap`. Tables: `cell_characteristics.csv`, `factors_cell_wls.csv`, `factors_cell_rf_shap.csv`,
  `factors_cell_summary.csv`, `factors_vif_dropped.csv`, `factors_panel_interactions.csv`.

## Step 13 - New MRT stations as a natural experiment (decisions 109-111)

- Cohorts: TEL stage 3 (13 Nov 2022), TEL stage 4 (23 Jun 2024), Punggol Coast (10 Dec 2024) and Hume
  (28 Feb 2025). 22 eligible 1 km cells lie within 800 m of a new station (TEL3 10, TEL4 10, Punggol Coast 1,
  Hume 1); each is matched to 3 comparison cells more than 2 km from any new station (55 distinct comparison
  cells) on distance to the city centre, central-area status and distance to the nearest existing MRT.
- Dry-weather supply: difference-in-differences +2.3% (95% CI -6.6% to +12.0%, clustered by cell); no clear
  change. The pre-opening event-study coefficients are jointly different from zero (Wald p = 0.001), so the
  parallel-trends assumption is doubtful and even this null should be read with caution.
- Heavy-rain effect: the change in the heavy-rain effect near new stations after opening is -0.8% (95% CI
  -10.1% to +9.4%, clustered by day); the heavy-rain effect itself in this sample is -14.3%.
- What it can show: no detectable shift in vacant-taxi supply near new stations within 12 months of opening.
  What it cannot show: a causal effect of stations (pre-trends fail, only 22 treated cells, the two later cohorts
  have single cells and their post-opening months fall in the test year, which was logged in
  `test_scoring_log.csv` as an association use; the run was made twice after a code fix, both logged).
- Chart: `mrt_did_event_study` (title now states the pre-trend failure). Tables: `mrt_did_summary.csv`,
  `mrt_did_event_study_supply.csv`, `mrt_did_heavy_rain.csv`, `mrt_did_sample.csv`.

## Step 16 - Dose, duration and after-effects (decision 114)

- The first run's spline was rank-deficient (the centred cubic-regression basis sums to zero), giving NaN and
  huge intervals; one basis column is now dropped and the curve is well identified.
- Intensity: vacant taxis fall steeply with the first millimetre (-9.7% at 1 mm/h, CI -11.5 to -7.9), then the
  curve flattens: -12.2% at 10 mm/h, -13.2% at 20-30 mm/h, -12.8% at 60 mm/h. Share of citywide: -2.5% at 1 mm/h,
  -5.5% at 10 mm/h, about -6% to -7% above 15 mm/h. Whether it rains matters more than how hard.
- Duration: within each intensity band, longer wet spells go with bigger drops. Heavy rain: -11.4% in the first
  30 minutes of a spell, -13.2% at 31-60, -14.3% at 61-120 and -18.0% beyond 2 hours (CI -21.2 to -14.6); light
  rain: -6.7% early vs -12.4% beyond 2 hours.
- After rain stops (vs cells dry for at least 6 hours): -5.3% 30-60 minutes after (CI -6.6 to -4.1), -3.1% at
  60-90, about -2% at 90-180 minutes and still -1.4% 3-6 hours later (CI -2.6 to -0.3). In share terms there is
  no hangover: the after-rain shortfall is citywide, not local.
- Recovery after rain onset (first event bin from which every later CI includes 0): rain-sensitive (type 0)
  cells 150 minutes in absolute terms (60 minutes in share), other cells 120 minutes.
- Chart: `dose_intensity_hangover`. Tables: `dose_spline_curve.csv`, `dose_duration_hangover.csv`,
  `dose_recovery_by_type.csv`.

## Step 17 - Redistribution and spillovers (decision 115)

- Island-wide rain (at least half the working gauges wet): 2,394 snapshots on 423 days in the fit period.
  Against the share benchmark, 100 cells clearly lose share, 100 clearly gain and 174 show no clear change.
- Biggest share losers in island-wide rain: Plab (Paya Lebar) -40%, a Changi Airport cell without terminals
  (cargo / airside side) -35%, Central Water Catchment edge (Zoo, Night Safari, River Safari) -33%, Seletar
  Aerospace Park -22%, Bayfront / Marina Bay Sands -22%, Dhoby Ghaut / Fort Canning -20%, Kampong Ubi -19%.
- Biggest gainers: Changi Airport terminal cells (+28% and, at T1/Jewel, +22%), Senoko West +27%, Tuas View
  +25%, Xilin (Tampines) +24%, Tampines West (Temasek Polytechnic) +17%, Katong +17%, Bedok South +15%. During
  island-wide rain, vacant taxis concentrate at the airport terminals and in east and west suburban/industrial
  areas, and thin out in the CBD and isolated non-residential places.
- [First-run wording, superseded by the review fixes below: absolute counts show almost every cell loses taxis in
  island-wide rain, and the characteristic regression was regenerated (decision 144).]
- Characteristics of gainers (weighted regression on the step-12 set): more HDB units (+2.7% share per SD), a
  new MRT station within 800 m (+4.9%), further from Raffles Place (+1.7%); losers have more commercial land
  (-1.0%), more expressway and through-roads (betweenness -1.1%) and are further from the airport (-1.3%).
- Spillovers (own rain and neighbours' rain together): with rain recorded 2-5 km away, a cell has -6.7% vacant
  taxis (heavier rain, CI -7.9 to -5.4) and with heavier rain within 2 km -2.3%, on top of its own heavy rain
  (-5.6%, CI -6.9 to -4.2; the own-cell effect shrinks from -12.9% once neighbours' rain is included). In share
  terms: own heavy -2.8%, within 2 km -1.9%, 2-5 km -2.2%. Much of what looks like a local rain effect is the
  regional storm: taxis thin out across the whole wet area, not just under the cloud.
- Tables: `spillover_islandwide_share.csv`, `spillover_islandwide_characteristics.csv`, `spillover_model.csv`.

## Step 18 - Rain measurement error (decision 116)

- 64% of cell-days are more than 1 km from the nearest working rain gauge.
- Heavy-rain effect near a gauge (<= 1 km) -12.4% (CI -13.8 to -11.0); far (> 1 km) -13.3% (CI -14.8 to
  -11.8). Interaction: far cells lose 1.0 percentage point more (CI 0.0 to 2.0) - the opposite of the
  attenuation that pure measurement error would cause, so distance to the gauge does not visibly weaken the
  estimates (far cells also differ in other ways, so this is not a clean test).
- Reliability ratio of the cell rain measure (nearest gauge vs the 2nd/3rd nearest): 0.72 (correlation 0.79).
  A corrected effect size derived from this ratio was withdrawn (decision 132). Table: `gauges_measurement_error.csv`.

## Step 19 - Fleet trend (decision 117)

- 55 months (Oct 2021 - Sep 2026) had at least 2,000 heavy-rain cell-snapshots; test-year months were used for
  this association analysis and logged. LTA fleet fell from 15,380 to 11,932 taxis over the period.
- Meta-regression (controls: feed coverage level, season): per 1,000 fewer taxis, the absolute heavy-rain
  effect changes by -1.0 log-points (CI -2.6 to +0.5; not clear) and the share effect by -2.2 log-points (CI -4.1
  to -0.3): as the fleet shrank, heavy rain took a somewhat larger bite out of the local share of vacant taxis.
  Feed coverage level is strongly related to the monthly effect (p < 0.01), so coverage changes are a competing
  explanation; association only. Yearly averages of the monthly effects: abs -12% (2022-2024) vs -17% to -19%
  (2025-2026). Chart: `fleet_trend`. Tables: `fleet_monthly_effects.csv`, `fleet_meta_regression.csv`.

## Step 15 - Planning value of the morning forecast (decision 113)

- 228,144 planning-area x time-band x day rows (Apr 2022 - Sep 2026); 51,156 in the test year. Outcome: number of
  low-availability cell-half-hours later that day (10-17, 17-20, 20-24). NEA 24-hour forecasts issued before
  09:00 were found for 86-99% of days depending on the year.
- Pre-registered rule: material if test-year deviance falls by >= 2% with the forecast and the day-bootstrap CI
  excludes 0. Results (test year, scored once and logged):
  - LightGBM, retrospective label: deviance -6.6% with the forecast (CI 5.7 to 7.5%) - meets the rule; mean
    absolute error 4.45 to 4.37 low half-hours per area-band-day.
  - Poisson GLM, retrospective label: -0.04% (CI -0.2 to +0.2) - not material.
  - Issue-time label: LightGBM +0.6% (CI -1.0 to +2.1), not material; GLM gets worse with the forecast (-5.3%).
- Reading: the morning forecast adds planning value only when it is allowed to interact with area, band and
  recent history (LightGBM), and only for the retrospective label. Support for "plan the day with the morning
  forecast" is therefore real but modest and model-dependent. Table: `morning_forecast_value.csv`.

## Step 14 - Taxi stands and the planning map (decision 112)

- (a) 268 of 374 analysed cells have an LTA taxi stop/stand or an OSM taxi point within 300 m. Controlling for
  MRT distance, Central Area, malls, HDB density and distance to the city, heavy rain goes with -12.3% vacant
  taxis in cells with a stand nearby (CI -14.0 to -10.6) and -11.5% without (CI -13.0 to -9.9); difference -1.0
  percentage point (CI -2.5 to +0.5) - no evidence that a nearby stand protects supply in heavy rain (share:
  -5.5% vs -4.3%, difference CI -2.7 to +0.3). The cell-level spatial model in step 12 found a small opposite
  sign (more stands, slightly smaller loss), so the honest summary is "no clear difference either way".
- (b) 18 candidate locations without a stand or taxi point within 300 m: 12 rain-hit cells among the 100 that
  lose most taxis in heavy rain - Woodlands South (Vista Point, Woodlands Hospital), Changi West (Liv@Changi),
  Lower Seletar (Wisteria Mall), Cheng San (Ang Mo Kio), Bukit Batok South (two cells), Pei Chun (Toa Payoh),
  Plab, Tampines West, Hougang West (Hougang 1), Teck Whye, Bedok North - and 6 taxi deserts: Waterway East
  (Punggol), Central Water Catchment edge (Upper Thomson), Simpang South, Safti (Jurong West), Bayshore (Bedok),
  Khatib. Feasibility notes are qualitative (arterial road, MRT exit, mall, hospital, mainly residential); no
  cost, kerb-space or traffic-safety data were available. Given (a), these are candidates for pick-up
  convenience and dry-weather coverage, not a proven fix for rain losses.
- (c) Predicted heavy-rain effect for all 778 land cells from the step-12 random forest (resident-weighted by
  planning area): largest losses predicted for the CBD and fringe (Downtown Core -22.7%, Rochor -22.8%, Outram
  -22.5%, Newton -22.4%, River Valley -22.3%), smallest among large residential areas in Bishan (-12.3%),
  Queenstown (-12.3%), Ang Mo Kio (-12.6%), Bukit Batok (-13.2%) and Clementi (-13.3%). Predictions for cells
  without reliable taxi data (dots on the map, e.g. Lim Chu Kang, Western Islands, -21%) are extrapolations from a
  weak model (spatial-CV R2 0.12) and lean on distance to the airport; treat them as rough.
- Chart: `stands_predicted_sensitivity`. Tables: `stands_effect.csv`, `stands_candidates.csv`,
  `stands_predicted_sensitivity_cells.csv`, `stands_predicted_by_planning_area.csv`, `stands_predicted_by_subzone.csv`.

## Step 20 - Simulation v2 (decisions 119-122)

- Diagnosis of why all 24 step-8 combinations failed (re-run on the 20 training storms, and on the 10 held-out
  storms for reporting, logged):
  - Level: the simulated citywide path sat on average 19% below the observed one on training storms (13% on
    held-out); the "mix" mechanism drained taxis most (-36%).
  - Timing: correlation over time between simulated and observed paths 0.62 (training) and 0.49 (held-out);
    the simulated minimum was typically 30 minutes off.
  - Spatial pattern: which cells hold taxis was matched moderately (r = 0.56 / 0.64), which cells lose taxis
    in the storm poorly (r = 0.25 / 0.14).
  - Benchmarks (renamed from "noise floor", decision 142): two non-simulation references (the normal time-of-day path, and baseline x the estimated rain
    effects) pass the same +-20% / 70% rule on only 10-11 of 20 training storms and 1-3 of 10 held-out storms.
    Held-out (test-year) storms have deeper drops and twice the snapshot-to-snapshot noise (median jump 9.3% vs
    4.6%). The rule is close to unattainable for these storms with the information we have; it was not changed.
- v2 (OpenStreetMap drive times between cells, drive-time dispatch rings, place-characteristics or observed
  supply patterns, per-cell rain sensitivity from step 12), tuned exactly as before: the cell pattern matches
  much better (cell correlation 0.80-0.86 on training storms vs 0.28-0.79 in v1, 0.86-0.92 held-out), but the
  citywide level drains further (held-out level gap -12% to -53%); the tuned demand scale and initial occupied
  share sit at the lower edges of the pre-registered ranges, i.e. longer road trips tie up more taxis than the
  fixed ranges let the model offset. Plausibility: no combination passes (best 1/10 storms; signs at the peak
  match in 8-9 of 10).
- So the page is presented as an illustration only, with the reason on the page. Python/JavaScript parity:
  within 5% on 3 scenario-storm pairs.
- Dispatcher panel added to `sim/v2/index.html`: at every 30-minute step of a replayed storm it lists the top
  staging moves (from subzone/planning area -> named place, taxis, drive minutes, reason: rain approaching /
  rain-sensitive area / forecast risk), labelled "demonstration on historical replays, not a live system".
- Charts: `sim2_diagnosis`, `sim2_heldout_storms`. Tables: `sim2_diagnosis_by_storm.csv`,
  `sim2_diagnosis_summary.csv`, `sim2_noise_floor.csv`, `sim2_cell_inputs.csv`, `sim2_tuning.csv`,
  `sim2_plausibility.csv`, `sim2_plausibility_by_storm.csv`, `sim2_parity_check.csv`.

# Fixes after the second independent review (commit 37081c1)

## Group A - data fixes (decisions 123-126)

- A1, MRT lines and exits: station codes such as "NS24-NE6-CC1" are now split into every line prefix (27
  interchange stations; before, none was detected and the interchange flag was a constant that the VIF step
  dropped). Interchange within 800 m now stays in the model (no characteristic exceeds VIF 10). "Exit"
  variables use the 545 MRT exits in `sg_mrt.json`: distance to the nearest MRT exit replaces station distance
  in step 12 (cell regressions and panel bands) and step 14.
- A2, HDB blocks: matched only inside the block's HDB town and only when the footprint carries the street's
  consensus street code and an unclaimed postal code. 12,929 of 13,392 blocks located (coverage, not verified
  accuracy): 1,139,610 of 1,179,156 dwelling units (96.6%; was 96.9% with the looser rule); 463 blocks rejected
  (380 streets without a clear street code, 79 without a footprint of that number in the town, 4 on 2 postal
  codes claimed by different streets; the old match had 54 such postal codes).
- Rerun: step 10, step 12 (characteristics, cell-level, panel, charts), step 11 names, step 14 (with the B1
  transform fix below). Changes in step 12:
  - Panel (unchanged conclusion): heavy rain -24.5% in the Central Area (CI -27.6 to -21.3) vs -12.0% for cells
    1 km or more from an MRT exit; within 300 m of an MRT exit -12.5% (interaction -0.5%, CI -2.2 to +1.2);
    taxi stand within 300 m -11.7%; mall -12.3%.
  - Cell level, plain WLS and spatial-error model: Central Area -10.4% (WLS CI -17.6 to -2.5) / -10.2% (spatial,
    CI -18.2 to -1.5); business/industrial land +3.5% smaller loss per SD in both; more MRT lines within 800 m
    -2.7% per SD (spatial, CI -4.9 to -0.5; new after the parsing fix); taxi stands +2.8% per SD and HDB units
    +3.5% per SD only in the spatial model; interchange and a new station nearby only in plain WLS.
  - Random forest: spatial-CV R2 0.12 (abs) / 0.15 (share); type-0 AUC 0.71 (logistic) / 0.70 (forest).

## Group B - model fixes (decisions 125, 129-132)

- B1, planning map: the random forest's imputation and standardisation are fitted on the 374 training cells and
  stored with the model; step 14 and the simulation-v2 inputs reuse them unchanged. Before, every land cell was
  re-standardised on the 778-cell set, which shifted predictions. Resident-weighted predicted heavy-rain effect
  by planning area now: Museum -27.6%, Downtown Core -25.2%, Outram -23.8% (CBD and fringe largest); among large
  residential areas Woodlands -16.8%, Sembawang -16.7%, Choa Chu Kang -16.1% at the high end and Bishan -9.4%,
  Ang Mo Kio -9.6%, Bukit Merah -10.3%, Queenstown -10.5% at the low end (Bukit Merah was -16.1% before the fix).
  Figure 24 and `stands_predicted_by_*.csv` regenerated. The model stays weak out of area (R2 0.12).
- B2, morning forecast timing: history now uses the issue-time label only, exposure is scheduled (cells x
  half-hours), GLM imputation uses training rows only, and one forecast issue (the latest before 09:00) is used
  per day. Test year re-scored once (logged). Deviance change with the forecast:
  - LightGBM, retrospective label: -10.1% (CI 9.4 to 10.8) - meets the rule.
  - LightGBM, issue-time label: -6.3% (CI 4.9 to 7.5) - meets the rule (it did not before).
  - GLM, retrospective: +0.2% better (CI -0.1 to +0.5) - not material; GLM, issue-time: 4.5% worse with the
    forecast (CI -5.4 to -3.8).
  The flexible model gains under both labels once the timing is right; the linear model never does.
- B3, MRT natural experiment: controls now matched on the cohort-specific distance to the nearest station open
  before each opening; the heavy-rain DiD includes treated x post. Pre-trends fail more clearly (Wald p =
  0.00002). Dry-supply DiD +2.2% (CI -6.8 to +12.1), still no clear change. Heavy-rain DiD -4.2% (CI -13.4 to
  +5.9), not clear. The new treated x post term (+5.0%, CI 3.2 to 6.8) says vacant supply near the new stations
  rose relative to controls in the snapshot panel; with failed pre-trends this is not evidence of a station
  effect.
- B4, fleet trend: registered regime coverage level and Newey-West HAC errors (3 lags). Per 1,000 fewer taxis
  the absolute heavy-rain effect changes by -0.9 log-points (CI -2.8 to +1.0) and the share effect by -2.0
  (CI -4.3 to +0.3): neither is clear any more (the share result was CI -4.1 to -0.3 with HC1 errors and the
  daily coverage control). The forward-looking sentence about a shrinking fleet is removed.
- B5, measurement error: the "-17.5% corrected" figure and the claim that the headline is understated are
  withdrawn; gauge agreement (reliability ratio 0.72, correlation 0.79) and the near/far comparison (far cells
  -13.3% vs near -12.4%) are kept as sensitivity diagnostics only.

## Group D - wording and presentation (decisions 126, 133-136)

- D1, named lists: every cell effect now has a day-bootstrap p-value and a Benjamini-Hochberg q-value across
  the 374 tested cells. Presentation lists and map labels show only cells with >= 4 expected vacant taxis in
  heavy rain and q < 0.10 (abs: 145 cells; share: 70); full sorted lists are kept as appendix tables
  (`rain_hit_absolute_all.csv`, `rain_hit_share_all.csv`, `rain_gainers.csv`, `spillover_islandwide_share.csv`,
  `minutes_cells_named.csv` with a `presentable` flag). Every share result now carries the absolute change in
  taxis per heavy-rain half-hour with its CI. Consequences:
  - The extreme share losses at Plab (-48%), Marina South (-34%) and Seletar Aerospace Park (-31%) came from cells
    with fewer than 4 expected taxis and drop out of the presented list; the presented share losers are Bayfront
    (-26.4%; -4.8 taxis per heavy-rain half-hour), North Coast (-25.6%; -2.5), Dhoby Ghaut (-25.5%; -3.8),
    Sembawang East (-25.0%; -1.8) and Raffles Place (-21.1%; -4.9).
  - Of 40 cells that gain share in heavy rain, 14 are listable and only 2 gain taxis in absolute terms (Senoko
    West +1.7 taxis, CI 1.1 to 2.3; Yio Chu Kang East +1.4, CI 0.2 to 2.6). In island-wide rain 329 of 374 cells
    have fewer vacant taxis and 3 have more; every listable share gainer still loses taxis. "Gather" is no
    longer used.
  - Minutes to the nearest taxi: described as associated with the citywide drop (conditional association), not
    explained by it; the listable places with the most extra drive time are Monk's Hill (+18%), Tampines East
    (+15%), Bishan East (+10%) and Sentosa (+5%). Changi Airport's +22.6% and Plab drop out (fewer than 4 expected
    taxis in that cell or q >= 0.10). p-values here come from the bootstrap CI (normal approximation on the log
    scale).
- D2, step 12: WLS, spatial-error and panel results are reported separately in the summary; only the Central
  Area (all designs) and business/industrial land (both cell-level designs) are called robust; HDB density and
  taxi stands are not.
- D3, deserts: recomputed on dry snapshots only (normal-coverage regimes, all hours) for analysed cells, so the
  "dry-weather" wording stays. New ranking: Punggol Town Centre (0.73 vacant taxis per 10,000 residents),
  Punggol Canal, Brickland, Gombak, Anak Bukit, Safti, Chin Bee, Bedok South, Ulu Pandan, Kovan, Woodlands East.
  Upper Thomson, Waterway East and Pasir Ris Park left the list (they had no reliable taxi data). Step 14's
  desert candidates follow.
- D4, recovery: reported as the registered statistical recovery criterion (CIs include zero from 120 / 150
  minutes), not "back to normal".
- D5: decision 126 records that the step 10-11 specifications and first outputs share one commit.

## Group C - simulation conservation (Critical; decisions 127-128)

- Bug: in every dispatch ring each taxi cell could take all requests it reached, so overlapping rings served the
  same requests several times (one storm: 11,469 requests, 21,486 trips), and requests were removed with the
  wrong (outgoing) adjacency. The step-8 engine and both JavaScript ports had the same rule, so all earlier
  step-8 and step-20 simulation numbers are void.
- Fix: integer requests; proportional allocation within each ring through incoming adjacency with matched
  systematic rounding, so taxis dispatched equal requests served and nothing is used twice; per-minute
  assertions (taxis conserved, trips never exceed requests) in both Python engines and a trip check in the
  JavaScript ports; `tests/test_sim_conservation.py` (4 tests, fail on the old rule).
- Retuned all 24 combinations of both versions with the unchanged settings; training fits improved (step 8 best
  loss 0.23, was 0.30; v2 best 0.23, was 0.34 - the v2 "drain" reported before was this bug).
- Unchanged plausibility rule on the 10 held-out storms (logged): **no combination passes in either version.**
  Step 8: best 4 of 10 storms (mix, land-use proxy, dry roads), signs at the peak 7-9 of 10. v2: best 3 of 10,
  signs 7-9 of 10.
- Redone diagnosis (step-8 combinations, fixed engine): level gap now small (-9% training, -3% held-out on
  average; demand +2.5%, supply -11%, mix -18% on training storms); timing still moderate (correlation 0.65
  training, 0.46 held-out); which cells lose taxis still matches poorly (0.27 / 0.18); which cells hold taxis
  matches well in v2 (0.87-0.92). The non-simulation benchmark (a path from the estimated rain
  effects passes 11 of 20 training and 3 of 10 held-out storms.
- Parity (Python vs JavaScript, 50 seeds, 3 scenario-storm pairs per version; tolerance: mean within 5%, peak
  within 5% or 0.01 absolute): all pass; largest gaps 0.3% (mean) and 1.4% (peak).
- Pages rebuilt and republished: `sim/index.html` and `sim/v2/index.html` (dispatcher panel unchanged in
  design, illustration banner with the new diagnosis). The step-8 scenario grid (50 seeds) is re-run.
- Step-8 grid re-run (24 combinations x 3 demand levels x 2 policies x 10 held-out storms x 50 seeds = 72,000
  runs; logged): vacant taxis at the rain peak about 0.7-1.0 of the start in demand or supply scenarios and
  0.5-0.8 when both act; simulated abandonment during rain 0.1-6%; step-7 repositioning changes abandonment
  during rain by -0.4 points on average (0 to -2.6). Before the fix the same summary read 1-10% abandonment and
  -1.3 points (0 to -4.7); those numbers are void. `recommendation_inputs.md` section 4 is updated.

## Follow-ups (decisions 137-138)

- MRT lines: MRT lines only (LRT codes excluded, CG counted as EW; codes without numbers now parsed). 25
  interchange stations; the interchange flag changed for 4 eligible cells (Gombak, Keat Hong, Senja, Choa Chu Kang
  North). Step 12 cell-level designs rerun: the Central Area result is unchanged (-10.6% WLS, -10.7% spatial);
  the interchange flag is now significant in the spatial model too (+5.5%, CI 0.1 to 11.2), alongside more MRT
  lines nearby (-3.4% per SD); both hold in the two cell-level designs with opposite signs and are not tested in
  the panel, so the summary calls only the Central Area robust across all designs. Random forest R2 and AUC
  unchanged (0.12 / 0.15; 0.71 / 0.70). Step-14 map regenerated.
- Morning planning and simulation wording in `summary.md` clarified (second test-year scoring; plain words;
  the statistical path also fails the unchanged rule).
- Simulators: trips now start at the request cells. Training loss moved by more than 1% for 5 of 48 combinations
  (largest 1.44%), so both versions were retuned and re-checked with the unchanged rule (logged): still no
  combination passes (step 8 best 4 of 10 storms, v2 best 3 of 10); diagnosis and parity (within 5% or 0.01;
  largest gap 1.9% at the peak) unchanged in substance. Grid: abandonment during rain 0.1-5%, repositioning
  -0.3 points on average (0 to -2.3).

# Third independent review (commit 078c8bc)

## Group 1 - simulation, final iteration (decisions 139-143)

- Allocation now uses integer edge flows (floored fluid flows on permitted taxi-cell -> request-cell edges, then
  single units along permitted edges in a seeded random order), in Python (`analysis/sim_alloc.py`, shared by both
  engines) and both JavaScript ports. 3,000 random asymmetric rings agree with an exact max-flow; every dispatch
  has a permitted partner; a constructed five-cell world with overlapping rings fails on the 37081c1 engine (745
  requests, 823 trips) and passes now; the old real-data test, which passed on the old engine, is removed. A
  first rerun with this allocator drew a random number for every ring edge and was too slow (stopped at 6 of 48
  grid cells per mechanism; its plausibility, diagnosis and partial grid runs are in the scoring log); the final
  allocator draws only for edges with a fractional flow. 12 tests pass.
- `sim/v2/data.json` rebuilt from the final step-12 bundle (decision 140). Both versions retuned with unchanged
  settings (best training loss 0.232 step 8, 0.231 v2).
- Unchanged plausibility rule (logged): no combination passes. Step 8 best 4 of 10 storms (mix, land-use proxy,
  dry roads, nearest), v2 best 3 of 10 (demand, characteristics pattern, dry roads, nearest); signs at the peak
  7-9 of 10. These are the reported simulation results.
- Diagnosis (step-8 combinations): level gap -9% training / -3% held-out; timing correlation 0.65 / 0.47; which
  cells lose taxis 0.27 / 0.19. The non-simulation benchmark also fails the rule (11 of 20 training, 3 of 10
  held-out storms); it is a benchmark, not a noise floor (decision 142).
- Parity (now logged as test-year storm inputs only, no observed outcomes; six earlier runs added): within 5% or
  0.01; largest gaps 0.3% mean, 1.7% peak. Grid (72,000 runs): abandonment during rain 0.1-5%; repositioning -0.3
  points on average (0 to -2.3). Pages rebuilt.

## Group 2 - analysis (decisions 144-145)

- Step 17: characteristic regression regenerated with the final characteristics. Share gainers in island-wide rain
  go with a new MRT station within 800 m (+4.9% per SD), more business land (+1.4%), share 65+ (+1.1%) and distance
  from Raffles Place (+1.8%); losers with commercial land (-1.0%), expressways (-0.8%), through-road betweenness
  (-1.2%) and distance from the airport (-1.3%). MRT lines nearby is no longer significant.
- Step 15: registered day-bootstrap CIs unchanged ([9.4, 10.8] retrospective, [4.9, 7.5] issue-time, flexible
  model). Sensitivity with 7-day moving blocks: [8.9, 11.4] and [4.4, 8.1]; both still exclude 0 and the
  materiality conclusion does not change. Lag-1 autocorrelation of daily gains 0.37 / 0.24.

## Group 3 - wording (decision 146)

- Measurement-error correction paragraph replaced by one line (withdrawn, decision 132); stands wording in
  `recommendation_inputs.md` (cell-level designs only, not the panel: not robust); recovery wording in
  `summary.md` item 2; the summary now states the corrective refit of the morning models and that no model was
  tuned on test-year outcomes. Wording check and all tests re-run.

# Step 21 - Radar rainfall measurement check (separate analysis; decisions 147-149)

- Registration: specification and code committed and pushed as `ed4e4ba` before any taxi outcome fit; verified
  data audit committed as `0ada6ac`. Decisions 139-146 were already occupied, so the new specification is 147.
  Frozen outputs and headline estimates remain unchanged. No test-year taxi panels are used.
- Data: Zhuang et al. (2026), Zenodo 19642566, CC BY 4.0; the full 10,087,581,305-byte `5min_SG.zip` matches
  MD5 `5d97d0700c23d028fa6e6977485359f7`. All 1,827 archive dates are present. There are no missing selected
  land values or five-minute steps on the 1,007 prepared dates (including the warm-up day). All daily grids
  match: rainfall(time,lat,lon), 288 x 311 x 532, mm per five-minute interval, NaN fill, geographic axes with
  no explicit CRS/datum metadata. Code and metadata record these limitations.
- Timing: UTC+8, interval-end labels. On all five fixed storm days, zero shift gives the largest gauge-pixel
  correlation (0.968-0.996); the +/-5-minute alternatives give 0.817-0.872. All -10/-5/0/+5/+10-minute results
  remain in `radar_clock_check.csv`. Land pixels are aggregated before constructing (t-30,t] and both lags;
  checks across a year boundary match direct sums exactly. Pixel-weighted 500 m reconstruction agrees with
  the 1 km means within 0.0000024 mm per five minutes. All 374 main cells have land support; eight nested
  500 m cells have none and remain missing, including one frozen eligible 500 m cell (60024). All 793
  frozen eligible 500 m cells are included in the prepared files.
- Agreement at gauge pixels (not independent validation of a radar-gauge merged product): five-minute r =
  0.9802, half-hour r = 0.9886; radar/gauge totals 1.0182 at both scales. Half-hour wet/dry agreement is 97.70%
  at zero and 99.17% at 0.1 mm/h. Heavy agreement is 99.9278%, sensitivity 96.30%, precision 95.74%. These
  diagnostics use near-complete, working gauge-days and exclude unknown midnight gauge observations.
- Paired sample: 16,925,334 cell-snapshots, 374 cells, Apr 2022-Dec 2024. This is exactly the original step-3
  valid sample within those dates: radar/common support removes zero further observations. The 80,820 rows
  between main exclusions and the final sample already lack valid gauge measurements/lags.
- Primary (dry = 0) absolute estimates (gauge / radar, percentages with 95% day-clustered CIs): light -7.92 [-9.41,-6.41] /
  -5.19 [-6.22,-4.15]; moderate -10.52 [-11.98,-9.03] / -9.30 [-10.65,-7.94]; heavy -12.12 [-13.58,-10.64] /
  -12.01 [-13.50,-10.50]. Per 10 expected vacant taxis these are -0.79/-0.52, -1.05/-0.93 and -1.21/-1.20.
  Heavy local-share estimates -5.10 [-6.39,-3.79] / -5.86 [-7.16,-4.54]. Central Area heavy counts -23.32
  [-27.04,-19.40] / -23.97 [-27.70,-20.04] (about 2.3/2.4 fewer per 10 expected); outside Central Area
  -11.07/-10.84% (about 1.1 fewer per 10 expected).
- Approaching rain uses the registered >10 mm/h annulus category, own cell dry for 90 minutes and neighbouring
  controls. Gauge -7.47% [-10.94,-3.87], radar -16.88% [-38.85,+12.99]. The radar contrast has only 52
  cell-snapshots across 29 days; gauge has 5,708 across 375 days. The large radar uncertainty is retained.
- Event study: gauge/radar onset associations -5.00%/-3.33%; at +30 minutes -5.32%/-4.74% (about 0.53/0.47
  fewer per 10 at the reference level). Both later CIs include zero at 150 and 180 minutes, a statistical
  detectability statement. There are 148,353/88,634 source-defined onsets on the full grid including warm-up.
  All nine bins and the registered dry-threshold sensitivity are reported in tables.
- Registered dry-threshold check (<=0.1 mm/h): radar absolute light -6.65% [-7.86,-5.42], moderate -9.27%
  [-10.60,-7.92], heavy -12.07% [-13.55,-10.57] (0.66, 0.93, 1.21 fewer per 10 expected); share light -1.84%,
  moderate -4.05%, heavy -5.88%. Central Area -23.91% [-27.65,-19.98] (2.39 fewer per 10 expected).
  Approaching-heavy rain remains imprecise: radar -5.93% [-20.21,+10.91] with 210 cases on 78 days; gauge
  -7.94% [-11.40,-4.34]. Main gauge fits are identical; the gauge approaching term changes slightly because
  the same dry rule also recodes trace values in neighbouring controls. Event estimates remain similar:
  radar -3.60% at onset and -4.70% at +30 minutes; 136,811 full-grid radar onsets, with CIs including zero
  at 150 and 180 minutes.
- Unexpected: radar is not rarely zero on this sample: 87.08% of cell-windows are exactly dry, versus 93.68%
  with gauges; the 0.1 rule raises radar dry share to 91.12%. The wider trace-light category helps explain why
  the primary radar light association is smaller. The post-fit contrast-count diagnostic is labelled in
  decision 149; no model or row filter was changed after inspecting its uncertainty.
- Reading: the matched heavy-rain and Central Area estimates are similar across measurement representations;
  there is no uniform strengthening of effects with radar and no basis for a blanket attenuation correction.
  The radar approaching-heavy contrast does not give a precise confirmation. Agreement at gauge pixels is
  non-independent because gauges are part of the merged product. Frozen full-period gauge estimates remain
  the headline; this is a separately labelled measurement check, not a forecasting or intervention result.
- Final checks: all 20 registered fits use n = 16,925,334; absolute/share fits have 956 day clusters.
  The 108 coefficient rows, 36 event rows and 8 Central Area contrasts have finite CIs; all 20 covariance
  matrices are finite and positive semidefinite. All 15 tests pass (14 existing dependency/test warnings).
  Wording scanner completes with 69 hits; new hits are negated validation claims or code terminology, reviewed
  in context. All 267 frozen table/figure hashes match, and the summary outside the new subsection is identical.

## Step 22: regional storm forecasting (fresh holdout; decision 150)

- Frozen model/code commit: `cc12a0ef9d14f5284b6e302e3fcb94df09e0c2e9`, pushed before any October labels, storm counts or scores.
- Development used only Apr 2022-Mar 2025 and calibration Apr-Sep 2025. Settings and tree counts
  were fixed before refitting Apr 2022-Sep 2026. The old test year entered only that final refit,
  which is separately logged; frozen analyses and their outputs remain unchanged.
- Fresh holdout: 1-24 October 2026, scored once. Storm onsets: **2**; power: **descriptive only: fewer than eight onsets**.
- Onsets require >=25% of the same working gauges to change from dry to >=1 mm/h within 30 min;
  candidates within three hours are merged. Storm issue windows are -60 to +120 minutes.
- Paired 1,000-draw issue-day bootstrap CIs. Six overlapping units; the pooled comparison is primary.
  T1 is log(count / issue-time expected); T2 is a 15% shortfall, with 10%/20% checks reported.
- Fixed alert workloads equal calibration base rates, not October base rates. All model x weather x
  horizon x target x unit x subset combinations are retained; no holdout model selection occurred.
- **Pooled LightGBM storm comparisons** (positive gain favours weather):
  - 30 min T1: 0.18648 without / 0.17973 with weather; gain +3.6178 % lower MAE, CI [+0.4155, +6.5643].
  - 30 min T2_15: 0.72376 without / 0.75710 with weather; gain +0.0333 PR-AUC, CI [-0.0029, +0.0394].
  - 60 min T1: 0.21974 without / 0.21476 with weather; gain +2.2646 % lower MAE, CI [+0.9345, +3.9503].
  - 60 min T2_15: 0.73240 without / 0.75616 with weather; gain +0.0238 PR-AUC, CI [+0.0123, +0.0787].
- Registered materiality threshold: **met numerically; confirmation unavailable (fewer than eight storms)**. Numerical crossings are reported separately from the
  eight-onset power requirement; 10%/20% labels and individual regions are checks, not extra primary tests.
- Absolute supply and expected counts, base rates, alert counts and sample sizes are in s22_support.csv.
  MAE is measured on a log ratio, not taxis. CIs are pointwise and the 24-day period cannot establish
  general performance across seasons or feed regimes. Multiple-day dependence can widen uncertainty.
- Sparse gauge archives omit zeros and observation timestamps: preceding-day health is causal, but
  cannot prove intraday completeness. Unknown midnight intervals remain missing and are imputed from
  fitting data. Seven coastal cell centres use their frozen planning-area region; Central Area keeps
  the URA centre-within definition. Neither eligibility nor membership is selected using holdout outcomes.
- Outputs: s22_audit_*.csv, s22_unit_cells.csv, s22_development.csv, s22_alert_rates.csv,
  s22_model_manifest.csv, s22_storm_onsets.csv, s22_metrics.csv, s22_weather_gains.csv,
  s22_materiality.csv, s22_support.csv; one figure s22_weather_gain.png/.svg.
- These results concern vacant-taxi supply. Frozen gauge associations and earlier forecasting conclusions
  remain as originally reported for their own targets, periods and spatial scales.

- Additional reporting of the fixed scores (no new scoring): storm windows have 84 region forecasts
  on two days, with 31 primary shortfall events at each horizon. Of 1,000 day draws, 107 contain
  neither storm day, leaving 893 defined primary pooled storm comparisons. These CIs are conditional
  on a nonempty resample and cannot support confirmation from two storms. At 60 minutes the fixed
  workload has 23 alerts: 16 are correct without weather and 18 with weather; at 30 minutes both
  have 16/23 correct alerts. All-time pooled primary PR-AUC gains are +0.001458 [-0.000106,+0.003208]
  at 30 minutes and +0.000430 [-0.002387,+0.002757] at 60 minutes; T1 gains are +0.0518% and -0.0961%.
  No method, fitted model, label, sample definition or score changed after opening October.
- Final checks: all 22 tests pass (14 existing warnings); wording check completes with 69 reviewed hits.
  All 287 earlier table/figure hashes and all 72 freeze hashes still match after scoring. The original
  summary is unchanged outside the new subsection. The scoring log has exactly one fresh-holdout entry;
  the saved prediction SHA-256 is repeated in s22_scoring_record.csv. No model or executable source changed.

## Step 22b: confirmatory backward holdout in 2019 (decisions 152-153)

- Model source: cc12a0e. Adapter/input freeze `0ca69d3b6a369a3ec0eb36cab41c99f3bcc0cafa` was pushed before scoring.
- Registration f8dfda4 was pushed before downloading. No refitting, tuning or 2019-based
  imputation, probability calibration, residual CDF, alert workload or seasonal pattern changes.
- 2019 storm onsets: **49**. Power rule >=8: **True**.
- Primary confirmation (60-minute pooled storm T2, 15% shortfall): **False**.
  PR-AUC without/with weather: 0.860094/0.868841;
  gain +0.008747, day-block 95% CI [+0.000807, +0.017070].
- Original step-22 omnibus materiality rule: **False**. All primary-label storm contrasts:
  - 30 min T1: gain +4.089506, CI [+2.443677,+5.924907]; n=1974, defined draws=1000.
  - 30 min T2_15: gain +0.008526, CI [+0.003682,+0.014521]; n=1974, defined draws=1000.
  - 60 min T1: gain +2.820118, CI [+1.420216,+4.445052]; n=1968, defined draws=1000.
  - 60 min T2_15: gain +0.008747, CI [+0.000807,+0.017070]; n=1968, defined draws=1000.
- Audit before scores (full tables s22b_audit_*.csv):
  - requested: 17520
  - expected: 17520
  - usable: 16989
  - invalid_status: 525
  - bad_offsets: 6
  - glitch_flags: 245
  - regimes: 5
  - short_spells: 0
  - unique_gauges: 54
  - min_daily_gauges: 0
  - max_daily_gauges: 54
  - complete_gauge_days: 17034
  - gauge_days: 18055
  - days_without_rain_readings: 11
  - days_without_complete_gauges: 16
  - days_without_forecast_records: 3
  - forecast_issues: 21029
  - forecast_area_records_issued_at_or_after_end: 1269
  - issued_at_or_after_end: 27
  - naive_future_issue_rejections: 16412
  - strict_forecast_slots: 16819
  - unavailable_forecast_slots: 701
- Forecast issue times are never replaced by validity times. Naive validity-only candidates with
  issue>=t are rejected. The latest actually issued forecast must also be valid at t; otherwise
  saved training imputation supplies missing weather. Eleven entirely unobserved rain days supply
  unknown five-minute depths, not dry zeros, before the unchanged frozen rolling windows.
  All raw issue and slot counts and the four
  prespecified sample days are reported. Missing archive forecasts can limit this era comparison.
- Counts and labels use the unchanged seasonal pattern with the trailing seven-day level frozen
  at issue time. The first January observations provide wash-in (minimum 48 past snapshots);
  unavailable issue/target observations and exact lags are not filled using future data.
- Six units overlap (Central Area within Central Region); day resampling keeps them together.
  The 1,000 draws and undefined-draw handling are exactly step 22. CIs are pointwise; multi-day
  dependence and this single historical year limit inference.
- 2019 had a different fleet and market, and different archive coverage. A failed confirmation
  may reflect an era shift; it does not revise frozen 2022-26 associations or earlier forecasts.
  Vacant taxis measure supply only. The optional heavy-rain regression was not undertaken.
- All 896 model/weather/horizon/target/unit/subset rows and 448 paired gains are in s22b_metrics.csv
  and s22b_weather_gains.csv; s22b_support.csv includes observed/expected counts, base rates,
  alert counts and sample days. One figure: s22b_weather_gain.png/.svg.

- Interpretation of the fixed scores: weather provides a small positive pooled gain, including the primary
  CI excluding zero, but its entire primary CI lies below +0.02. Neither the primary confirmation nor
  pooled omnibus materiality rule is met. The 30-minute T1 interval includes a 5% improvement, so the
  failure of its point-estimate rule does not rule out that magnitude. No claim of zero weather value.
- Absolute alert counts at the registered 60-minute storm workload: 473/524 correct without weather,
  482/524 with weather, against 972 shortfall events. All 49 onsets have usable pairs; storm comparisons
  span 44 issue days. T1's max(1,.) floor is used in five/six region targets at 30/60 minutes, retained
  as registered. No regime, glitch or low-count exclusion was added after the audit or scoring.
- Snapshot audit: 525 invalid statuses and six offsets beyond 10 minutes; no positive offsets.
  The 245 step-0 glitch flags are retained by the registered step-22 sample rule. The 11 entirely
  missing rain dates stay unknown, not dry; another five dates have no complete gauges. Intraday
  completeness cannot be reconstructed from sparse positive-only files. Three dates have no forecast
  records. The 16,412 rejected naive candidate uses include ordinary publication delays, not only
  retroactive corrections: 27 distinct issues (1,269 area records) were issued at/after expiry.
  At 14 June 18:00 the selected known issue is 14 June 17:38:52; the 15 June 08:43:53 update is blocked.
- Final checks: 27 tests pass (14 existing warnings); wording scanner completes with 69 reviewed hits.
  All 72 original freeze hashes, 112 backward-holdout input/adapter hashes and 306 earlier table/figure
  hashes still match after scoring. The previous summary is identical outside the new subsection.
  Exactly one log entry says "backward holdout 2019, scored once"; the saved prediction hash matches
  s22b_scoring_record.csv. No forecast model, transform, input definition or executable source changed
  after scoring. No heavy-rain regression was added.

## Step 23 — Why taxis disappear: minute-flow feasibility and matching diagnostics

**Status: registered design cannot produce a matched comparison; no mechanism effect estimated.**
Decision 155 was committed/pushed as `eca91cd` before any minute-position request. Pilot-dependent
settings and code were frozen in `cb7c53e` (decision 156). Gauge-only auditing then exposed an extra
half-hour onset restriction; `a95e19b` corrected it to native five-minute gauges before any main-sample
minute download or taxi-flow comparison (decision 157). Gauge eligibility counts had been seen when
making that disclosed correction. No rain thresholds, regime rules or matching controls were relaxed.
No frozen result, model or test/holdout outcome was used or changed.

### Pilot and matching

The two fixed pilot days, 12 July 2023 and 17 April 2024, each contain 1,081 valid requests from 06:00
through 24:00. Median intervals between distinct timestamps and changed coordinate multisets are
60 seconds on both days; there are 1,078 and 1,080 distinct observations. Median archive offsets are
-19 and -17 seconds, with no future snapshots or offsets beyond ten minutes. One-minute sampling
is retained. Exact coordinate multiplicities are 13,552/1,954,854 points (0.69%) and 7,245/2,274,987
(0.32%); colocated taxis cannot be identified as duplicate vehicles, so multiplicities remain.

Isolated mutual-nearest points within 20 m have displacement medians 0 and 0.105 m, and p95 values
14.389 and 14.539 m. The registered pooled moving-point threshold is 14.4835 m. These are conditional
apparent stationary displacements, including slow movement; without IDs they do not identify true GPS
jitter. Minute raw positions are compressed NPZ locally in gitignored `data/raw_minute/`; hashes and
sizes are in `s23_raw_manifest.csv`. No main matched-day minute sample was pulled.

Synthetic checks use real pilot positions, known independent movements at 0/15/30 km/h, 10%/20%
removals/entrants, and all 0.5/1/2 km-per-minute radii: 108 scenarios, all in
`s23_matching_validation.csv`. At 1 km/min, mean correct-link precision is 77.9%, 23.0% and 9.8%
respectively. True disappearance recall is 10.2%, 6.1% and 4.5%; appearance recall is 10.2%, 1.7%
and 1.0%. The maximum-cardinality rule frequently matches unrelated entrants to departed taxis.
With true speed zero, erroneous moving links alone produce a 37.0 km/h mean inferred moving-link
median speed. Synthetic paths are illustrative validation cases, not a measured error rate on real roads;
they nevertheless show that coordinate assignment does not establish vehicle identity or traffic speed.
Algorithm tests check cardinality, one-to-one use, distance limits, multiplicities, flicker timing and the
zero-pair guard. No greedy identity shortcut, matching-radius selection or tuning followed these results.

### Sample audit and unavailable results

Of 1,096 fit-period dates, 865 pass the frozen coverage/day exclusions and public-holiday/pilot rule.
Only six dates meet the strict gauge-onset rule before those exclusions. Two are eligible:

- **5 December 2023, 17:50:** 19/64 working gauges newly reach >=1 mm/h (29.69%).
- **17 September 2024, 19:20:** 27/62 working gauges (43.55%).

Direct sparse raw-record checks independently confirm the shares and zero positive readings in the
preceding three-hour dry windows. There are 76 eligible dry days, 26 in R09. The only Tuesday dry days
in R09 are 26 March and 23 July 2024, outside the allowed month +/-1 windows for BOTH storms.
Thus neither storm has a qualifying control: **zero matched pairs**, regardless of random seed or cost.
See `s23_sample_audit.csv`, `s23_storm_candidates.csv`, `s23_dry_candidates.csv`, `s23_match_audit.csv`
and `s23_onset_validation.csv`. The empty `s23_sample.csv` retains its column schema.

Consequently R and its CI, 1-R, the vacant-plus-recent-disappearance inventory, speed change,
D/A peak lag, relocation flow, cell CIs/FDR and named rankings are **not estimated**. The planned
1,000 day-pair bootstrap draws cannot be performed. No proxy threshold receives a hires/off-duty
verdict, and there is no claim of zero rain effects. `s23_results.csv` records unavailable estimates for
every radius/dense-zone combination. `s23_flows`, `s23_speed` and `s23_geography` explicitly show
the failed design; the speed figure also displays the synthetic assignment warning. No pickup or
drop-off places are ranked, because there are no tested effects satisfying the presentation filter.

Disappearance can mean hire, a booked vehicle travelling to a pickup, or leaving duty; appearance can
mean drop-off or coming on duty. Anonymous positions add substantial assignment ambiguity. The
registered R thresholds are conditional heuristics, not identified mechanism shares. This design cannot
answer why taxis disappear under its strict sample rule, and frozen supply associations remain unchanged.

Verification: **32 tests pass** (14 existing dependency warnings); wording check has **72 reviewed hits**
(the three new code hits are the synthetic-check function/CLI name). All **326 existing output table and
figure files** retain their pre-step-23 SHA-256 hashes. The test-scoring log has no new row because no
new test-year use occurred. Main sample constraints, expected-count thresholds and frozen results remain intact.

## Storm Builder — presentation-only v3 with real road animation

Registered as decision 159 (`9725a3e`) before implementation; checked choices/results are decision 160.
`sim/v3/index.html` is a **1.64 MB standalone HTML artifact**, with no external script, image, font or
network dependency. It adds four synthetic-storm presets, size/strength/duration/drift controls, weekday/
weekend time profiles, three assumed rain mechanisms, a request multiplier, policy toggle, advanced
settings, timeline, smooth taxi dots, request pulses, count chart and same-seed comparison. The phone
controls become a bottom sheet and comparisons stack at 400 px. The permanent failed-realism banner
stays visible on scroll; every counter is labelled simulated. This is not a new empirical analysis.

Roads use the local step-11 OSM GraphML, filtered to motorway/trunk/primary/secondary/tertiary and
links. Mixed edges containing excluded classes are dropped. Largest strongly connected component:
**14,880 nodes / 21,651 directed edges / 612,734 inlined bytes**, below 3 MB. Geometry is simplified
at 15 m and quantised to integer metres in the existing local projection. Each eligible cell has an ID
mapping to its nearest node (`storm_builder_cell_nodes.csv`); snap distances median 147.75 m, max
764.03 m. Cached directed A* routes occupied trips, pickup approaches and repositioning. There are
**zero path fallbacks** in tested scenarios; the missing-path unit test confirms the counted straight-line
fallback. One-way cruise loops remain local (max 1,120.85 m); 84 cells without a short legal loop wait
for an engine move. These trajectories and identities are illustrations, not recovered vehicles or speeds.

The v2 engine gains optional observational callbacks only. No model RNG calls, integer allocation,
arrival times, parameters or realism rules change. Twelve fixed-seed cases match the original engine
and match hooks off/on exactly at every minute and in final scheduled arrivals. Six existing conservation
tests pass. The three existing 50-seed Python/JS parity cases pass their unchanged rule (max peak gap
0.707%) and are written to `storm_builder_parity.csv`; the frozen parity table stays unchanged.
Their held-out input-only use is logged once; no observed outcomes are scored or used for choices.
The 96 typical calendar profiles reuse saved fit-period step-5 predictions with normal feed scaling;
there is no baseline refit or new test-year choice. `sim/index.html` and `sim/v2/index.html` are unchanged.

Headless Chromium 156 on this Apple M2 Pro records **60 fps with 2,500 moving road dots** and
2.7 ms p95 drawing time; ordinary 16x playback also stays near 60 fps. The 400 px emulation runs near
60 fps on the same machine, without horizontal scroll; this is not a real-phone hardware claim.
Both policy versions have zero per-cell animation/count discrepancies across 241 engine minutes.
Independent hooks-off checks reproduce initial, mid-storm, end, mobile policy and reduced-motion
counters. Default end totals: **1,742 vacant / 8,103 hired trips / 1 offline / 0 waiting / 10 abandoned**, with
8,113 simulated requests. Worker-blocked fallback, a nonzero 30-minute light shower, permanent banner,
stacked split view and no external requests all pass. **No console errors.** Required 1440/400 px
before/mid-storm screenshots include roads; extra phone sheet/split screenshots are also saved.

Full build and browser reports: `storm_builder_build.json`, `storm_builder_browser_check.json`.
Build/check instructions, provenance, OSM/ODbL credit and simplifications: `sim/v3/README.md`.
Frozen v2 data, tuning/plausibility/parity tables and both earlier HTML pages retain their original hashes.
The wording checker now scans the v3 template; new demand/lost-passenger matches describe explicitly
simulated assumptions or state that those quantities are not measured.

Final gates: **35 tests pass** (14 existing dependency warnings). Wording check: **76 reviewed hits**;
the four new v3 hits are scenario controls/identifiers and explicit negations of measured demand or
lost-passenger claims. `storm_builder_hook_check.json` records all 12 exact old/new/on/off cases;
`storm_builder_preservation.json` records the unchanged frozen hashes. No existing result table or
figure is modified. A local preview is available on port 8765; the HTML also works directly from disk.

### Storm Builder visual refinement and scenario explanation (decision 161; presentation only)

The v3 presentation now uses a professional navy palette, muted blue accents, flat taxi markers and
quieter rain/trails. A short **Scenario brief** changes with each prepared storm, explaining its selected
conditions and how the request/off-duty assumptions, wet travel time, request multiplier and
repositioning affect model counts. It also distinguishes cumulative counters from current counts.
The brief describes assumptions rather than claiming empirical mechanisms or an isolated rain effect.
The realism notice remains visible; phone OSM attribution moves above the fixed controls launcher.

The engine and numeric inputs are unchanged. Exact independent counter checks and all 241 per-cell
frames pass; default end totals remain 1,742 vacant / 8,103 hired / 1 offline / 0 waiting / 10 abandoned.
Default/shower/policy brief changes pass browser checks. Desktop and 400 px emulation remain about
60 fps with 2,500 road dots; no console errors, network requests, path fallbacks or horizontal overflow.
The six presentation screenshots are refreshed. Wording check: 76 reviewed hits, all tests: 35 passed
(with the existing dependency warnings). No new held-out data use or analysis results.

## Storm Builder visual polish

- Presentation-only restyle of `sim/v3/index.html` (palette, dot size, rain layer, type sizes, map aspect, chart
  range and labels, phone layout). The browser checker passes with exact counter agreement; screenshots in
  `outputs/figures/storm_builder_*.png` are refreshed. No model or number changed.
- City-builder restyle of the Storm Builder (decision above): full-screen light map with floating panels and a tool
  bar. Presentation only; the browser checker passes with exact counter agreement.

### Deck chart presentation exports (decision 167)

Created all 11 requested PNGs in `outputs/figures/deck/` at exactly twice their specified display sizes.
The charts use the supplied navy/blue/red palette, registered Poppins fonts, direct labels and common
±40% change-map scales. Every text element passes a font-file and glyph check; image dimensions and
all source hashes pass validation. Each image was opened for visual inspection, and label collisions
were corrected. No model is re-estimated, no holdout is re-scored, and frozen tables/figures stay unchanged.

The storm snapshot did not have a result CSV: the export copies its 374 saved panel rows and the
original descriptive ratio formula, with exact values retained beside the PNGs. The first Changi label
is −8.5% (saved −8.50%, rather than the request's illustrative −8%). Island-wide markers identify the
three absolute gainers; only Senoko West meets the naming filter, so the other two use anonymous cell
IDs. The holdout plot keeps October's one-onset result explicitly descriptive, and labels the 1 km
maximum as descriptive selection over saved combinations. Full selections and rounding are in the
folder README; input/font/image hashes and dimensions are in `audit.json`. No table-value mismatch
was found. Tests: 35 passed (14 existing warnings). Wording check: 76 reviewed hits; additional checking
of the deck script and README with the same patterns found no hits.

### Complete project presentation (decision 168; presentation only)

The supplied reference now has a completed 92-slide version: 24 main presentation slides, an appendix
divider, and 67 appendix slides covering all 44 unique saved project graphs and 97 nonempty panels.
Crowded maps have separate place lists; the appendix keeps diagnostics, failed designs and simulations.
The eleven earlier selected charts remain, with SVG versions, and all appendix cards are exported as PNGs.
The reference file and frozen result tables/figures are unchanged. No models or holdouts are re-scored.

One earlier presentation annotation was wrong: October 2026 has **two** onsets, not one. Its annotation
and plotted CSV are corrected; the estimates and descriptive-only conclusion are unchanged. Other
reference wording now distinguishes absolute versus share losses, uses issue-time forecast precision,
reports the simulator v2/v1 pass counts correctly, and discloses corrective/repeated scoring. Candidate
recommendations do not claim measured operational benefits. Input hashes and graph coverage are recorded
in `outputs/presentations/graph_coverage.json`. Poppins/Anton registration and package validation pass.
All slides are rendered for visual inspection. Final gates: 35 tests pass (14 existing warnings);
the wording checker reports the same 76 reviewed hits. No new local data are required.

### HTML research story (decision 169; presentation only)

Created `outputs/story/index.html`: a self-contained navy/Poppins/Anton research presentation with
15 main graphs. The story moves from the rain association through timing, geography and forecasting
to planning candidates and the simulation's limits. Interactive controls select map measure, forecast
horizon and saved day/seven-day intervals. Each chart has a plain-English takeaway and method/source
notes. The searchable evidence viewer retains all 44 saved figures, 97 data panels and 67 panel groups.
Presentation mode supports arrow navigation; all assets are embedded for offline reading.

No model, threshold, frozen table/figure, scoring log or holdout has changed. Named maps retain the
count/q-value filter and counts beside percentages. The page shows the four morning combinations,
corrective refit/repeated scoring, October's two-onset power failure, descriptive 1 km maximum,
failed simulation rule and minute-flow limitations. The after-rain annotation uses the saved table's
explicit 30–60-minute interval. Source hashes are verified before/after rendering in `provenance.json`.

Visual checks cover all 15 main graphs, 1440 px desktop and 400 px phone layouts. SVG labels fit their
bounds at both sizes; Poppins/Anton load successfully, and the browser logs no warnings or errors.
Map positive/negative counts, map measure/horizon/interval controls, search, all 44 gallery entries,
multiple panel groups and keyboard presentation navigation work. Desktop/map/mobile JPG previews are
saved beside the HTML. Final gates: 35 tests passed (14 existing warnings); the wording checker reports
76 existing reviewed hits. Four additional story-prose matches are explicit supply/causality caveats.
