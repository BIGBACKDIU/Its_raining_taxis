# Complete project presentation

`Its_Raining_Taxis_complete.pptx` follows the supplied 23-slide reference's navy layout,
Anton headings and Poppins body text. The supplied reference file is unchanged.

- Slides 1–24: the project presentation, including the eleven selected charts and the key caveats.
- Slide 25: appendix divider.
- Slides 26–92: all 44 unique saved analysis graphs, split into 97 data panels across 67 appendix
  slides. Crowded named maps receive a slide per map. Blank subplot slots are omitted.
- `all_project_charts.zip`: all appendix and selected chart PNGs, plus fonts and licences.
- `graph_coverage.json`: exact figure, panel and slide mapping, with hashes of frozen inputs.
- `../figures/deck/all/`: 67 slide-card PNGs, 2220 × 856 px (2× a 1110 × 428 px card).
  These supplement the original eleven PNGs; multipart graphs have several files.

## Evidence and editing

This is a presentation export, not a new analysis. There is no estimation, tuning, bootstrap,
model scoring or new holdout-data access. Saved SVG data paths and confidence intervals retain
their geometry. Numeric text retains the saved values and rounding. The complete planning heatmap
uses the existing table's fifteen areas and five bands, with signed values and a sequential blue scale.
Percentage-count maps use cell-ID joins to saved tables, with a common red/white/blue scale capped
at ±40%. Maps of minutes, counts, residents and risk retain their own units.

Slide text, chart paths, markers and the planning heatmap are editable PowerPoint objects.
They are **not Office chart objects with embedded workbooks**. Some original colour-scale rasters
and the reference's simulator screenshot remain images. The appendix retains diagnostic and null
results, and explicitly labels the failed minute-flow design and illustrative simulations.

The reference's content is checked against saved results. Corrections include issue-time forecast
precision; the absolute-versus-share distinction in named places; the simulator v2/v1 pass counts;
and October 2026's **two** storm onsets. The earlier eleven-chart export incorrectly annotated
October as one onset; the chart and accompanying CSV are corrected without changing any estimate.
The small 2019 gain, failed power rule in October, and repeated test scoring remain visible.
Policy selection precision is 44.2% for risk-weighted selected cells versus 27.7% among all candidate
cells (issue-time label); the groups have different sizes, so this is not a fixed-workload comparison.
Operational recommendations are candidates for a trial, not measured benefits.

## Rebuild

Run from the repository root. The reference is needed only for rebuilding, not for opening the deck.
The build uses the presentation skill's `@oai/artifact-tool` runtime and bundled dependencies.

```sh
.venv/bin/python -m analysis.deck_charts
.venv/bin/python -m analysis.presentation_graphics
RUNTIME_NODE_MODULES=/path/to/runtime/node_modules node analysis/build_complete_deck.mjs "/path/to/It's Raining Taxis.pptx"
.venv/bin/python -m analysis.presentation_graphics --export-panels
```

The default reference path is the user-supplied file in Downloads. Intermediate renders and validation
receipts stay in ignored `.deck-build/`. The finalizer deliberately refuses to overwrite an existing
final deck or receipt: move the previous generated output and receipt aside before rebuilding.

Poppins and Anton TTFs and OFL licences are bundled under `assets/fonts/`. Registration is explicit
and font validation fails on fallback. Install those fonts for consistent editing on another machine.
The export was rendered and visually inspected; it was not inspected in the PowerPoint application.
