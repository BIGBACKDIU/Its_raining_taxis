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
8. **Simulation.** A storm simulator (`sim/index.html`) shows how demand surges, drivers going offline, or both,
   could play out. It is scenario-based and **none of the 24 tuned scenarios passed the plausibility check we fixed
   in advance** on 10 held-out storms (best: 5 of 10). Use it to explain mechanisms, not to predict. (fig 14)

## 2. How sure are we?

- **Strong:** rain is associated with fewer vacant taxis. The sign and size hold across three model types, 3-gauge
  rain, each fiscal year, 500 m cells, 15-minute snapshots, negative binomial models, a sample with excluded days put
  back, a rain window shifted by 15 minutes, a permutation test (p < 0.001, assuming rain days are exchangeable
  within month and day type) and day / storm bootstraps. (`effects_robust.csv`, `inference_*.csv`)
- **Moderate:** the size of the effect varies between feed periods more than chance allows (direction consistent,
  size varies), and is larger in the test year (2025-26) than earlier. Season and time of day do not explain it.
- **Strong (for the tested setups):** the weather gain in forecasting is negligible. Wider labels, scales and
  horizons were checked in a pre-registered secondary analysis; the conclusion is limited to the models, labels and
  horizons we tried.
- **Weak:** simulation numbers (failed plausibility) and modelled travel times / shortfall reductions in the plan.

## 3. Caveats

- **The feed's coverage changes.** The number of taxis in the feed jumps between periods (about half in Aug - Nov
  2022, about double in Oct 2025 - Jan 2026, with duplicate records). We found 18 such regimes and 8 short outages
  and allowed for them in every model; some excluded days (100) and missing months (Jun 2025 mostly) remain.
- **Retrospective labels.** "Unusually low" in the test year uses each feed regime's normal level estimated from
  that regime's own data. A second scoring with a label knowable at forecast time gives the same conclusions.
- **The test year was used more than once.** `outputs/test_scoring_log.csv` lists 19 runs that scored or used
  test-year outcomes (13 reconstructed from file times): the pre-specified primary scoring, a pre-registered
  secondary analysis, post-hoc checks (marked as such), the policy evaluation, the simulation's held-out storms, and
  re-scorings after an independent review. No forecasting model was refitted after the first scoring.
- **Not available:** company field (CDG vs others), trip / booking data (requested from LTA), road speeds.
  Travel times and destination patterns in the plan and simulation are assumptions.
- Rain is measured at the nearest working gauge; snapshots are taken about 19 seconds before the rain window ends
  (checked: shifting the window by 15 minutes does not change the conclusions).
