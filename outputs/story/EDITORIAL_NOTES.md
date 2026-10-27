# Main-story editorial rationale

The presentation answers four connected questions: how much supply falls; where and when; whether weather improves useful warning; and how that informs a feasible planning trial. Every main figure has a specific role in that argument. The complete 44-figure appendix remains available.

The cover omits the graph count and methodological slogans. Measurement/identification details belong with the relevant evidence. Radar sensitivity, simulator realism, weak explanatory models and other diagnostics remain in the appendix. The live Storm Builder follows the recommendation as an optional scenario demonstration, with its limitations stated.

Graph 1 uses arithmetic over the existing storm export: at 09:30, 2,309.5936 expected minus 1,473 observed = 836.5936 (shown as 837), or a 36.2225% gap. At 08:30, 258 cells with zero rain in the preceding half-hour have 1,167 observed versus 1,319.8843 expected, a gap of 11.5832%. These descriptive comparisons motivate the fitted analyses; they do not attribute the gap to a mechanism.

The approaching-rain definition was checked against `analysis/03_effects_more.py`: the 2–5 km ring indicator uses >2.5 mm/h while the own cell is dry for three half-hours. It is not the >10 mm/h heavy band. Frozen tables are unchanged.

## 1. At this storm’s peak, 837 fewer vacant taxis than expected.

At 09:30, there are 1,473 taxis versus 2,309.6 expected: 837 fewer (−36.2%). At 08:30, the 258 cells with no rain in the preceding half-hour already have 11.6% fewer than expected.

**Decision implication:** The rain footprint alone misses part of the supply gap. A useful warning system must look beyond the square under the cloud.

**Method:** A storm-day shortfall, measured against the usual level. **Source:** `storm_2023-07-20.csv`.

**Next question:** Does this pattern persist across years, after usual place and time differences are controlled?

## 2. Heavy rain is associated with 12.9% fewer vacant taxis.

Light, moderate and heavy rain correspond to 7.7%, 10.8% and 12.9% fewer vacant taxis. Heavy rain still has a −5.7% local-share association after the citywide comparison.

**Decision implication:** Rain is linked to both a wider supply drop and extra local losses. Focusing only on the wet square would miss the wider part.

**Method:** Same-place, same-time Poisson comparison. **Source:** `effects_main.csv`.

**Next question:** Which places and times have the largest losses?

## 3. The central-area percentage loss is about twice as large.

The central-area contrast is −24.2% versus −11.9% outside. Weekday rush periods show −18.1% versus −11.3% at other times.

**Decision implication:** Rain plans should give extra attention to central coverage and weekday peaks. Next, translate percentages into the number of taxis involved.

**Method:** Spatial estimates plus group-interaction regressions. **Source:** `rain_hit_absolute_all.csv · effects_interact.csv`.

**Next question:** Does the largest percentage loss also mean the most taxis lost?

## 4. Changi loses more taxis; Bayfront loses a larger fraction.

Changi T3: 7.08 of 83.37 taxis (−8.50%). Marina Bay Sands: 4.76 of 13.08 (−36.42%). The airport loses more taxis; Bayfront loses a larger fraction.

**Decision implication:** Use taxi counts to size a staging trial and percentages to judge local severity. The two rankings answer different planning questions.

**Method:** Rank the absolute heavy-rain gap. **Source:** `rain_hit_top30_absolute.csv`.

**Next question:** When should a response start, and how long does the gap remain?

## 5. The deepest average gap is in the first hour.

Availability is 5.3% lower at onset and 5.6% lower 30 minutes later. The estimate narrows to −1.3% at +120 minutes; from +150 minutes, all later intervals include zero.

**Decision implication:** The deepest average gap comes early. Waiting until after rain starts leaves little time for a driver to reposition.

**Method:** Align many local rain onsets. **Source:** `effects_event_study.csv`.

**Next question:** Is there any useful signal before local rain begins?

## 6. Supply is already lower before local rain arrives.

Rain >2.5 mm/h 2–5 km away is associated with 7.3% fewer vacant taxis in a still-dry cell. An issued thundery forecast corresponds to −5.1%, or −3.7% with neighbouring rain controlled.

**Decision implication:** Nearby rain and issued forecasts are plausible early signals. Their predictive value still needs a direct with/without-weather test.

**Method:** Test nearby rain and forecasts while the cell stays dry. **Source:** `effects_approach.csv · effects_forecast.csv`.

**Next question:** Does the response depend more on intensity, spell length, or time since rain?

## 7. The supply gap is larger during long heavy-rain spells.

The intensity curve reaches −9.7% at only 1 mm/h. Heavy spells deepen from −11.4% in the first half-hour to −18.0% beyond two hours. The saved 30–60-minute after-rain bin is −5.3%.

