"""POST-HOC check (added after the first test scoring and after S1): is the null weather gain driven by the
high-coverage months? Recomputes the weather gain on the test-year subset from 11 Jan 2026 (normal coverage)
using the frozen predictions of the primary 1 km models (h = 30, 60) and the S1 planning-area models
(h = 30, 60, 120; both labels). No model is refitted. Output: outputs/tables/posthoc_weather_gain_from_11jan.csv

Usage: .venv/bin/python -m analysis.06c_posthoc_normal_coverage
"""
from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from analysis.common import INTERIM, SEED, TABLES

P = importlib.import_module("analysis.06_forecast")
LABEL = "POST-HOC check, added after first test scoring and after S1"
START = pd.Timestamp("2026-01-11")


def gain(ts, y, a, b, mmh_h, rng, n_boot=1000):
    rows = []
    days = pd.Series(ts).dt.normalize()
    for sub, m in (("all", np.ones(len(y), bool)), ("rainy (rain at target time)", np.nan_to_num(mmh_h) > 0)):
        ud = np.sort(days[m].unique())
        di = np.searchsorted(ud, days[m].values)
        W = rng.multinomial(len(ud), np.full(len(ud), 1 / len(ud)), size=n_boot).astype(float)
        yy = y[m].astype(int)
        da = P.binned_ap(a[m], yy, di, len(ud), W)[1] - P.binned_ap(b[m], yy, di, len(ud), W)[1]
        g = average_precision_score(yy, a[m]) - average_precision_score(yy, b[m])
        rows.append({"subset": sub, "rows": int(m.sum()), "base_rate": float(yy.mean()),
                     "pr_auc_with_weather": float(average_precision_score(yy, a[m])),
                     "pr_auc_without_weather": float(average_precision_score(yy, b[m])), "weather_gain": float(g),
                     "lo": float(np.quantile(da, 0.025)), "hi": float(np.quantile(da, 0.975))})
    return rows


def main():
    rng = np.random.default_rng(SEED)
    out = []
    for h in (30, 60):
        t = pd.read_parquet(INTERIM / f"fc_pred_h{h}_test.parquet")
        t = t[(t.ts >= START) & t.y_low.notna()]
        for r in gain(t.ts, t.y_low.values, t.score_lgb_weather.values, t.score_lgb_no_weather.values, t.mmh_h.values, rng):
            out.append({"analysis": LABEL, "model": "primary 1 km LightGBM", "label": "deficit >= 50%", "h": h, **r})
    for h in (30, 60, 120):
        t = pd.read_parquet(INTERIM / f"s1_pred_pa_h{h}_test.parquet")
        t = t[t.ts >= START]
        for target, name in (("def", "deficit >= 50%"), ("nb", "below NB 5th percentile")):
            q = t[t[f"y_{target}"].notna()]
            for r in gain(q.ts, q[f"y_{target}"].values, q[f"score_{target}_lgb_weather"].values,
                          q[f"score_{target}_lgb_no_weather"].values, q.mmh_h.values, rng):
                out.append({"analysis": LABEL, "model": "S1 planning-area LightGBM", "label": name, "h": h, **r})
    o = pd.DataFrame(out)
    o.to_csv(TABLES / "posthoc_weather_gain_from_11jan.csv", index=False, float_format="%.5f")
    print(o.drop(columns="analysis").round(4).to_string(index=False))


if __name__ == "__main__":
    main()
