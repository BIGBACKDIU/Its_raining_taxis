# It's raining taxis - summary of results

For Ben, En and Manda (analysis summary). Plain English; every number traces to a file in `outputs/tables/`, and
every choice is logged in `outputs/decisions.md`.

**What the data can and cannot say.** We observe *vacant* taxis in the public feed (all operators; CDG cannot be
separated), every 30 minutes (15 from Oct 2024), Oct 2021 - Sep 2026, on 374 analysed 1 km cells, with NEA rain
gauges and 2-hour forecasts. Vacant taxis are supply, not demand: the results say nothing directly about unmet
demand, waiting times or revenue. All rain results are **associations**, not causes - the feed cannot tell whether
taxis disappear because they are booked, go off shift, move away or are stuck in traffic.

## 1. Main findings

1. **Rain is associated with fewer vacant taxis, and more so the heavier it rains.** Compared with the same cell at
   the same time of week in dry weather (Apr 2022 - Mar 2025), vacant taxis are 7.7% lower in light rain, 10.8% in
   moderate rain and 12.9% in heavy rain (> 10 mm/h). Part of this is citywide: comparing each cell with all other
   cells at the same moment (the "share" model), the extra local drop is 1.9%, 4.5% and 5.7%.
   (`effects_main.csv`, fig 4)
2. **The drop starts before rain arrives and fades within about two hours.** Vacant taxis are about 5% lower in
   the first hour after rain starts in a cell, and back near normal after about 2.5 hours. When heavier rain falls
   2-5 km away while a cell is still dry, it already has 7% fewer vacant taxis; an NEA "thundery showers" forecast
   goes with 5% fewer before any rain falls. (`effects_event_study.csv`, `effects_approach.csv`,
   `effects_forecast.csv`; figs 5-6)
3. **Where and when it matters most.** Heavy-rain drops are larger in the city centre (-24% vs -12% elsewhere) and
   in weekday rush hours (-18% vs -11%). 299 of 374 cells have significantly fewer vacant taxis in heavy rain
   (false-discovery rate 10%). Heavy rain raises the odds of unusually low availability in a cell by about 1.5
   times; 114 of the 179 cells we could test show a clear increase. (`effects_interact.csv`,
   `inference_hotspots.csv`, `risk_*.csv`; figs 8-9)
4. **The planning view.** When NEA forecasts showers or thunder, vacant taxis run about 7% below the no-rain level
   on average (heavy rain observed: about 14%). The biggest shortfalls in taxis are at Changi early in the day,
   Bukit Merah at night and in the evening peak, Downtown Core early morning, and Geylang / Kallang in both rush
   hours. (`planning_*.csv`, fig 12)
5. **Weather does not add material early-warning skill (the centrepiece).** Forecasts of unusually low
   availability 30-120 minutes ahead clearly beat "it stays as it is now": alerting the 19 riskiest cells each
   half hour, 53% are really unusually low 30 minutes later with LightGBM vs 46% with persistence. But adding
   weather data gives **no material weather gain (all 36 comparisons below the pre-registered 0.01 PR-AUC
   threshold; largest +0.002) for the tested labels, models and horizons**, also in rainy periods, at 2 km and
   planning-area scale, in normal-coverage months, and with labels that are knowable when the forecast is made.
   Likely reason: rain moves expected counts by 5-15%, while a cell's count swings much more from half hour to half
   hour. (`forecast_eval_both_labels.csv`, `s1_results.csv`; figs 10-11)
6. **Early warning is limited.** With 19 alerts per half hour, only 6% (30 min ahead) to 13% (60 min ahead) of
   low-availability runs get an alert before they start; another 3-9% are flagged at or after the start; most are
   never flagged. (`forecast_eval_lead_both_labels.csv`)
7. **Repositioning plan.** A plan that moves idle CDG taxis towards cells at risk, weighting cells by the forecast
   risk, targets cells that are really low 43% of the time (all candidate cells: 28%). Operational limits (a taxi
   stop nearby, travel time, available spare taxis) cost precision: the unconstrained forecast ranking reaches 51%.
   (`policy_diagnosis.csv`, fig 13; details for Nat in `recommendation_inputs.md`)
