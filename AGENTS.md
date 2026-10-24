# AGENTS.md - instructions for any coding agent (Codex, Claude Code, others)

1. Read `HANDOFF.md` in full before doing anything. It is the single source of truth: plan, data layout,
   definitions, steps 0-20 and the rules in its section 2.
2. Then read, in this order: `outputs/summary.md` (current results), `outputs/decisions.md` (every choice,
   numbered 1-138+), the end of `outputs/phase2_progress.md` (review fixes), `outputs/test_scoring_log.csv`.

## Status (25 Oct 2026)

- Analysis steps 0-8 and 10-20 are done and **frozen** after three independent reviews (last fixes in commits
  041c538, c47ccd6, 43e96ab). Do not change frozen results, registered rules, thresholds or the simulation
  plausibility rule. Step 9 waits for LTA trip data.
- Any new work is a **new, clearly labelled analysis**: register its specification in `outputs/decisions.md`
  (next free number) and commit that BEFORE running it; append a plain-English result to
  `outputs/phase2_progress.md`; never retune or re-score frozen models.
- The test year (Oct 2025 - Sep 2026) has been used many times; any further use must be logged in
  `outputs/test_scoring_log.csv` with the reason. Data after Sep 2026 has never been used.

## Rules that are easy to break

- Vacant taxis are supply, not demand. No claims about unmet demand, waiting times, lost riders or revenue.
- Rain results are associations, not causes.
- Rain must come before the taxi count it explains; forecasts only as issued; no look-ahead anywhere.
- Named places in presented lists need >= 4 expected vacant taxis and q < 0.10 (decision 133).
- Always report absolute counts next to percentages.
- Run `python analysis/99_wording_check.py` and `python -m pytest tests -q` before every commit.

## Environment

- Work in the existing local clone on Matthew's Mac (the folder Claude Code used). Large derived files
  (panels, models, drive-time matrices, OSM extracts) are in `.gitignore` and exist only there; rebuilding them
  from raw takes hours (`analysis/prep_*.py`, `analysis/01_panel.py`, see HANDOFF section 3).
- Python virtualenv in `.venv/` (`requirements-analysis.txt`, exact versions in `outputs/requirements-lock.txt`).
  Fixed seed `SEED = 2702`.
- Commit small, descriptive commits to `main` and push. Never commit API keys; keys go in GitHub repo secrets.
- Finish every task with a short report: what changed, the key numbers, and anything that failed.
