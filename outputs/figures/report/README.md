# Report figures

PNG and SVG; numbered in suggested report order. Sources and notes are printed under each chart.

 1. `fig01_feed_regimes` - The taxi feed's coverage changes between regimes; every model allows for this.
 2. `fig02_desc_profile_rain_bands` - Vacant taxis relative to the expected level by time of day, dry vs rain bands.
 3. `fig03_desc_maps_dry_heavy` - Vacant taxis per 1 km cell, dry vs heavy rain, and % change vs expected.
 4. `fig04_effects_main` - Main rain associations: absolute, share and offset models (95% CI by day).
 5. `fig05_effects_event_study` - Vacant taxis around rain onset in a cell (event study).
 6. `fig06_effects_approach_forecast` - Vacant taxis thin before rain arrives: rain 2-5 km away and NEA forecasts.
 7. `fig07_effects_robustness` - The heavy-rain association across robustness checks.
 8. `fig08_inference_hotspots` - Cells with significantly fewer vacant taxis in heavy rain (BH FDR 10%).
 9. `fig09_risk_vulnerability` - Where heavy rain most raises the chance of unusually low availability.
10. `fig10_forecast_topk_both_labels` - Early warning at a fixed workload, retrospective and issue-time labels.
11. `fig11_s1_weather_gain` - Weather's added skill across 36 scale x horizon x label comparisons (none material).
12. `fig12_planning_forecast_rain` - Planning view: availability under an NEA rain forecast by area and hour.
13. `fig13_policy_diagnosis` - Repositioning plan vs forecast ranking: what the constraints cost in targeting.
14. `fig14_sim_heldout_storms` - Step-8 simulation vs observed on held-out storms (after the conservation fix; does not pass).
15. `fig15_names_rain_hit_map` - Named places where heavy rain goes with the most taxis lost and the largest share losses.
16. `fig16_minutes_to_taxi_maps` - Drive minutes to the nearest vacant taxi, dry, and the extra in heavy rain, by place.
17. `fig17_dry_supply_by_band` - Dry-weather vacant-taxi supply by time band, best-supplied places named.
18. `fig18_taxi_deserts_map` - Dry-weather taxi deserts: residential areas with the fewest dry-weather vacant taxis per resident.
19. `fig19_factors_contrasts` - Why: heavy-rain effect by place type (Central Area, MRT, taxi stand, mall) in the panel model.
20. `fig20_factors_shap` - Which characteristics separate places that lose more (random forest; weak out-of-area fit).
21. `fig21_dose_intensity_hangover` - Intensity-response curve and the after-rain shortfall.
22. `fig22_mrt_did_event_study` - New MRT stations: dry-weather supply nearby before and after opening (pre-trends fail).
23. `fig23_fleet_trend` - Monthly heavy-rain effect against the LTA fleet size.
24. `fig24_stands_predicted_sensitivity` - Predicted heavy-rain sensitivity for every land cell (planning map).
25. `fig25_spillover_islandwide_map` - Island-wide rain: share of vacant taxis by place (almost every cell still loses taxis).
26. `fig26_sim2_diagnosis` - Why the step-8 simulation fails its plausibility check: level, timing, spatial pattern.
27. `fig27_sim2_heldout_storms` - Simulation v2 vs observed on held-out storms (illustration only; does not pass).
