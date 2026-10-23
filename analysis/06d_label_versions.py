"""DISCLOSED ADDITIONAL SCORING of the test year (after the independent review of aac26fe). No model is refitted.

The forecasting results so far were evaluated against RETROSPECTIVE labels: the test-year baseline uses each test
regime's level estimated from that regime's own (test-year) rows, and the regime change points were found on all
five years. This script adds an ISSUE-TIME-KNOWABLE label: baseline B_f = pattern at t+h x trailing 7-day
coverage level known at t (the seasonal_h input), with the same rules:
    deficit:  (B_f - Y) / max(1, B_f) >= 0.5 where B_f >= 4
    NB:       Y < 5th percentile of NB(mean = B_f, dispersion of the scale, fitted on the fit period)
For the primary 1 km models (deficit label, 30/60 min) and the S1 models (both labels, 3 scales, 30/60/120 min),
it reports for BOTH label versions: PR-AUC with and without weather, the weather gain with 1,000 day-block
bootstrap draws, fixed-workload top-K precision / recall, and corrected lead times (analysis/fc_eval.py).

Output: outputs/tables/forecast_eval_both_labels.csv, forecast_eval_lead_both_labels.csv
"""
from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import average_precision_score

from analysis.common import INTERIM, SEED, TABLES, log_test_scoring
from analysis.fc_eval import k_for, lead_summary, lead_times, topk_alerts, topk_metrics

P = importlib.import_module("analysis.06_forecast")
LABEL = "Disclosed additional test-year scoring (after review of aac26fe); no refitting"


def nb_low(y, mu, alpha):
    ok = np.isfinite(mu) & (mu > 0)
    n = 1 / alpha
    p = n / (n + np.where(ok, mu, 1.0))
    q = stats.nbinom.ppf(0.05, n, p)
    return np.where(ok, (y < q).astype(float), np.nan)


def deficit_low(y, mu):
    ok = np.isfinite(mu) & (mu >= 4)
    return np.where(ok, ((mu - y) / np.maximum(1, mu) >= 0.5).astype(float), np.nan)


def evaluate(df, unit_col, h, label_cols, score_cols, rng, meta, eligible=None, n_boot=1000):
    rows, leads = [], []
    K = k_for(df[unit_col].nunique())
    rainy_all = (df.mmh_h.fillna(0) > 0).values
    for version, ycol in label_cols.items():
        y_all = df[ycol].values
        alerts = {m: topk_alerts(df.ts.values, df[c].values, K, eligible) for m, c in score_cols.items()}
        for sub, msk in (("all", np.ones(len(df), bool)), ("rainy (rain at target time)", rainy_all)):
            sel = msk & ~np.isnan(y_all)
            y = y_all[sel].astype(int)
            days = df.ts.dt.normalize().values[sel]
            ud = np.sort(np.unique(days))
            di = np.searchsorted(ud, days)
            W = rng.multinomial(len(ud), np.full(len(ud), 1 / len(ud)), size=n_boot).astype(float)
            r = {**meta, "h": h, "label_version": version, "subset": sub, "rows_defined": int(sel.sum()),
                 "base_rate": float(y.mean()), "K": K}
            for m, c in score_cols.items():
                s = np.nan_to_num(df[c].values[sel].astype(float), nan=-1e9)
                r[f"pr_auc_{m}"] = float(average_precision_score(y, s)) if y.any() else np.nan
                ya = np.nan_to_num(y_all[msk], nan=0.0) > 0.5
                a = alerts[m][msk]
                r[f"topk_precision_{m}"] = float(ya[a].mean()) if a.any() else np.nan
                r[f"topk_recall_{m}"] = float(a[ya].mean()) if ya.any() else np.nan
            a_ = P.binned_ap(df[score_cols["lgb_weather"]].values[sel], y, di, len(ud), W)
            b_ = P.binned_ap(df[score_cols["lgb_no_weather"]].values[sel], y, di, len(ud), W)
            d = a_[1] - b_[1]
            r["weather_gain"] = r["pr_auc_lgb_weather"] - r["pr_auc_lgb_no_weather"]
            r["gain_lo"], r["gain_hi"] = float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))
            r["material_gain_rule_met"] = bool(r["weather_gain"] >= 0.01 and r["gain_lo"] > 0)
            rows.append(r)
        for m, c in score_cols.items():
            runs = lead_times(df.ts.values, df[unit_col].values, alerts[m], y_all, h)
            leads.append({**meta, "h": h, "label_version": version, "model": m, "alerts": f"top-{K} per issue time",
                          **lead_summary(runs)})
    return rows, leads


