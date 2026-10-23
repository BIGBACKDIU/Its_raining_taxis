# Recommendation inputs (for Nat)

Steps 7 and 8 of the analysis. All numbers describe **vacant-taxi availability** in the public feed (all
operators; CDG cannot be separated). They are associations, not causes. Simulation numbers are **simulated,
conditional on a scenario**, and no simulation scenario passed the pre-registered plausibility check on held-out
storms, so they are illustrations of mechanisms, not predictions.

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
- Test year, base case (200 taxis per decision): about 150-170 taxis moved to 73-78 cells per half-hour decision.
  Targeted cells were unusually low 31-32% of the time vs 28% for all candidate cells (retrospective label);
  30-32% vs 27-28% with the issue-time label. A 50-taxi budget picks clearer cases (35-39%).
- Modelled expected shortfall at targeted cells falls by about 34-39% (a model quantity).
- Cells most often targeted when it rains (equal weights): Tampines (2 cells), Geylang, Sengkang (2), Ang Mo Kio,
  Woodlands, Clementi, Hougang - see `policy_staging_plans.csv` for the ranked lists by weighting scenario
  (equal, MRT-station activity, land-use proxy).
- Sensitivity: travel cost (lambda) and budget N matter most; congestion and weighting scenario matter little
  (`policy_sensitivity.csv`).

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

Simulated, conditional on scenario; none of the 24 tuned scenario combinations passed the held-out plausibility
rule (best 5 of 10 storms). Read as "what could happen under assumption X":
- Vacant taxis at the rain peak relative to the start: about 0.6-0.9 of the start level in demand-surge or
  supply-drop scenarios (5-95% ranges roughly 0.4-1.4); much lower (about 0.06-0.65) when both happen together.
- Simulated share of requests abandoned during rain: about 1-10% depending on the scenario.
- Step-7 repositioning in the simulation: abandoned requests during rain -1.3 percentage points on average
  (range 0 to -4.7), vacant taxis at the peak -4 points (taxis are in transit), waits essentially unchanged.
These are simulation quantities; they are not observed demand, waiting times or revenue.