8. **Simulation.** Two storm simulators (`sim/index.html`; `sim/v2/index.html` on OpenStreetMap road times, with a
   dispatcher panel) show how demand surges, drivers going offline, or both, could play out. Reviews found and
   fixed matching errors (requests served more than once; then totals that no matching could achieve); the final
   version allocates taxis to requests by integer flows on permitted ring edges, checked against an exact
   max-flow. After the fix and retuning, **no tuned scenario of either version passes the plausibility check we
   fixed in advance** on 10 held-out storms (best: 4 of 10 and 3 of 10); this is the reported result. The
   citywide level matches on average, but timing matches only moderately and which cells lose taxis poorly. A
   non-simulation benchmark (baseline x estimated rain effects) also fails the rule, passing 3 of the 10 held-out
   storms; the rule stays unchanged. Use the pages to explain mechanisms, not to predict. (figs 14, 26-27)
9. **Morning planning.** Information available by 09:00 - recent issue-time labels, usual patterns and the
   single latest NEA 24-hour forecast issued before 09:00 - predicts how many low-availability half-hours a
   planning area will have later that day. This is the second scoring of the test year, made after the timing
   fixes the reviewer required (the first scoring met the materiality rule only on the retrospective label).
   Adding the forecast cut the test-year deviance by 10.1% [9.4, 10.8] (retrospective label) and 6.3% [4.9, 7.5]
   (issue-time label) in the flexible model, meeting the materiality rule fixed in advance for both labels. In the
   linear regression the forecast made essentially no difference on the retrospective label and made it 4.5%
   worse on the issue-time label. Support for planning the day around the morning forecast, from a flexible
   model. (`morning_forecast_value.csv`)

## 2. Where and why (phase 2)

All numbers are heavy rain (> 10 mm/h) vs the no-rain expectation for the same cell and time, Apr 2022 - Mar
2025, unless stated; 95% CIs in brackets. Associations with vacant-taxi supply, not causes. Named places are
listed only where the cell expects at least 4 vacant taxis in heavy rain and the effect passes a 10%
false-discovery rate across the 374 analysed cells; full lists are in the `*_all.csv` appendix tables.

**Where heavy rain takes the most taxis away** (`rain_hit_top30_absolute.csv`, fig 15). In taxis lost per
heavy-rain half-hour: Changi Airport T3/T2 (7.1 of 83 expected; -8.5% [-15.6, -0.6]) and T1/Jewel (6.9 of 43;
-15.9%) - large because the airport holds so many taxis, not because it loses a big share; then the CBD and its
fringe: Raffles Place / Lau Pa Sat (4.9 of 16; -30.8% [-38.2, -23.5]), Bayfront / Marina Bay Sands (4.8 of 13;
-36.4%), Dhoby Ghaut / Fort Canning (3.7 of 11; -34.9%), Lavender (3.6; -21.9%), Victoria / Bugis (3.5; -23.9%),
Nicoll / Kampong Glam (3.2), City Hall (3.0), Chinatown (3.0), Farrer Park (2.7) and Woodlands East (2.5; -17.3%).
The median analysed cell loses 14.9%; 309 of 374 cells pass the false-discovery rate.

**Where the local share falls most** (`rain_hit_top30_share.csv`). Relative to the citywide drop, with the
absolute loss per heavy-rain half-hour: Bayfront -26.4% (-4.8 taxis [-5.4, -4.1]), North Coast (Woodlands)
-25.6% (-2.5 [-2.9, -2.0]), Dhoby Ghaut -25.5% (-3.8 [-4.2, -3.3]), Sembawang East -25.0% (-1.8), Raffles Place
-21.1% (-4.9), Monk's Hill (Newton) -18.1% (-1.5), Woodlands South, City Hall, Sentosa and Changi West (-15%
to -16%). The earlier extreme share losses at Plab, Marina South and Seletar Aerospace Park came from cells with
fewer than 4 expected taxis and are no longer listed.