def main():
    rng = np.random.default_rng(SEED)
    log_test_scoring("06d_label_versions.py", "primary and S1 test-year predictions scored against retrospective "
                     "and issue-time labels (top-K workload, corrected lead time)", "disclosed additional scoring")
    alpha = pd.read_csv(TABLES / "s1_nb_dispersion.csv", index_col=0).alpha
    rows, leads = [], []
    # primary 1 km models, deficit label
    for h in (30, 60):
        t = pd.read_parquet(INTERIM / f"fc_pred_h{h}_test.parquet")
        t["y_retro"] = t.y_low.astype(float)
        t["y_issue"] = deficit_low(t.y_count.values, t.seasonal_h.values.astype(float))
        sc = {"persistence": "score_persistence", "lgb_no_weather": "score_lgb_no_weather",
              "lgb_weather": "score_lgb_weather", "glm_no_weather": "score_glm_no_weather",
              "glm_weather": "score_glm_weather"}
        r, l = evaluate(t, "cell", h, {"retrospective": "y_retro", "issue-time": "y_issue"}, sc, rng,
                        {"analysis": "primary", "scale": "1km", "label": "deficit >= 50%"},
                        eligible=t.seasonal_h.values >= 4)
        rows += r
        leads += l
        print(pd.DataFrame(r)[["h", "label_version", "subset", "base_rate", "pr_auc_lgb_no_weather", "pr_auc_lgb_weather",
                               "weather_gain", "gain_lo", "gain_hi"]].round(4).to_string(index=False), flush=True)
    # S1 models
    for scale in ("1km", "2km", "pa"):
        for h in (30, 60, 120):
            pr = pd.read_parquet(INTERIM / f"s1_pred_{scale}_h{h}_test.parquet")
            fc = pd.read_parquet(INTERIM / f"s1_fc_{scale}_h{h}_test.parquet", columns=["ts", "unit", "y_h", "seasonal_h"])
            t = pr.merge(fc, on=["ts", "unit"], how="left")
            mu = t.seasonal_h.values.astype(float)
            for target, name in (("def", "deficit >= 50%"), ("nb", "below NB 5th percentile")):
                t["y_retro"] = t[f"y_{target}"].astype(float)
                t["y_issue"] = (deficit_low(t.y_h.values, mu) if target == "def" else nb_low(t.y_h.values, mu, alpha[scale]))
                sc = {"persistence": f"score_{target}_persistence", "lgb_no_weather": f"score_{target}_lgb_no_weather",
                      "lgb_weather": f"score_{target}_lgb_weather"}
                r, l = evaluate(t, "unit", h, {"retrospective": "y_retro", "issue-time": "y_issue"}, sc, rng,
                                {"analysis": "S1", "scale": scale, "label": name},
                                eligible=(mu >= 4) if target == "def" else None)
                rows += r
                leads += l
            print(scale, h, "done", flush=True)
    out = pd.DataFrame(rows)
    out.insert(0, "note", LABEL)
    out.to_csv(TABLES / "forecast_eval_both_labels.csv", index=False, float_format="%.5f")
    lo = pd.DataFrame(leads)
    lo.insert(0, "note", LABEL)
    lo.to_csv(TABLES / "forecast_eval_lead_both_labels.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
