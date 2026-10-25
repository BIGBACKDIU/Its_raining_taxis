# Storm Builder

Live site: **https://storm-builder-sg.vercel.app** (Vercel project `storm-builder-sg`). The project is connected to this
GitHub repository with root directory `sim/v3` and no build step, so every push to `main` redeploys the site.
`.vercelignore` keeps `template.html` and local env files out of the deploy.

Open `index.html` directly in a browser, or paste that **single file** into an HTML artifact.
It contains every script, style, baseline and road coordinate. There are no external requests, images,
fonts, storage requirements or dependencies. The other files here are editable build sources.

This is a presentation of the frozen v2 scenario model, **not a forecast or a validated operating tool**.
At the user's request there is no top banner; the city card says "simulated scenario" and the help text records the failed realism check. `sim/index.html` and `sim/v2/index.html` are unchanged.

## Rebuild

From the repository root:

```sh
.venv/bin/python analysis/build_storm_builder.py
node analysis/check_storm_builder.cjs
.venv/bin/python -m pytest tests -q
.venv/bin/python analysis/99_wording_check.py
```

The browser checker uses Playwright and a local Chromium/Chrome executable. Set `CHROMIUM_PATH` if needed.
On this workspace it can use the bundled Playwright package and system Google Chrome.
The build needs the ignored local step-11 GraphML and the frozen panel Parquets.

`analysis/check_storm_builder_parity.py` repeats the existing three 50-seed Python/JavaScript parity cases
into a **new** CSV. It logs the use of held-out storm inputs and preserves the frozen parity table.
It is a compatibility check, not observed-outcome scoring or retuning.

## What remains fixed

- The integer edge-flow allocator, RNG, arrivals, tuned parameter rows, drive-time matrix, request/destination
  weights, rain response and plausibility rule are unchanged.
- Optional observers in `sim/v2/engine_v2.js` consume no model randomness. The hook test compares every
  minute and the final scheduled-arrival arrays, with hooks on/off. A separate comparison against the
  original engine at commit `1819163` also matches exactly in all 12 fixed-seed cases.
- Observer metadata adds the actual allocated taxi cell and pickup time. Extra stock-adjustment and
  arrival/duty metadata let the animation preserve every per-cell vacant count, including normal baseline
  changes and the initially occupied taxis' later returns.
- Visual random walks use a separate seeded RNG. All pickup, trip and reposition paths are time-scaled
  to the engine's existing timestamps. Geometry does not update the engine's drive times.

## Presentation inputs and simplifications

Only 96 typical weekday/weekend half-hour profiles are exported from saved step-5 predictions in the
April 2022–March 2025 fit period. The export removes the saved regime multiplier, averages months and
weekdays/weekends equally, and restores the median normal-regime multiplier (1.0010005001667084).
No baseline or model is refitted. Initial counts round those expected levels to integers. The policy
share is the unchanged 0.6355 from the first frozen v2 storm input; there is no new date-specific fleet assumption.

Synthetic rain averages six five-minute midpoint samples per engine half-hour. The radar layer shows
smooth movement and ramp/decay; it is an illustration of those synthetic slots. The original engine
response still saturates above 30 mm/h even when the displayed field peaks at 60 mm/h.
The four-hour replay includes engine minutes 0–240, with an initial state before minute zero.
Playback 1× means one simulated minute per second.

Major roads and their links are retained from the local OSM drive GraphML. Mixed-class merged edges
containing any excluded road type are omitted. The largest **strongly** connected component preserves
one-way directions and allows routes between all snapped cell nodes. Geometry uses Douglas–Peucker
simplification at 15 m and integer metre coordinates in `pipeline/grid.py`'s projection.
Point-to-point routes use cached directed A* with distance costs and an admissible Euclidean heuristic.
Missing paths fall back to a straight line and increment a diagnostic counter; the tested scenarios have none.

Vacant taxis take short directed random walks near their cell's snapped node. Local return routes are
bounded rather than taking long expressway detours. Where no short directed loop exists, taxis wait
at their node until the engine moves them. This affects drawing only. Pickup approaches follow the
remaining cruise road, then the origin-node/request-node shortest path; occupied journeys start at
the request node. Individual identities and journeys are illustrative, not reconstructed vehicles.
Phones omit trails and quantise cruise motion; reduced motion freezes cruising, removes trails and
slows request pulses. If an artifact sandbox blocks workers, preparation falls back to the main thread;
playback still uses the same prepared data.

## Checks and outputs

- `outputs/tables/storm_builder_build.json`: node/edge counts, exact road/HTML bytes, source hash and baseline provenance.
- `storm_builder_cell_nodes.csv`: explicit cell ID to road node mapping and snap distances.
- `storm_builder_browser_check.json`: observed frame rates, exact counter agreement, cruise radius,
  road fallbacks, reduced motion, blocked-worker fallback, layout and console/network checks.
- `storm_builder_parity.csv`: all three existing parity cases pass the unchanged 5% rule.
- `outputs/figures/storm_builder_*.png`: 1440 px and 400 px views before and during the storm;
  additional phone controls and comparison views.

Road data © OpenStreetMap contributors, ODbL. Attribution remains visible in each map corner.
The embedded road database is derived from the local step-11 OpenStreetMap graph.

## Scenario brief and visual style

The navy interface uses muted blue, amber and lilac markers without glow. The scenario brief updates
from the prepared storm's settings after every build, and when repositioning or comparison is switched.
It explains the selected mechanism, the existing 25% wet-area travel multiplier, non-default request
levels and the existing 30 mm/h response cap. These are model assumptions, not estimated real-world
effects. The counter note distinguishes running totals from current stocks. Presentation text and
colours do not change the engine, its random stream, parameters, rain slots or numeric results.

## City-builder look

The page is a full-screen light city view with frosted ("liquid glass") floating panels, in the spirit of a
city-building game (own design; no game names, logos or assets). The base map adds URA Master Plan 2019 land use
(urban, industry, green space, beaches, water bodies; dissolved and simplified at 18 m by the build script),
shallow coastal water and seeded canopy texture. Rain is drawn as a radar-style field: seeded value noise inside
the synthetic storm footprint, coloured light blue to red by display intensity. All of this changes the drawing
only; the engine, rain slots and counters are unchanged.