**Decision implication:** Rain planning needs spell length as well as intensity. An extreme-intensity trigger alone would miss gaps already present in lighter rain.

**Method:** Separate intensity and spell-duration models. **Source:** `dose_spline_curve.csv · dose_duration_hangover.csv`.

**Next question:** When rain covers the island, can another area reliably supply spare taxis?

## 8. Island-wide rain leaves few clear gainers to draw taxis from.

329 of 374 cells have clearly fewer vacant taxis; only 3 clearly gain. Several eastern and northern cells gain citywide share while their actual taxi counts still fall.

**Decision implication:** A relative gainer is not automatically a donor area. A repositioning plan must check the current surplus before drawing taxis from it.

**Method:** Compare local shares during island-wide rain. **Source:** `spillover_islandwide_share.csv`.

**Next question:** Can a model identify the next low-supply cells accurately enough to act?

## 9. Taxi information improves alerts. Weather barely changes them.

At 30 minutes, 54.23% of LightGBM alerts are correct versus 47.18% for persistence. At 60 minutes: 51.95% versus 43.99%. Weather gives 54.20% and 51.88%.

**Decision implication:** The model improves alert ranking, but adding the tested weather inputs barely changes it. The next test checks whether a different target or scale changes that conclusion.

**Method:** Forecast the same targets with and without weather. **Source:** `forecast_eval_both_labels.csv`.

**Next question:** Is the small weather gain just a consequence of the 1 km target or its label?

## 10. Changing the grid and label still adds little forecast skill.

0 of 36 comparisons reaches the +0.0100 materiality bar. The largest gain is +0.0024; larger grids and the noise-aware label do not rescue the tested weather features.

**Decision implication:** The weak increment is not confined to one sparse-cell definition. Use the stronger taxi-information model while testing any new weather approach separately.

**Method:** Registered secondary tests across targets and scales. **Source:** `forecast_eval_both_labels.csv · S1, issue-time rows`.

**Next question:** Even with better ranking, how often do alerts arrive before a shortfall starts?

## 11. Most shortfalls still receive no advance warning.

Only 6.65% of runs receive advance warning at 30 minutes and 13.79% at 60. About 83% are never alerted under this workload.

**Decision implication:** Correct alerts are not enough: most shortfalls lack advance warning. This limits how much proactive repositioning the current system can support.

**Method:** Measure warning before each low-supply run. **Source:** `forecast_eval_lead_both_labels.csv`.

**Next question:** Could weather work better for regional shortfalls specifically during storms?

## 12. Regional storm forecasts show a small, unconfirmed weather gain.

October 2026 gives +0.0238, but only 2 storms versus 8 required. In 2019, 49 storms give +0.0087 [0.0008, 0.0171], below +0.02.

**Decision implication:** There is small positive regional weather information, but no adequately powered confirmation of a material gain. October’s promising point estimate is not confirmation.

**Method:** Test frozen regional models on separate holdouts. **Source:** `s22_materiality.csv · s22b_materiality.csv`.

**Next question:** Does weather help a different decision: planning the coming day at 09:00?

## 13. Weather helps daily planning in the flexible model.

The flexible model lowers deviance by 6.3% on the issue-time label and 10.1% retrospectively. The linear model is flat or worse: −4.5% on issue-time.

**Decision implication:** Weather helps the coarser daily-planning task in the flexible model. That supports testing advance staffing/staging schedules, rather than claiming better immediate cell alerts.

**Method:** Predict daily exposure using information available by 09:00. **Source:** `morning_forecast_value.csv`.

**Next question:** Which areas and time bands should a planning trial focus on?

## 14. The planning window depends on both place and time.

Changi: roughly 25–33 fewer taxis early in the day. Bukit Merah: roughly 21–25 fewer in evening/night periods. Central-area gaps have a different daily pattern.

**Decision implication:** A single island-wide incentive window would miss these differences. A planning trial should specify both an area and a time band.

**Method:** Aggregate forecast-conditioned gaps by place and time. **Source:** `planning_rain_losses.csv`.

**Next question:** How much targeting precision survives actual staging and supply constraints?

## 15. Operational constraints reduce targeting precision.

Unconstrained ranking reaches 51.47% precision. Eligibility/staging gives 48.05%; the risk-weighted allocation gives 44.16%, versus 31.01% for the original policy.

**Decision implication:** Use risk weighting for a staging pilot, with live donor checks and travel limits. Operational feasibility costs targeting precision; the final plan still needs an intervention trial.

**Method:** Evaluate an implementable constrained allocation. **Source:** `policy_diagnosis.csv`.

**Next question:** Recommendation: use live supply for dispatch and the morning forecast for a targeted planning trial.
