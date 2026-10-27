# Fifteen-minute presentation (decisions 174–176)

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
(speaker notes, next slide, elapsed timer), **A** appendix, **Escape** back to the talk. `present.html#4`
opens slide 4. References and appendix pages A1–A9 follow slide 14 and are outside the 14-slide count.
Motion respects `prefers-reduced-motion` (the title shows one static frame).

Design (decision 175): navy #0B1F3A, slate #2E4A6B, steel #4F7CAC, surfaces #F4F6F9/#FFFFFF, hairlines
#DDE3EA; yellow #F2B705 only for progress and the active step; red #B5473A only for fewer taxis and
map scales; 12-column grid with fixed title and footer positions. The title animation is illustrative:
synthetic noise-based rain cells and teal dots on real roads from `sim/v3/data.json`, a 20-second
seamless loop. The QR code (segno) is generated at build time and decoded with zxing-cpp before use.

Sources: `template.html` (slides and speaker notes), `present.css`, `present.js`. The story page
(`outputs/story/index.html`, `story/`) is not changed.

Presentation choices to know before presenting:
- Slide 4 headline reads "Heavy rain, fewer vacant taxis on the street" (association wording).
- The fleet chart joins only the two supplied years (2015, 2025).
- The event cursor covers the saved −60 to +180 minute range; no −2 h estimate exists.
- "53% vs 46%" is the mean of the saved 30- and 60-minute top-19 precision.
- The repositioning callout uses issue-time labels throughout: 44% vs 28%.
- Appendix A1–A9 draw saved tables only; snapshot coverage is 120,017 of 122,688 OK (97.8%), 118,136
  usable after glitch removal.
- Storm Builder has no URL preset; the speaker notes say to pick Monsoon surge, weekend, 1 pm by hand.
- Wang (2024) and Sun et al. (2020) need full references from the team.

## Decision 176: projector pass

Charts are rendered at their display size and shown 1:1 with a 24 px floor on chart text (20 px inside
numbered markers). Slides use 68 px titles, 56 px key numbers, 30 px body text and 20 px footers; the
browser check reports the smallest font per page (20 px everywhere, map attribution excluded). Chart
slides 4–8 carry a METHOD box and "What it shows" points; slide 6 adds a numbered 1 km map. The title
animation runs on a 40-second loop. Appendix pages: A1, A2, A3a/b, A4, A5a/b, A6a/b, A7, A8, A9.
