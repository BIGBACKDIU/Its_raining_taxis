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
  [Withdrawn in review fix B5 below: the next sentence's correction rests on an unsupported assumption.]
  Under the classical-error assumption the headline heavy-rain effect (-12.9%) could be understated, with an
  indicative corrected size of about -17.5%; because the near/far comparison shows no attenuation, the true
  understatement is probably smaller. Table: `gauges_measurement_error.csv`.

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
  - Noise floor: two non-simulation references (the normal time-of-day path, and baseline x the estimated rain
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
