# Recommendation inputs (for Nat)

Steps 7 and 8 of the analysis, plus phase-2 inputs (steps 10-20, section 5). All numbers describe **vacant-taxi availability** in the public feed (all
operators; CDG cannot be separated). They are associations, not causes. Simulation numbers are **simulated,
conditional on a scenario**, and no simulation scenario (before or after the conservation fix) passes the
pre-registered plausibility check on held-out storms, so they are illustrations of mechanisms, not predictions.

## 1. What the forecasting result means for the recommendation

All forecasting results are evaluated against **retrospective labels**: the test-year "normal level" uses each
feed regime's level estimated from that regime's own test-year rows, and the regime change points were found on
all five years. A second scoring with an **issue-time-knowable label** (normal level = usual pattern x the
coverage level of the previous 7 days, known when the forecast is made) gives the same picture
(`forecast_eval_both_labels.csv`).

- Short-term forecasts (30-120 min) of unusually low availability beat "it stays as it is now". At a fixed
  workload of 19 alerted cells per half hour (5% of analysed cells), 1 km, 30 min: 53% of alerted cells are
  really low with LightGBM vs 46% with persistence (issue-time label: 54% vs 47%).
- **No material weather gain** (all 36 comparisons below the pre-registered 0.01 PR-AUC threshold; largest
  +0.002) for the tested labels, models and horizons; also in normal-coverage months and with issue-time labels
  (largest +0.0024). Recommendation: drive real-time repositioning with availability forecasts built from current
  taxi numbers and the usual pattern for the place and time; the tested weather inputs did not add to them.
- Early warning is limited: with 19 alerts per half hour, only 6-14% of low-availability runs get an alert
  before they start (1 km; 30 / 60 min ahead); a further 3-10% are flagged at or after onset; most runs are
  never flagged. A simple "usual risk for this place and time" ranking warns more runs before onset at 30 min
  (13%) but is less precise (43%).
- Weather is useful for **planning in advance** (section 3): rain is reliably associated with fewer vacant taxis,
  and the NEA 2-hour forecast flags when.

## 2. Repositioning plan (step 7) - `outputs/tables/policy_*.csv`

- Model: move idle CDG taxis (62% of surplus vacant taxis in over-supplied cells) to cells forecast to fall short
  of their normal level, where a taxi stop or stand is within 300 m, within 60 minutes' modelled travel.
- **Recommended variant: weight destinations by the forecast risk of low availability** (chosen on the
  calibration period, Apr - Sep 2025). Test year, scored once: 43% of targeted cells were really unusually low
  60 minutes later, against 31% for the first design (equal weights) and 28% for all candidate cells
  (issue-time label: 44% vs 31% vs 28%).
- **Trade-off, stated plainly.** The forecast alone, ranking the 19 riskiest cells with no operational limits,
  reaches 51%. The policy's limits cost targeting precision: requiring a taxi stop or stand nearby costs about
  3 points (48%), and the travel-cost / supply allocation about 4 more (43%). The first design lost most
  (down to 31%) because it spread taxis over about 76 cells chosen by expected shortfall rather than risk.
  The risk-weighted plan is sharper but moves fewer taxis: about 38 taxis to about 20 cells per half-hour
  decision (183 taxi-minutes), against about 118 taxis to 66 cells (659 taxi-minutes) for the first design.
- Modelled expected shortfall reductions are model quantities, not observed demand or service.
- Cells most often targeted by the risk-weighted plan (calibration period; `policy_staging_plans_risk_weights.csv`):
  when it rains - Geylang, Tampines, Downtown Core, Sembawang, Novena, Sengkang, Woodlands; when dry - Bukit Merah
  (4 cells), Geylang, Tampines, Novena, Changi, Downtown Core. Equal-weight plans by weighting scenario remain in
  `policy_staging_plans.csv`.
- Sensitivity of the first design: travel cost (lambda) and budget N matter most; congestion and weighting
  scenario matter little (`policy_sensitivity.csv`).

