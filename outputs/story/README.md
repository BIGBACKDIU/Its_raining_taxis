# It's Raining Taxis — interactive research presentation

Open `index.html` in a browser, or serve the repository and visit `/outputs/story/index.html`.
The page embeds its fonts, saved chart values and appendix images. Only the optional live Storm
Builder needs an internet connection.

## Story and controls

The presentation has **26 scenes and 15 main figures**. It follows the client question, data and
methods, rain magnitude/geography/timing, forecast accuracy and advance warning, daily planning,
and constrained targeting. Graph 15 closes with the operational allocation trade-off. Radar and
simulator diagnostics stay in the appendix; the live app is an optional demonstration. Every main
figure has visible **Method / Result / Practical meaning** notes. The complete **44-figure appendix**
retains 97 data panels in 67 readable groups, with explanations in its viewer.

Choose **Present** for a consistent, full-window slide canvas. Every scene uses the same dimensions;
there is no large website header, floating slide card or internal scrolling. Next/back, left/right
arrows, Page Up/Down and Home/End advance slides. Escape or **Exit** returns to reading mode.
The portrait layout uses the same canvas for every scene on a phone.

On slide entry, the storm replay and event cursor play automatically. The intensity plot highlights its saved 1 mm/h estimate. The spatial slide shows the absolute
map and pooled centre/rush comparisons. Both forecast horizons appear together, allowing a direct
comparison without clicking or waiting for numbers to change. Slides themselves advance at the presenter's pace. A compact **Pause**
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

Editable sources are `story/template.html`, `story/story.css`, `story/story.js`, `story/motion.js`, `story/presentation.css`, `story/editorial.css`, `story/storyline.json`
and `story/evidence_notes.json`. The builder reads saved CSVs and presentation exports, embeds
fonts and images, and verifies input hashes. `provenance.json` records hashes, graph/scene counts
and final HTML size. It performs no estimation, tuning, bootstrap, model scoring or holdout access.
The storm export can be recreated with `python -m analysis.export_story_playback` from the
existing local fit-period panel; its saved peak is checked against the original peak CSV.

The design uses a pale blue background and frosted white cards, with embedded Poppins and Anton
fonts under the SIL Open Font License. Maps retain the common ±40% red/white/blue scale. Named
places retain expected counts and the expected-count/q-value presentation filter.

The cover contains the research question rather than a graph count or disclaimer slogans. Each
main graph has a quantitative analysis, decision implication, concise method and a question leading
to the next piece of evidence. `EDITORIAL_NOTES.md` records the selection and the source for each
claim. Storm-day totals are arithmetic over the existing presentation export, not a new model.

Browser checks cover desktop 1440 px and phone 400 px, all scenes, graph explanations, fonts,
chart controls, appendix navigation, unique IDs after leaving Present, and the live embed's
automatic playback, pause/resume and unloading. JPG previews are presentation QA records.
