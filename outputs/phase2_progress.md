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
- Heavy rain lengthens that drive by 2.5% (CI 1.9 to 3.0%; light 2.0%, moderate 2.2%). With the citywide
  vacant count added as a regressor the effect is about zero (heavy +0.05%, CI -0.26 to +0.37%): rain moves the
  nearest taxi further away through the citywide drop in vacant taxis, not through a separate local gap.
- Most extra minutes in heavy rain (named): Changi Airport (+0.8 min, +22.6%), Plab / Paya Lebar (+12.5%),
  Swiss Club / Chatsworth International School (+16.1%), Changi Point / Changi Village (+14.3%), Sentosa
  (Quayside Isle, +8.5%; S.E.A. Aquarium, +6.3%), Seletar Aerospace Park (+13.4%).
- Chart: `minutes_to_taxi_maps`. Tables: `minutes_effects.csv`, `minutes_cells_named.csv`.

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

## Step 18 - Rain measurement error (decision 116)

- 64% of cell-days are more than 1 km from the nearest working rain gauge.
- Heavy-rain effect near a gauge (<= 1 km) -12.4% (CI -13.8 to -11.0); far (> 1 km) -13.3% (CI -14.8 to
  -11.8). Interaction: far cells lose 1.0 percentage point more (CI 0.0 to 2.0) - the opposite of the
  attenuation that pure measurement error would cause, so distance to the gauge does not visibly weaken the
  estimates (far cells also differ in other ways, so this is not a clean test).
- Reliability ratio of the cell rain measure (nearest gauge vs the 2nd/3rd nearest): 0.72 (correlation 0.79).
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
