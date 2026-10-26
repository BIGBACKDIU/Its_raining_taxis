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

Choose **Present** for a consistent, full-window slide canvas. Every scene uses the same dimensions;
there is no large website header, floating slide card or internal scrolling. Next/back, left/right
arrows, Page Up/Down and Home/End advance slides. Escape or **Exit** returns to reading mode.
The portrait layout uses the same canvas for every scene on a phone.

On slide entry, the storm replay and event cursor play automatically. The intensity display steps
through saved points, the map alternates absolute/share views, and forecasting alternates 30/60
minutes with visible labels. Slides themselves advance at the presenter's pace. A compact **Pause**
control stops playback; **Resume** continues. Playback also stops when a slide or tab is left.
The system reduced-motion preference is respected; its static storm view uses the saved rain peak.

The storm player shows **15 observed half-hour snapshots**, 06:30–13:30 Singapore time on
20 July 2023. It pauses briefly at the saved 09:30 peak and the end before looping. Colour fades
create no intermediate observations. The event cursor and intensity display use only saved model
estimates and intervals. The morning slide shows the saved seven-day-block intervals. Reading
mode retains manual play, scrubbing, map, horizon and interval controls, tooltips and numeric tables.

The live demonstration embeds `https://storm-builder-sg.vercel.app/?presentation=1` and starts
on entry. Its animation runs at the existing 4× playback rate and loops without changing engine
inputs or results. The slide's Pause/Resume also controls the app; leaving the slide unloads it.
The simulation remains an illustration: its unchanged realism rule fails. Reading mode retains
**Load Storm Builder**, **Expand view** and opening separately.

## Rebuild and provenance

```sh
.venv/bin/python -m analysis.build_story
```

Editable sources are `story/template.html`, `story/story.css`, `story/story.js`, `story/motion.js`, `story/presentation.css`
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
automatic playback, pause/resume and unloading. JPG previews are presentation QA records.
