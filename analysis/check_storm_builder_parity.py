"""Re-run the existing v2 parity cases without overwriting frozen parity outputs."""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.common import SEED, log_test_scoring
from analysis.sim_engine_v2 import simulate


def main():
    old = importlib.import_module("analysis.20_sim_v2")
    s8 = importlib.import_module("analysis.08_simulation")
    world, storms, _ = old.load2()
    tuned = pd.read_csv(ROOT / "outputs/tables/sim2_tuning.csv")
    held = [s for s in storms if s["period"] == "test"]
    cases = [(tuned.iloc[0], held[0]), (tuned.iloc[len(tuned)//2], held[3]), (tuned.iloc[-1], held[7])]
    log_test_scoring("check_storm_builder_parity.py", "Presentation compatibility: repeat existing v2 Python/JS parity cases; held-out storm inputs only, no observed outcomes",
                     "Storm Builder presentation", note="50 seeds, same cases/rule; new storm_builder_parity.csv; no tuning or frozen output changes")
    rows = []
    for row, storm in cases:
        scen = dict(mechanism=row.mechanism, dest=row.dest, travel=row.travel, dispatch=row.dispatch, demand_level=1.)
        params = s8.params_of(row)
        output = simulate(world, storm, scen, params, S=50, seed=SEED, record_cells=False)
        pk = int(np.argmin(np.abs(np.array(storm["snap_minutes"])-storm["peak_minute"])))
        py_mean, py_peak = float(old.rel(output["city"]).mean()), float(old.rel(output["city"])[:, pk].mean())
        args = json.dumps(dict(scen=scen, params=params, storm=storm["date"], seeds=50))
        js = json.loads(subprocess.run(["node", str(ROOT / "sim/v2/parity_v2.mjs"), args],
                                       capture_output=True, text=True, check=True, timeout=3600).stdout.strip().splitlines()[-1])
        mean_diff, peak_diff = 100*(js["mean_rel"]/py_mean-1), 100*(js["peak_rel"]/py_peak-1)
        ok = abs(mean_diff) <= 5 and (abs(peak_diff) <= 5 or abs(js["peak_rel"]-py_peak) <= .01)
        result = dict(**scen, storm=storm["date"], python_mean_rel=py_mean, js_mean_rel=js["mean_rel"],
                      python_peak_rel=py_peak, js_peak_rel=js["peak_rel"], diff_mean_pct=mean_diff,
                      diff_peak_pct=peak_diff, within_5pct=ok)
        rows.append(result)
        print(result, flush=True)
    pd.DataFrame(rows).to_csv(ROOT / "outputs/tables/storm_builder_parity.csv", index=False)
    assert all(r["within_5pct"] for r in rows)


if __name__ == "__main__":
    main()
