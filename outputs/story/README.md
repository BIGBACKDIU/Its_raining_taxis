# It's Raining Taxis — HTML research story

Open `index.html` in a modern browser. The page is self-contained: fonts, chart data and all appendix images are embedded. No server, internet connection or install is required to read it. External links to the repository and Storm Builder require internet access.

## Reading and presenting

- The main story has **15 graphs**: rain bands, radar comparison, event timing, intensity, duration, named rain map, count-loss ranking, paired storm maps, island-wide redistribution, planning heatmap, place characteristics, alert precision, holdout weather gains, morning planning value, and simulation realism.
- Scroll or use the chapter links. The map switches between absolute and citywide-share associations. Hover, tap or focus a coloured square for its counts and uncertainty.
- Forecast controls switch between 30 and 60 minutes. Morning controls switch between the existing day-block and seven-day-block intervals.
- Choose **Present**, then use left/right arrows to move between the 15 main figures. Escape exits presentation mode. Use the browser's own fullscreen command if desired.
- The searchable evidence appendix retains **all 44 saved source figures**, covering **97 data panels** across **67 readable panel groups**. Open a card and use Previous/Next or arrow keys. Escape closes the viewer.
- Expand methods for definitions, source filenames and embedded numeric tables. Chart labels use rounding; tooltips and tables give more precision.

## Rebuild and provenance

From the repository root:

```sh
.venv/bin/python -m analysis.build_story
```

Editable sources are `story/template.html`, `story/story.css` and `story/story.js`. The builder reads existing CSVs and the already exported storm snapshot, and embeds the previously rendered appendix cards. `provenance.json` records SHA-256 hashes, graph counts and final HTML size. The builder checks naming thresholds, unique cell joins, figure coverage and unchanged input hashes. It performs no estimation, tuning, bootstrap, model scoring or holdout-data access.

The navy design uses embedded Poppins and Anton fonts from `assets/fonts/` under the SIL Open Font License. Map changes share a red/white/blue scale capped at ±40%; rain uses a separate sequential blue scale. Signed planning values are retained, including gains. Expected counts accompany named percentages.

Important disclosures remain visible: associations describe supply; absolute and share models differ; October 2026 has two onsets and fails the power rule; the 1 km maximum is descriptive selection; the morning result follows a corrective refit and second scoring; simulation fails its unchanged realism rule; minute flows do not identify a mechanism.

Browser checks cover 1440 px desktop and 400 px phone layouts, SVG label bounds, map and horizon controls, saved interval switches, all 44 gallery entries, multi-panel navigation and presentation mode. Preview JPGs are visual records, not result figures.