**Where the share rises** (`rain_gainers.csv`). 14 listable cells gain share in heavy rain, but in only two does
the number of vacant taxis itself rise: Senoko West (+37% share; +1.7 taxis [1.1, 2.3]) and Yio Chu Kang East /
Nanyang Polytechnic (+20%; +1.4 [0.2, 2.6]). Elsewhere (Depot Road, Geylang Bahru, Kebun Bahru, Xilin, Kampong
Tiong Bahru, Bishan East) the count stays the same or falls, and the share rises only because other places lose
more. In island-wide rain (`spillover_islandwide_share.csv`, fig 25) 329 of 374 cells have fewer vacant taxis
and 3 have more; listable share losers are Bayfront (-22%; -4.1 taxis), Dhoby Ghaut (-20%; -3.2), Kampong Ubi
(-19%; -1.3), Raffles Place (-17%; -4.4), North Coast, City Hall, Monk's Hill and Victoria; the listable share
gainers (+3% to +5%: Tampines East and West, Yishun South, Clementi West, Pasir Ris Drive, Woodlands West) all
still lose taxis in absolute terms.

**Why: what distinguishes places that lose more** (step 12; figs 19-20). Three designs, reported separately:
- **Panel model with heavy-rain interactions (day-clustered CIs):** heavy rain goes with -24.5% [-27.6, -21.3]
  vacant taxis in the URA Central Area vs -12.0% [-13.5, -10.6] in cells 1 km or more from an MRT exit (share:
  -18.9% vs -5.0%). Within 300 m of an MRT exit -12.5% (difference -0.5% [-2.2, +1.2]); a taxi stand within
  300 m -11.7% (difference +0.4% [-1.2, +2.0]); a mall in the cell -12.3%; HDB density and distance to the city
  show no clear difference.
- **Cell-level weighted regression (374 cells):** Central Area cells lose 10.6% more [3.0, 17.6] than
  otherwise similar cells; business/industrial land goes with a 3.6% smaller loss per SD [1.5, 5.8]; an MRT
  interchange within 800 m with a 5.2% smaller loss [1.3, 9.4] but each SD more MRT lines within 800 m with a 2.7%
  larger loss [0.7, 4.7]; taxi stands within 300 m +2.5% per SD [0.3, 4.7]; several others are significant here
  only (new station nearby, HDB resale price, share 65+, hospitals, commercial land, distance to the airport).
- **Spatial-error model (residuals were spatially clustered):** Central Area -10.7% [1.9, 18.6]; business land
  +3.6% per SD [1.6, 5.6]; interchange +5.5% [0.1, 11.2]; MRT lines -3.4% per SD [-5.7, -1.0]; taxi stands +3.0%
  per SD [0.6, 5.4]; HDB units +3.4% per SD [0.3, 6.5] appears here only.
- **Robust across designs:** the Central Area (all three designs). Business/industrial land, the MRT interchange
  and the number of MRT lines nearby hold in both cell-level designs but are not tested in the panel; the last
  two have opposite signs and overlap, so read them together, not as separate effects. Taxi stands hold in both
  cell-level designs but show no difference in the panel, and HDB density appears in one design only: neither is
  robust. A random forest predicts the cell effects weakly out of area (spatial-CV R2 0.12-0.15; type-0 AUC
  0.70-0.71).

**Why: rain is regional, and the drop is mostly citywide.** Rain 2-5 km away goes with -6.7% [-7.9, -5.4]
vacant taxis even with the cell's own rain in the model (own heavy rain then -5.6%). The drive time to the
nearest vacant taxi is 2.5% [1.9, 3.0] longer in heavy rain (median dry drive 1.6 min); with the citywide vacant
count in the model the difference is +0.05% [-0.26, +0.37] - associated with the citywide drop (a conditional
association only). Listable places with the most extra drive time include Monk's Hill (+18%), Tampines East
(+15%), Bishan East (+10%) and Sentosa (+5%). (figs 16, 25)

**How rain bites: onset, duration, after-effects** (fig 21). The first millimetre matters most (-9.7% at 1 mm/h;
-13% from 20 mm/h, no further deepening). Long spells bite harder: heavy rain -11.4% in its first 30 minutes,
-18.0% [-21.2, -14.6] after 2 hours. After rain stops, vacant taxis stay 5.3% below the dry level for the next half
hour and about 2% below for up to 3 hours - citywide (no local share hangover). By the registered statistical
recovery criterion (every event-study CI from that bin on includes zero), rain-sensitive cells recover 150 minutes
after onset and others 120 minutes.

