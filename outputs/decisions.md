# Decisions log

Choices not fixed by HANDOFF.md, in the order they were made. Each entry says what was decided and why.

## Environment (22 Oct 2026)

- **Python 3.11.9 (python.org build) for `.venv`.** Homebrew Python 3.12 cannot create a virtualenv on this Mac
  (`pyexpat` fails with `Symbol not found: _XML_SetAllocTrackerActivationThreshold`). HANDOFF allows 3.11 or 3.12.
- Added `ruptures` (change-point detection) and `pypdf` (reading LTA fleet PDFs) to `requirements-analysis.txt`.

## Step B: data

1. **Retried every non-ok snapshot, not only the three listed gaps.** 2,671 snapshots (all `empty` or
   `bad_payload` statuses, including 118 in Jun 2024 and 61 in Feb 2025 that HANDOFF did not list) were requested
   once more. **None came back**: the API answers `{"message": "no results found"}` or an empty point list for
   these times, so the archive does not hold them. Raw files are untouched; the retry results are in
   `data/raw/taxi_retry/` (summary: `retry_summary.csv`).
2. **Coverage regimes** (`analysis/prep_feed_regimes.py`): daily index = median over the day's snapshots of
   log(count / median count for that half-hour-of-week). PELT with L2 cost, minimum segment 5 days,
   penalty 40 x sigma^2 x log(n) where sigma is the robust noise level from day-to-day differences. The usual
   BIC-type penalty (2-3 x) gave 60+ segments because the daily index is autocorrelated (weather, holidays).
   Neighbouring segments within 10% merge. Segments under 14 days are an *anomalous spell* (excluded) if they are
   at least 15% (log) away from both neighbours; otherwise they join the closer neighbour. A short segment that
   matches the regime on the far side of a spell gets that regime's label (14-23 Nov 2022 -> R06).
   Result: 18 regimes, 8 spells (41 days).
3. **Single unusual days are flagged, never dropped.** A day can fall 30% below its regime level because of a
   holiday or a storm. Dropping days on the outcome would bias the rain effects. They are kept and listed
   (`anomalous_day` in `data/interim/feed_daily.csv`). Step 0 checks them against rain and holidays.
4. **26 Feb - 7 Mar 2023 spell.** 2-6 Mar is a feed outage: flat ~490 taxis for five days, dry days included.
   26 Feb - 1 Mar overlaps the record rain of 28 Feb 2023 (146 mm per gauge on average). The feed is also
   unstable on those days (single snapshots drop to 23 taxis), so the rain and feed effects cannot be separated.
   It is excluded from main estimates and added back in a robustness check.
5. **No de-duplication of positions.** From Oct 2025 the feed contains exact duplicate coordinates
   (607 of 3,928 points at 03:00 on 15 Oct 2025, vs 6 of 1,537 on 16 Sep 2025). Merging points within 5 m only
   reduces the count to 2,629, still 1.8x September. So the jump is duplicates plus extra vehicles, and the
   panel stores cell counts, not positions. Handled with regime fixed effects and the share-of-citywide model,
   as HANDOFF says. Cell shares are stable across every boundary (correlation 0.91-1.00,
   `outputs/tables/feed_share_stability.csv`), which supports the share model.

## Step B: static data

6. **School holidays are hand-entered** from MOE calendars (2025-2026 checked against the MOE release of
   30 Jul 2025). Public holidays come from data.gov.sg (consolidated dataset).
7. **CDG fleet share = (Comfort + CityCab) / all taxis**, from LTA's monthly P2P statistics PDFs
   (`data/static/sources/`). It is 60-65% over the period. Sep 2026 is not yet published; Aug 2026 is used.
8. **Storm days for the simulation:** rank days by the peak island-mean rain over a 30-minute window between
   07:00 and 23:00 (working gauges only), skip excluded days, keep days at least 7 days apart. Take 20 from the
   fit period (Apr 2022 - Mar 2025) and 10 from the test year. Positions are saved from 3 h before to 4 h after
   the peak, not whole days, to keep the files small (13 MB in total). Five fit-period storms fall in the
   low-coverage regime R05 (Aug-Nov 2022); step 8 must scale or flag them.
