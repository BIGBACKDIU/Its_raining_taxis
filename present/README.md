# Fifteen-minute presentation (decision 174)

`outputs/story/present.html` is a single offline file (fonts, data and charts embedded; only the two
live demos need internet). Presentation only: every number is read from saved tables at build time
(checked by `analysis/build_present.py`) or was supplied by the team (LTA 2015/2025 fleet counts,
The Straits Times fleet note, references). No estimation, labels or scoring.

```sh
.venv/bin/python -m analysis.present_charts   # deck_factors + presentation-palette charts
.venv/bin/python -m analysis.build_present    # outputs/story/present.html
node analysis/check_present.cjs               # screenshots + checks in outputs/story/present_previews/
```

Keys: ← → / Space / Page Up/Down move, Home/End jump, **F** full screen, **S** presenter panel
(speaker notes, next slide, elapsed timer). `present.html#4` opens slide 4. The references slide
follows slide 14 and is outside the 14-slide count. Motion respects `prefers-reduced-motion`.

Sources: `template.html` (slides and speaker notes), `present.css`, `present.js`. The story page
(`outputs/story/index.html`, `story/`) is not changed.

Presentation choices to know before presenting:
- Slide 4 headline reads "Heavy rain, fewer vacant taxis on the street" (association wording).
- The fleet chart joins only the two supplied years (2015, 2025).
- The event cursor covers the saved −60 to +180 minute range; no −2 h estimate exists.
- "53% vs 46%" is the mean of the saved 30- and 60-minute top-19 precision.
- The repositioning callout uses issue-time labels throughout: 44% vs 28%.
- Storm Builder has no URL preset; the speaker notes say to pick Monsoon surge, weekend, 1 pm by hand.
- Wang (2024) and Sun et al. (2020) need full references from the team.