**Taxi deserts in dry weather** (`taxi_deserts.csv`, figs 17-18; dry snapshots only, analysed cells). Fewest
dry-weather vacant taxis per resident: Punggol Town Centre (23,600 residents, 1.7 vacant taxis, 0.73 per 10,000),
Punggol Canal, Brickland (Tengah), Gombak (two cells), Anak Bukit, Safti, Chin Bee, Bedok South, Ulu Pandan,
Kovan and Woodlands East (43,100 residents, 1.20 per 10,000).

**Over time and other checks.** Against the LTA fleet (15,400 down to 11,900 taxis) the monthly heavy-rain
effect shows no clear trend once the regime coverage level is controlled and errors allow for autocorrelation:
per 1,000 fewer taxis -0.9 log-points [-2.8, +1.0] (absolute) and -2.0 [-4.3, +0.3] (share) (fig 23). New MRT
stations (Thomson-East Coast Line stages 3-4, Punggol Coast, Hume) show no clear change in nearby dry-weather
supply (+2.2% [-6.8, +12.1]) or in the heavy-rain effect (-4.2% [-13.4, +5.9]); pre-opening trends differ
(p < 0.001), so this is not a clean test (fig 22). Cells far from a working rain gauge show slightly larger, not
smaller, effects; gauge agreement and the near/far comparison are sensitivity diagnostics only, and no
correction is applied to the headline.

## 3. How sure are we?

- **Strong:** rain is associated with fewer vacant taxis. The sign and size hold across three model types, 3-gauge
  rain, each fiscal year, 500 m cells, 15-minute snapshots, negative binomial models, a sample with excluded days put
  back, a rain window shifted by 15 minutes, a permutation test (p < 0.001, assuming rain days are exchangeable
  within month and day type) and day / storm bootstraps. (`effects_robust.csv`, `inference_*.csv`)
- **Moderate:** the size of the effect varies between feed periods more than chance allows (direction consistent,
  size varies), and is larger in the test year (2025-26) than earlier. Season and time of day do not explain it.
- **Strong (for the tested setups):** the weather gain in forecasting is negligible. Wider labels, scales and
  horizons were checked in a pre-registered secondary analysis; the conclusion is limited to the models, labels and
  horizons we tried.
- **Moderate (phase 2):** the named rankings of places (day-bootstrap CIs; presented lists pass a 10%
  false-discovery rate and need >= 4 expected taxis) and the Central Area contrast (all three designs). **Weak:**
  which characteristics explain the rest (low out-of-area R2; most associations hold in only one design), the
  MRT natural experiment (pre-trends fail), the fleet trend (no clear relation) and predictions for cells without
  reliable taxi data (extrapolations).
- **Weak:** simulation numbers (both versions fail the plausibility check after the conservation fix) and modelled travel times / shortfall
  reductions in the plan.

## 4. Caveats

- **The feed's coverage changes.** The number of taxis in the feed jumps between periods (about half in Aug - Nov
  2022, about double in Oct 2025 - Jan 2026, with duplicate records). We found 18 such regimes and 8 short outages
  and allowed for them in every model; some excluded days (100) and missing months (Jun 2025 mostly) remain.
- **Retrospective labels.** "Unusually low" in the test year uses each feed regime's normal level estimated from
  that regime's own data. A second scoring with a label knowable at forecast time gives the same conclusions.
- **The test year was used more than once.** `outputs/test_scoring_log.csv` lists 45 runs that scored or used
  test-year outcomes (13 reconstructed from file times): the pre-specified primary scoring, a pre-registered
  secondary analysis, post-hoc checks (marked as such), the policy evaluation, the simulation's held-out storms,
  re-scorings after an independent review, and phase-2 uses (morning-forecast scoring once, test-year months in the
  fleet-trend and MRT analyses as associations, simulation v2 held-out check, and re-runs after the second review:
  morning-forecast re-scoring once, simulation retuning checks and grid). No forecasting model was refitted
  after its first scoring.
- **Not available:** company field (CDG vs others), trip / booking data (requested from LTA), observed road
  speeds, LTA pick-up bay locations (need a DataMall key; OpenStreetMap taxi points used as a partial proxy).
  Road times come from OpenStreetMap road classes and speed limits (rain = x 1.25); destination patterns in the
  plan and simulation are assumptions. Residents are Census 2020 (2025 subzone tables were not downloadable).
- Rain is measured at the nearest working gauge; snapshots are taken about 19 seconds before the rain window ends
  (checked: shifting the window by 15 minutes does not change the conclusions).
