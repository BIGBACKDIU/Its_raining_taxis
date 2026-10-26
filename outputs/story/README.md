# It's Raining Taxis — interactive research presentation

Open `index.html` in a browser, or serve the repository and visit `/outputs/story/index.html`.
The page embeds its fonts, saved chart values and appendix images. Only the optional live Storm
Builder needs an internet connection.

## Story and controls

The presentation has **26 scenes and 15 main figures**. It follows the client question, data and
methods, rain associations, geography, forecast accuracy and advance warning, daily planning,
constrained targeting, measurement checks, simulation limits, and recommendations. Every main
figure has visible **Method / Result / Practical meaning** notes. The complete **44-figure appendix**
retains 97 data panels in 67 readable groups, with explanations in its viewer.

Choose **Present**, then use next/back, left/right arrows, Page Up/Down, Home/End or chart replay.
Escape returns to the scrolling view. On phones, tall scenes scroll while navigation remains visible.
Motion can be disabled and respects the system reduced-motion preference.

The storm player shows **15 observed half-hour snapshots**, 06:30–13:30 Singapore time on
20 July 2023. Play, pause, scrub or jump to the saved 09:30 peak. Colour fades create no intermediate
observations. The event player and intensity slider use only saved model estimates and intervals.
Map controls change absolute/share measures; forecast controls change horizon; morning controls
select saved day/seven-day intervals. Tooltips and expandable tables retain exact values.

The live demonstration embeds `https://storm-builder-sg.vercel.app/`. Select **Load Storm Builder**.
Its presentation scene uses almost the whole window, with compact controls. **Expand view** fills
the window further; **Back to presentation** restores the slide without restarting the scenario.
Leaving the demonstration slide unloads the app. The simulation remains an illustration: its
unchanged realism rule fails. Opening the app separately is also supported.

## Rebuild and provenance

```sh
.venv/bin/python -m analysis.build_story
```

Editable sources are `story/template.html`, `story/story.css`, `story/story.js`, `story/motion.js`
and `story/evidence_notes.json`. The builder reads saved CSVs and presentation exports, embeds
fonts and images, and verifies input hashes. `provenance.json` records hashes, graph/scene counts
and final HTML size. It performs no estimation, tuning, bootstrap, model scoring or holdout access.
The storm export can be recreated with `python -m analysis.export_story_playback` from the
existing local fit-period panel; its saved peak is checked against the original peak CSV.

The design uses a pale blue background and frosted white cards, with embedded Poppins and Anton
fonts under the SIL Open Font License. Maps retain the common ±40% red/white/blue scale. Named
places retain expected counts and the expected-count/q-value presentation filter.

Visible limitations include supply/association scope, distinct absolute/share models, weak advance
warning despite alert precision, differing policy group sizes, the selected 1 km maximum, October's
two-onset power failure, the corrected morning analysis's repeated scoring, count-interval
undercoverage, failed simulation realism and unidentifiable minute-flow mechanisms.

Browser checks cover desktop 1440 px and phone 400 px, all scenes, graph explanations, fonts,
chart controls, appendix navigation, unique IDs after leaving Present, and the live embed's
expansion, state preservation and unloading. JPG previews are presentation QA records.