## 3. Planning layer - `outputs/tables/planning_*.csv`, figure `planning_forecast_rain.png`

When NEA issues a showers / thundery forecast, vacant taxis run about 7% below the no-rain level on average
(heavy rain observed: about 14% below). The largest expected shortfalls in taxis per half hour (whole area,
weekday):
- Changi 00-10 (airport queue): 25-33 fewer vacant taxis per half hour (-16% to -23%).
- Bukit Merah night and evening peak: 21-25 fewer (-28% to -33%).
- Downtown Core early morning: about 20 fewer (-43%).
- Geylang and Kallang, morning and evening peaks: 16-18 fewer (-24% to -28%).
Use these to time rain incentives (e.g. driver bonuses) for forecast rainy periods, before rain starts.

## 4. Simulation ranges (step 8) - `outputs/tables/sim_*.csv`, page `sim/index.html`

Simulated, conditional on scenario. The first version of these ranges came from a simulator with a matching bug
(requests could be served more than once) and is void; the numbers below are from the fixed, retuned simulator.
No tuned combination passes the held-out plausibility rule (best 4 of 10 storms; the road-network version v2
best 3 of 10 - section 5). Read as "what could happen under assumption X":
- Vacant taxis at the rain peak relative to the start: about 0.7-1.0 of the start level in demand-surge or
  supply-drop scenarios (5-95% ranges roughly 0.5-1.5); about 0.5-0.8 when both happen together (5-95% roughly
  0.3-1.25).
- Simulated share of requests abandoned during rain: about 0.1-5% depending on the scenario.
- Step-7 repositioning in the simulation: abandoned requests during rain -0.3 percentage points on average
  (range 0 to -2.3), vacant taxis at the peak -2 points (taxis are in transit), waits essentially unchanged.
These are simulation quantities; they are not observed demand, waiting times or revenue.

## 5. Phase-2 inputs: where to act and what to expect (steps 10-20)

All supply associations in the public feed; named places from URA subzones and nearby landmarks. Named lists
show only cells with at least 4 expected vacant taxis in heavy rain and an effect passing a 10% false-discovery
rate; full lists are appendix tables. Plain-English detail in `outputs/phase2_progress.md`.

**Where to focus rain measures (by taxis lost).** Most vacant taxis lost per heavy-rain half-hour: Changi Airport
terminals (about 7 taxis each at T3/T2 and T1/Jewel), Raffles Place, Bayfront / Marina Bay Sands, Dhoby Ghaut,
Lavender, Victoria (Bugis), Nicoll (Kampong Glam), City Hall and Chinatown (3-5 taxis each, -22% to -36%)
(`rain_hit_top30_absolute.csv`). The URA Central Area loses about twice as much as elsewhere (-24.5% vs -12.0% in
heavy rain in the panel model), and it is the only place characteristic supported in every design. Rain
incentives or staging aimed at the CBD and its fringe in forecast heavy rain address the largest absolute gap.

**What not to expect from stands, MRT or malls.** A taxi stop/stand or taxi point within 300 m, an MRT exit
within 300 m or a mall shows no clear difference in the heavy-rain drop in the panel model (differences within
about +-1 point, CIs crossing 0; `stands_effect.csv`, `factors_panel_interactions.csv`); a small association with
stands appears only in the cell-level spatial model and is not robust. New stands are a dry-weather convenience
and coverage measure, not a proven rain fix.

**Candidate stand / staging locations** (no stand or taxi point within 300 m; `stands_candidates.csv`; qualitative
feasibility only - no cost, kerb-space or traffic-safety data): rain-hit cells (listable, top 100 by taxis lost)
in Woodlands South (Vista Point, Woodlands Hospital), Changi West (Liv@Changi), Lower Seletar (Wisteria Mall),
Cheng San (Ang Mo Kio), Bukit Batok South (two cells), Pei Chun (Toa Payoh), Tampines West, Hougang West (Hougang
1), Teck Whye, Bedok North, Yishun East and Yunnan; dry-weather taxi deserts in Safti (Jurong West), Bayshore
(Bedok), Khatib, Sunset Way, Fernvale and Punggol Field.

