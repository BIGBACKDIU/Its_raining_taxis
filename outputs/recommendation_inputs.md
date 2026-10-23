# Recommendation inputs (for Nat)

Steps 7 and 8 of the analysis, plus phase-2 inputs (steps 10-20, section 5). All numbers describe **vacant-taxi availability** in the public feed (all
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

Simulated, conditional on scenario; none of the 24 tuned scenario combinations passed the held-out plausibility
rule (best 5 of 10 storms; the road-network version v2 also fails, best 1 of 10 - section 5). Read as "what could happen under assumption X":
- Vacant taxis at the rain peak relative to the start: about 0.6-0.9 of the start level in demand-surge or
  supply-drop scenarios (5-95% ranges roughly 0.4-1.4); much lower (about 0.06-0.65) when both happen together.
- Simulated share of requests abandoned during rain: about 1-10% depending on the scenario.
- Step-7 repositioning in the simulation: abandoned requests during rain -1.3 percentage points on average
  (range 0 to -4.7), vacant taxis at the peak -4 points (taxis are in transit), waits essentially unchanged.
These are simulation quantities; they are not observed demand, waiting times or revenue.

## 5. Phase-2 inputs: where to act and what to expect (steps 10-20)

All supply associations in the public feed; named places from URA subzones and nearby landmarks. Tables in
`outputs/tables/`; plain-English detail in `outputs/phase2_progress.md`.

**Where to focus rain measures (by taxis lost).** Most vacant taxis lost per heavy-rain half-hour: Changi Airport
terminals (about 7 taxis each for T3/T2 and T1/Jewel), Raffles Place, Bayfront / Marina Bay Sands, Dhoby Ghaut,
Lavender, Victoria (Bugis), Nicoll (Kampong Glam), City Hall and Chinatown (3-5 taxis each, -22% to -36%)
(`rain_hit_top30_absolute.csv`). The URA Central Area as a whole loses about twice the share elsewhere (-24% vs
-12% in heavy rain), and it is the one place characteristic with a clear, robust association. Rain incentives
or staging aimed at the CBD and its fringe in forecast heavy rain address the largest absolute gap.

**What not to expect from stands, MRT or malls.** A taxi stop/stand or taxi point within 300 m, an MRT exit
within 300 m or a mall shows no clear difference in the heavy-rain drop (differences within about +-1 point,
CIs crossing 0; `stands_effect.csv`, `factors_panel_interactions.csv`). New stands are a dry-weather convenience
and coverage measure, not a proven rain fix.

**Candidate stand / staging locations** (no stand or taxi point within 300 m; `stands_candidates.csv`; qualitative
feasibility only - no cost, kerb-space or traffic-safety data): rain-hit cells in Woodlands South (Vista Point,
Woodlands Hospital), Changi West (Liv@Changi), Lower Seletar (Wisteria Mall), Cheng San (Ang Mo Kio), Bukit Batok
South, Pei Chun (Toa Payoh), Tampines West, Hougang West (Hougang 1), Teck Whye and Bedok North; taxi deserts
in Waterway East (Punggol), Simpang South, Safti (Jurong West), Bayshore (Bedok), Khatib and the Upper Thomson edge.

**Taxi deserts in dry weather** (`taxi_deserts.csv`): Upper Thomson, Waterway East, Punggol Town Centre (23,600
residents, 0.67 vacant taxis per 10,000), Punggol Canal, Pasir Ris Park, Sembawang Straits, Simpang South,
Brickland (Tengah) and Gombak - candidates for dry-weather coverage, separate from the rain question.

**Planning-area sensitivity map** (`stands_predicted_by_planning_area.csv`, resident-weighted predicted heavy-rain
effect, every land cell): Downtown Core, Rochor, Outram, Newton, River Valley about -22% to -23%; large residential
areas such as Bishan, Queenstown, Ang Mo Kio, Bukit Batok and Clementi about -12% to -13%. The prediction model is
weak out of area (R2 0.12), so use this to rank areas roughly, not to quote cell values.

**Timing.** The first millimetre matters most (-9.7% at 1 mm/h, little further deepening above 20 mm/h); long
spells bite harder (heavy rain beyond 2 hours: -18%); after rain stops vacant taxis stay about 5% low for the next
half hour and about 2% low for up to 3 hours, citywide. Recovery takes about 2-2.5 hours from onset
(`dose_*.csv`). Incentives should start with the rain (or the forecast) and run at least 1-2 hours past its end.

**Regional, not local.** Rain 2-5 km away is associated with as large a drop as rain overhead, and the extra drive
time to the nearest vacant taxi in rain is entirely explained by the citywide drop (`spillover_model.csv`,
`minutes_effects.csv`). Measures should target the whole wet region (and the citywide fleet on the road), not
just the cells under the cloud. In island-wide rain, vacant taxis concentrate at the airport terminals and in
Tampines, Katong, Bedok South, Senoko and Tuas, while the CBD thins (`spillover_islandwide_share.csv`) - natural
sources for repositioning.

**Morning planning with the forecast (tests the main recommendation; `morning_forecast_value.csv`).** The NEA
24-hour forecast issued before 09:00 improved predictions of later low-availability half-hours by planning area
and band by 6.6% (CI 5.7-7.5%) in the flexible model - meeting the pre-registered materiality rule - but not in
the simpler regression or with the issue-time label. Support for "plan the day with the morning forecast" is
real but modest.

**Fleet trend (`fleet_meta_regression.csv`).** As the fleet fell from about 15,400 to 11,900 taxis, heavy rain took
a larger local share (2.2 log-points per 1,000 fewer taxis, CI 0.3-4.1); feed-coverage changes compete as an
explanation. If the fleet keeps shrinking, expect rain gaps to widen somewhat.

**Simulation v2 and dispatcher (`sim/v2/index.html`).** Rebuilt on OpenStreetMap drive times with place
characteristics; it reproduces where taxis are much better than v1, but no scenario passes the held-out
plausibility rule (best 1 of 10 storms) and even a statistical non-simulation path passes only 3 of 10. The
dispatcher panel lists staging moves per 30 minutes (from area -> named place, taxis, reason) as a
**demonstration on historical replays, not a live system**; present it as an illustration of how a plan would
read, not as evidence of its effect.
