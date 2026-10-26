# Deck chart exports

Presentation only. Rebuild from the repository root:

```sh
.venv/bin/python -m analysis.deck_charts
```

Every PNG is exactly twice the requested display width and height, at 200 dpi. The background is
`#FBFCFE`. All text uses the bundled Poppins fonts; the renderer rejects fallback fonts and missing
glyphs. Axis and tick text is at least 22 px at display size; direct value labels are 24 px. Small
geographic identifiers and explanatory notes are intentionally smaller. There are no chart titles or
source lines; panel/series/axis labels and interpretation notes remain. No Anton callouts are used.

## Files and provenance

| PNG | Display px | Saved results |
| --- | --- | --- |
| deck_effects_main.png | 1016 × 490 | effects_main.csv; absolute and share, light/moderate/heavy |
| deck_radar_check.png | 1146 × 440 | radar_effects.csv and radar_central.csv; primary dry=0 definition; absolute models |
| deck_storm_peak.png | 1560 × 516 | saved panel30_2023.parquet, 20 Jul 2023 09:30; see exception below |
| deck_event_timeline.png | 1040 × 536 | effects_event_study.csv, absolute; effects_approach.csv, ring_heavier_owndry |
| deck_dose.png | 1016 × 375 | dose_spline_curve.csv and dose_duration_hangover.csv; intensity/after-rain absolute and share; heavy absolute duration |
| deck_where_map.png | 1520 × 547 | rain_hit_absolute_all.csv and rain_hit_share_all.csv; relevant expected>=4 and q<0.10 filters |
| deck_places_bar.png | 1010 × 552 | first 12 rows of rain_hit_top30_absolute.csv |
| deck_islandwide_map.png | 889 × 552 | spillover_islandwide_share.csv |
| deck_planning_heatmap.png | 772 × 560 | planning_rain_losses.csv; issued NEA rain forecast, weekdays; top 10 areas by largest band gap |
| deck_forecast_bars.png | 1300 × 487 | forecast_eval_both_labels.csv; primary 1 km, issue-time label, all times, K=19 |
| deck_holdout_gain.png | 1100 × 420 | forecast_eval_both_labels.csv, s22_materiality.csv, s22b_materiality.csv |

`data/` contains the exact plotted inputs (not refitted estimates), exported with round-trip numeric
precision. `audit.json` records every source hash, registered font hash, rendered font, PNG hash and
pixel dimension. Source hashes are checked again at the end of rendering. Original tables and figures
are not overwritten. Snapshot rows are the only panel access; no model or held-out outcome is scored.

## Interpretation and display choices

- **Snapshot exception:** there is no existing storm-snapshot result CSV. The script reads only the
  frozen 374-row snapshot, then reproduces the original `02_describe.py` formula:
  `100 * (vacant / max(1, baseline) - 1)`. Exact counts, saved baseline, rain and calculated percentages
  are exported in `data/deck_storm_peak.csv`. The rain scale saturates at 60 mm/h, labelled `≥60`.
  The snapshot percentages are descriptive ratios; the other effect maps show model estimates.
- All change maps use the same ±40% red/white/blue scale (red fewer, blue more, white zero).
  A share change is a change in relative citywide share, not necessarily in absolute taxi counts.
  Land is pale grey-blue; non-analysed/masked cells use the specified no-data colour.
- Heavy-rain named maps show only presentable cells (expected>=4 and relevant q<0.10). The absolute
  top ten rank by taxis lost; the share top ten rank by most negative share change. Numbers may be
  displaced slightly with leader lines to avoid marker overlap. Count labels are signed **absolute**
  taxi changes per heavy-rain half-hour, including beside share percentages.
- Island-wide fills show all saved share estimates, including uncertain changes; uncertainty is not
  replaced with zero. The **three marked absolute gainers** are Senoko West (+0.880 taxis), cell 48018
  (+0.083) and cell 49023 (+0.083). The last two fail the naming filter and remain unnamed. There are
  more than three share gainers. The supplied colour-bar wording is retained; the list labels the
  percentages explicitly as share changes.
- Event study is relative to −30 minutes. “Back within noise” starts at +150 minutes, when this and
  every later CI includes zero; this does not establish full recovery. The requested approach callout
  rounds the separate ring-model estimate −7.3384034% to −7%; it is not an event-study observation.
- The duration panel uses heavy-rain absolute contrasts, while intensity and after-rain panels show
  both absolute and share estimates. After-rain bins are plotted at bin start +15 minutes, matching
  the original figure (the 180–360 bin is not plotted at its midpoint). The reference is dry for >=6 h.
- Places: red denotes the requested CBD/fringe group (Downtown Core, Museum, Rochor, Outram,
  Lavender/Kallang). Changi and Woodlands are navy. Values are saved-table values rounded to one
  decimal; for example the first bar is 7.1 of 83.4 (−8.5%), from 7.08 / 83.37 / −8.50%.
- Planning: area order follows the original maximum-gap rule. Negative gaps mean **more** taxis than
  expected; their signed numbers remain visible, while sequential colour floors at zero. Text never
  replaces a negative gap with a positive deficit. Only a rounded negative zero is printed as 0.0.
- Forecast bars: regression means the saved GLM without weather; LightGBM variants share the same
  issue-time-label evaluation. Labels are precision percentages in the 19 alerted cells, not recall.
- Holdout plot: 1 km “max” is the descriptive maximum over every saved 1 km combination, including
  S1: NB issue-time label, 30 minutes, all times (+0.00240; CI +0.00164 to +0.00288). October 2026 is
  +0.023765 (CI +0.012303 to +0.078655), but its single onset fails the eight-onset power rule;
  the result remains descriptive. 2019 is +0.008747 (CI +0.000807 to +0.017070), below +0.02.
  The exact source precision is retained in the accompanying CSV; displayed gains round to four decimals.

Fonts: [Google Fonts Poppins](https://github.com/google/fonts/tree/main/ofl/poppins), SIL OFL 1.1.
Font files and unmodified licence are in `assets/fonts/poppins/`. No new estimation or test-year use.