**Dry-weather taxi deserts** (`taxi_deserts.csv`, dry snapshots only): Punggol Town Centre (23,600 residents,
0.73 dry-weather vacant taxis per 10,000), Punggol Canal, Brickland (Tengah), Gombak, Anak Bukit, Safti, Chin
Bee, Bedok South, Ulu Pandan, Kovan and Woodlands East - candidates for dry-weather coverage, separate from the
rain question.

**Planning-area sensitivity map** (`stands_predicted_by_planning_area.csv`, resident-weighted predicted heavy-rain
effect for every land cell, using the training transform): Museum -27.6%, Downtown Core -25.2%, Outram -23.8%;
among large residential areas Woodlands -16.8%, Sembawang -16.7% and Choa Chu Kang -16.1% at the high end, Bishan
-9.4%, Ang Mo Kio -9.6%, Bukit Merah -10.3% and Queenstown -10.5% at the low end. The prediction model is weak out
of area (R2 0.12), so use this to rank areas roughly, not to quote cell values.

**Timing.** The first millimetre matters most (-9.7% at 1 mm/h, little further deepening above 20 mm/h); long
spells bite harder (heavy rain beyond 2 hours: -18%); after rain stops vacant taxis stay about 5% below the dry
level for the next half hour and about 2% below for up to 3 hours, citywide. By the registered statistical
recovery criterion (event-study CIs include zero from 120 / 150 minutes after onset), cells recover within about
2-2.5 hours. Incentives should start with the rain (or the forecast) and run at least 1-2 hours past its end.

**Regional, not local.** Rain 2-5 km away is associated with as large a drop as rain overhead, and the longer
drive to the nearest vacant taxi in rain is associated with the citywide drop (a conditional association only;
`spillover_model.csv`, `minutes_effects.csv`). Measures should target the whole wet region and the citywide fleet
on the road, not just the cells under the cloud. In island-wide rain almost every cell loses vacant taxis (329 of
374 clearly, 3 gain); the CBD loses share most (Bayfront -22%, Dhoby Ghaut -20%, Raffles Place -17%), and the
places that gain share (Tampines, Yishun, Clementi, Pasir Ris, Woodlands West; +3% to +5%) still lose taxis, so
there is no surplus area to draw from in island-wide rain.

**Morning planning with the forecast (tests the main recommendation; `morning_forecast_value.csv`).** Using only
information knowable at 09:00, the latest NEA 24-hour forecast issued before 09:00 improved predictions of later
low-availability half-hours by planning area and band by 10.1% (retrospective label) and 6.3% (issue-time label)
in the flexible model - both meet the pre-registered materiality rule - but not in the linear regression. This
supports planning the day around the morning forecast with a flexible model.

**Fleet trend (`fleet_meta_regression.csv`).** No clear relation between the monthly heavy-rain effect and the
LTA fleet size once the regime coverage level is controlled and errors allow for autocorrelation (share: -2.0
log-points per 1,000 fewer taxis, CI -4.3 to +0.3).

**Simulation v2 and dispatcher (`sim/v2/index.html`).** Both simulators had a matching bug that let requests be
served more than once; after the fix and retuning, no scenario of either version passes the held-out plausibility
rule (step 8 best 4 of 10 storms, v2 best 3 of 10), while a statistical non-simulation path passes 3 of 10. v2
places taxis well (cell correlation 0.87-0.92) but its timing is weak (0.38-0.54). The dispatcher panel lists
staging moves per 30 minutes (from area -> named place, taxis, reason) as a **demonstration on historical
replays, not a live system**; present it as an illustration of how a plan would read, not as evidence of its
effect.
