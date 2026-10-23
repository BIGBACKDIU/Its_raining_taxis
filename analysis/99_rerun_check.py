"""Final check: rerun the core pipeline from the raw files with fixed seeds and compare key numbers with the
committed outputs (HANDOFF section 7).

Reruns, in order: prep_feed_regimes, 00_audit, 01_panel (30-minute panel), 03_effects (main models, event study,
by regime) and 04_inference. Not rerun here (documented in outputs/decisions.md): the downloads (raw data are
fixed in git), the 15-minute and 500 m robustness panels, 03_effects_more, 05_risk, steps 6-8 (rerunning the
forecasting steps would score the test year again), and the simulation.

Output: outputs/rerun_check.csv (key quantity, committed value, rerun value, absolute difference).
Usage: .venv/bin/python -m analysis.99_rerun_check
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pandas as pd

from analysis.common import TABLES

STEPS = [["-m", "analysis.prep_feed_regimes"], ["-m", "analysis.00_audit"], ["-m", "analysis.01_panel"],
         ["-m", "analysis.03_effects"], ["-m", "analysis.04_inference"]]


def snapshot():
    v = {}
    reg = pd.read_csv(TABLES / "feed_regimes.csv")
    v["regimes (non-spell)"] = int(reg[reg.kind == "regime"].regime.nunique())
    v["spell days"] = int(reg[reg.kind == "spell"].n_days.sum())
    a = json.loads((TABLES / "audit_summary.json").read_text())
    for k in ("snapshots_usable", "dropped_glitch_spike", "dropped_glitch_dip", "unusual_feed_outage", "days_excluded_main"):
        v[f"audit: {k}"] = a[k]
    pc = pd.read_csv(TABLES / "panel_checks_30.csv")
    v["panel rows (all years)"] = int(pc.rows.sum())
    v["panel duplicate keys"] = int(pc.duplicate_keys.sum())
    m = pd.read_csv(TABLES / "effects_main.csv", index_col=0)
    for mod in ("abs", "share", "offset"):
        for b in ("light", "moderate", "heavy"):
            v[f"effect {mod} {b} (%)"] = round(float(m[m.model == mod].loc[b, "pct"]), 4)
    es = pd.read_csv(TABLES / "effects_event_study.csv")
    v["event study abs +30 min (%)"] = round(float(es[(es.model == "event_abs") & (es.event_min == 30)].pct.iloc[0]), 4)
    r = pd.read_csv(TABLES / "inference_ratio_statistic.csv").set_index("band")
    v["ratio statistic heavy (%)"] = round(float(r.loc["heavy", "pct"]), 4)
    h = pd.read_csv(TABLES / "inference_hotspots.csv")
    v["hotspot cells significantly lower"] = int((h.hotspot == "significantly lower").sum())
    return v


def main():
    before = snapshot()
    times = {}
    for s in STEPS:
        t0 = time.time()
        res = subprocess.run([sys.executable] + s, capture_output=True, text=True)
        times[s[-1]] = round(time.time() - t0)
        if res.returncode != 0:
            print(res.stderr[-2000:])
            raise SystemExit(f"step failed: {s}")
        print(s[-1], "done", times[s[-1]], "s", flush=True)
    after = snapshot()
    rows = [{"quantity": k, "committed": before[k], "rerun": after[k],
             "abs_diff": abs(float(after[k]) - float(before[k]))} for k in before]
    t = pd.DataFrame(rows)
    t["identical"] = t.abs_diff < 1e-6
    t.to_csv("outputs/rerun_check.csv", index=False)
    print(t.to_string(index=False))
    print("step seconds:", times)


if __name__ == "__main__":
    main()
