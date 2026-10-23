"""Step 6: forecasting unusually low availability - the centrepiece (HANDOFF section 6, step 6).

Question: how much does weather data improve early warning of unusually low taxi availability, beyond watching
current taxi numbers?

Setup
  issue time t, horizons h = 30 and 60 minutes, unit = eligible 1 km cell.
  targets: vacant count at t+h (count models) and low availability at t+h (deficit >= 0.5 where the baseline
  at t+h is >= 4; classification models). The target uses the panel's regime-level baseline (HANDOFF 5);
  that baseline is NEVER an input.
  inputs: only data available by t (rules 3 and 4): taxis at t, t-30, t-60; the citywide count at t; trailing
  coverage levels (1 day, 7 days, from snapshots up to t); the training-period pattern for the cell and time
  of week (cell + how^month effects from the baseline fit, no regime level); climatology of low availability
  (fit period); calendar; cell traits; and, for the "with weather" models only, rain before t at the cell,
  within 2 km, in the 2-5 km ring, island-wide, wet/dry durations, minutes since rain appeared within 5 km,
  and the latest NEA 2-hour forecast issued before t.
  periods: fit Apr 2022 - Mar 2025 (training and tuning with time-ordered expanding folds), calibrate
  Apr - Sep 2025 (probability calibration, alert thresholds, conformal quantiles), test Oct 2025 - Sep 2026
  (scored once; reported overall, in rainy slots, and before / after the coverage change of 11 Jan 2026).

Models (each with and without weather where it applies): persistence, seasonal baseline (pattern x trailing
level), regression (Poisson / logistic), LightGBM (poisson / binary).

Parts:  --part features | tune | fit | evaluate     (run in this order)
Outputs: data/interim/fc_* (not in git), outputs/tables/forecast_*.csv/json, outputs/figures/forecast_*.
"""
from __future__ import annotations

import argparse
import gc
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd

from analysis.common import (BLUE, BLUE_DARK, CALIB, FIT, INTERIM, MUTED, ORANGE, SEED, TABLES, TEST,
                             log_test_scoring, save, style)

HORIZONS = (30, 60)
SPLITS = {"fit": FIT, "calib": CALIB, "test": TEST}
FIT_SAMPLE_FRAC = 0.35                 # share of fit-period issue snapshots kept for training
COVERAGE_CHANGE = pd.Timestamp("2026-01-11")
ALERT_RATE = 0.05                      # fixed alert workload: 5% of eligible cell-snapshots (10% as a check)
TOP_K = 20
CONFORMAL_LEVEL = 0.90

PANEL_COLS = ["ts", "cell", "vacant", "citywide", "glitch", "drop_main", "baseline", "low", "regime_id", "how",
              "hod", "dow", "month", "daytype", "school_holiday", "vacant_lag1", "vacant_lag2", "mmh", "mmh_lag1",
              "mmh_lag2", "mmh_3g", "wet_min", "dry_min", "rain_2km", "rain_ring", "wet5_min", "dry5_min",
              "mmh_island", "gauges_wet_share", "fc_code", "fc_age_min"]
WEATHER = ["mmh", "mmh_lag1", "mmh_lag2", "mmh_3g", "wet_min", "dry_min", "rain_2km", "rain_ring", "wet5_min",
           "dry5_min", "mmh_island", "gauges_wet_share", "fc_code", "fc_age_min", "fc_code_max_nb"]
BASE = ["log_y0", "log_y1", "log_y2", "pattern_t", "pattern_h", "log_pattern_ratio", "lev_t", "lev_1d", "lev_7d",
        "seasonal_h", "deficit_feasible_t", "log_citywide", "citywide_change", "clim_low", "hod_h", "dow_h",
        "daytype", "month", "school_holiday", "city_centre", "dist_mrt_m", "taxi_stands_300m", "cell_cat"]


# ============================================================================= features
def pattern_table():
    """exp(cell + how^month effects) from the baseline fit, i.e. the baseline without the regime level."""
    f = INTERIM / "forecast_pattern.parquet"
    if f.exists():
        return pd.read_parquet(f)
    R = pd.read_csv(TABLES / "baseline_regime_levels_30.csv").set_index("regime_id").log_level
    parts = []
    for y in range(2022, 2026):
        p = pd.read_parquet(INTERIM / f"panel30_{y}.parquet", columns=["cell", "how", "month", "baseline", "regime_id"])
        p = p[p.baseline.notna()]
        p["pattern"] = p.baseline / np.exp(p.regime_id.map(R))
        parts.append(p.groupby(["cell", "how", "month"]).pattern.first())
    t = pd.concat(parts).groupby(level=[0, 1, 2]).first().rename("pattern").reset_index()
    t.to_parquet(f, index=False)
    return t


def climatology():
    f = INTERIM / "forecast_climatology.parquet"
    if f.exists():
        return pd.read_parquet(f)
    parts = []
    for y in range(2022, 2026):
        p = pd.read_parquet(INTERIM / f"panel30_{y}.parquet", columns=["ts", "cell", "hod", "daytype", "low", "drop_main"],
                            filters=[("ts", ">=", FIT[0]), ("ts", "<=", FIT[1])])
        p = p[~p.drop_main & p.low.notna()]
        parts.append(p.groupby(["cell", "hod", "daytype"]).low.agg(["sum", "count"]))
    t = pd.concat(parts).groupby(level=[0, 1, 2]).sum()
    t["clim_low"] = (t["sum"] + 1) / (t["count"] + 6)          # light shrinkage towards ~17%
    t = t.reset_index()[["cell", "hod", "daytype", "clim_low"]]
    t.to_parquet(f, index=False)
    return t


def forecast_neighbours():
    """For each cell, the max forecast code over the 3 nearest forecast areas is approximated by the max over
    cells within 5 km at the same time (computed in build_chunk)."""
    from pipeline.grid import to_xy
    c = pd.read_parquet(INTERIM / "cells.parquet")
    c = c[c.eligible].reset_index(drop=True)
    x, y = to_xy(c.lon.values, c.lat.values)
    d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    return c.cell.values, (d <= 5000)


def build_chunk(year, h, start, end, pat, clim, cells, nb5, frac=None, rng=None):
    hist_start = max(pd.Timestamp(f"{year}-01-01") - pd.Timedelta(days=8), pd.Timestamp("2021-10-01"))
    parts = []
    for y in (year - 1, year):
        f = INTERIM / f"panel30_{y}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f, columns=PANEL_COLS, filters=[("ts", ">=", hist_start),
                                                                         ("ts", "<=", pd.Timestamp(f"{year}-12-31 23:59") + pd.Timedelta(minutes=h))]))
    p = pd.concat(parts, ignore_index=True)
    if y == year and (INTERIM / f"panel30_{year + 1}.parquet").exists():
        nxt = pd.read_parquet(INTERIM / f"panel30_{year + 1}.parquet", columns=PANEL_COLS,
                              filters=[("ts", "<=", pd.Timestamp(f"{year + 1}-01-01") + pd.Timedelta(minutes=h))])
        p = pd.concat([p, nxt], ignore_index=True)
    p = p.drop_duplicates(["cell", "ts"]).merge(pat, on=["cell", "how", "month"], how="left")
    # snapshot-level coverage level: sum of vacant / sum of pattern over eligible cells (non-glitch snapshots)
    snap = p[~p.glitch].groupby("ts").agg(v=("vacant", "sum"), pt=("pattern", "sum"), cw=("citywide", "first"))
    snap["lev_t"] = snap.v / snap.pt
    s = snap.lev_t
    snap["lev_1d"] = s.rolling("1D").median()
    snap["lev_7d"] = s.rolling("7D").median()
    snap["citywide_change"] = snap.cw / snap.cw.shift(1)
    snap.loc[snap.index.to_series().diff() > pd.Timedelta(minutes=31), "citywide_change"] = np.nan
    # forecast code: max over cells within 5 km at the same time (neighbouring forecast areas)
    fc = p.pivot_table(index="ts", columns="cell", values="fc_code", aggfunc="first").reindex(columns=cells)
    F = fc.values.astype("float32")
    F[np.isnan(F)] = -1
    fmax = np.full(F.shape, -1, "int8")
    for j in range(len(cells)):
        fmax[:, j] = F[:, nb5[j]].max(1)
    fcm = pd.DataFrame(fmax, index=fc.index, columns=cells).stack().rename("fc_code_max_nb")
    # issue rows and their targets
    iss = p[(p.ts >= max(start, pd.Timestamp(f"{year}-01-01"))) & (p.ts <= min(end, pd.Timestamp(f"{year}-12-31 23:59")))
            & ~p.drop_main]
    if frac is not None:
        times = iss.ts.unique()
        keep = rng.choice(times, size=int(len(times) * frac), replace=False)
        iss = iss[iss.ts.isin(keep)]
    tgt = p[["ts", "cell", "vacant", "low", "baseline", "drop_main", "mmh", "pattern", "hod", "dow", "regime_id"]].copy()
    tgt["ts"] = tgt.ts - pd.Timedelta(minutes=h)
    tgt = tgt.rename(columns={"vacant": "y_count", "low": "y_low", "baseline": "baseline_h", "drop_main": "drop_h",
                              "mmh": "mmh_h", "pattern": "pattern_h", "hod": "hod_h", "dow": "dow_h",
                              "regime_id": "regime_h"})
    d = iss.merge(tgt, on=["ts", "cell"], how="inner")
    d = d[~d.drop_h & d.pattern_h.notna()].drop(columns=["drop_h"])
    d = d.join(snap[["lev_t", "lev_1d", "lev_7d", "citywide_change"]], on="ts")
    d = d.join(fcm, on=["ts", "cell"])
    d = d.merge(clim.rename(columns={"hod": "hod_h"}), on=["cell", "hod_h", "daytype"], how="left")
    cc = pd.read_parquet(INTERIM / "cells.parquet").set_index("cell")
    d["city_centre"] = d.cell.map(cc.city_centre).astype("int8")
    d["dist_mrt_m"] = d.cell.map(cc.dist_mrt_m).astype("float32")
    d["taxi_stands_300m"] = d.cell.map(cc.taxi_stands_300m).astype("int16")
    d["log_y0"] = np.log1p(d.vacant)
    d["log_y1"] = np.log1p(d.vacant_lag1)
    d["log_y2"] = np.log1p(d.vacant_lag2)
    d["pattern_t"] = d.pattern
    d["log_pattern_ratio"] = np.log(d.pattern_h / d.pattern_t)
    d["seasonal_h"] = d.pattern_h * d.lev_7d
    sea_t = d.pattern_t * d.lev_7d
    d["deficit_feasible_t"] = (sea_t - d.vacant) / np.maximum(1, sea_t)
    d["log_citywide"] = np.log(d.citywide.astype(float))
    d["cell_cat"] = d.cell.astype("int32")
    keep = (["ts", "cell", "y_count", "y_low", "baseline_h", "mmh_h", "regime_h", "vacant"]
            + [c for c in BASE if c not in ("cell_cat",)] + ["cell_cat"] + WEATHER)
    d = d[list(dict.fromkeys(keep))]
    for c in d.columns:
        if d[c].dtype == "float64":
            d[c] = d[c].astype("float32")
    return d


def part_features():
    rng = np.random.default_rng(SEED)
    pat, clim = pattern_table(), climatology()
    cells, nb5 = forecast_neighbours()
    for h in HORIZONS:
        for split, (a, b) in SPLITS.items():
            out = INTERIM / f"fc_h{h}_{split}.parquet"
            chunks = []
            for year in range(a.year, b.year + 1):
                t0 = time.time()
                d = build_chunk(year, h, a, b, pat, clim, cells, nb5, frac=FIT_SAMPLE_FRAC if split == "fit" else None,
                                rng=rng)
                chunks.append(d)
                print(f"h={h} {split} {year}: {len(d):,} rows {time.time() - t0:.0f}s", flush=True)
                gc.collect()
            pd.concat(chunks, ignore_index=True).to_parquet(out, index=False, compression="zstd")
            del chunks
            gc.collect()


# ============================================================================= models
CLIM_FILL = 0.17                       # fit-period share of low availability; used where climatology is undefined


def load_split(h, split):
    d = pd.read_parquet(INTERIM / f"fc_h{h}_{split}.parquet")
    d["clim_low"] = d.clim_low.fillna(CLIM_FILL)
    return d


def feats(weather: bool):
    return BASE + (WEATHER if weather else [])


def lgb_params(objective, tuned=None):
    p = {"objective": objective, "learning_rate": 0.05, "num_leaves": 127, "min_data_in_leaf": 200,
         "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "verbose": -1,
         "seed": SEED, "num_threads": 8, "max_bin": 255}
    if tuned:
        p.update(tuned)
    return p


def part_tune(n_trials=8, rows_per_fold=400_000):
    """Optuna on time-ordered expanding folds inside the fit period, for each LightGBM objective
    (h = 60, with weather); the chosen settings are reused for all LightGBM models."""
    import lightgbm as lgb
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    d = load_split(60, "fit")
    folds = [("2022-04-01", "2023-03-31", "2023-04-01", "2023-09-30"),
             ("2022-04-01", "2023-09-30", "2023-10-01", "2024-03-31"),
             ("2022-04-01", "2024-03-31", "2024-04-01", "2025-03-31")]
    rng = np.random.default_rng(SEED)
    X = d[feats(True)]
    results = {}
    for objective, target in (("poisson", "y_count"), ("binary", "y_low")):
        ok = d[target].notna().values
        fold_idx = []
        for a, b, c, e in folds:
            tr = np.flatnonzero(ok & (d.ts >= a).values & (d.ts <= pd.Timestamp(b) + pd.Timedelta(hours=23.9)).values)
            va = np.flatnonzero(ok & (d.ts >= c).values & (d.ts <= pd.Timestamp(e) + pd.Timedelta(hours=23.9)).values)
            fold_idx.append((rng.choice(tr, min(rows_per_fold, len(tr)), replace=False),
                             rng.choice(va, min(rows_per_fold // 2, len(va)), replace=False)))

        def objective_fn(trial):
            tuned = {"learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
                     "num_leaves": trial.suggest_int("num_leaves", 31, 255, log=True),
                     "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 50, 2000, log=True),
                     "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
                     "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 30, log=True)}
            scores, iters = [], []
            for tr, va in fold_idx:
                y = d[target].values
                dt = lgb.Dataset(X.iloc[tr], y[tr].astype(float), categorical_feature=["cell_cat"], free_raw_data=False)
                dv = lgb.Dataset(X.iloc[va], y[va].astype(float), reference=dt)
                m = lgb.train(lgb_params(objective, tuned), dt, num_boost_round=1500, valid_sets=[dv],
                              callbacks=[lgb.early_stopping(50, verbose=False)])
                scores.append(m.best_score["valid_0"]["poisson" if objective == "poisson" else "binary_logloss"])
                iters.append(m.best_iteration)
            trial.set_user_attr("iters", iters)
            return float(np.mean(scores))

        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=SEED))
        study.optimize(objective_fn, n_trials=n_trials)
        best = dict(study.best_params)
        best["num_boost_round"] = int(np.max(study.best_trial.user_attrs["iters"]) * 1.1)
        results[objective] = {"params": best, "cv_score": study.best_value,
                              "trials": [{"params": t.params, "value": t.value} for t in study.trials]}
        print(objective, best, study.best_value, flush=True)
    (TABLES / "forecast_tuning.json").write_text(json.dumps(results, indent=2))


def glm_design(d, weather, scaler=None):
    cols = [c for c in feats(weather) if c not in ("cell_cat", "hod_h", "dow_h", "month", "daytype", "fc_code",
                                                    "fc_code_max_nb")]
    Xn = d[cols].astype("float64").fillna(0).values
    if scaler is None:
        scaler = (Xn.mean(0), Xn.std(0) + 1e-9)
    Xn = (Xn - scaler[0]) / scaler[1]
    cats = [np.eye(48)[d.hod_h.values.astype(int)][:, 1:], np.eye(3)[d.daytype.values.astype(int)][:, 1:]]
    if weather:
        cats += [np.eye(5)[d.fc_code.values.astype(int) + 1][:, 1:], np.eye(5)[d.fc_code_max_nb.values.astype(int) + 1][:, 1:]]
    return np.hstack([Xn] + cats), scaler


def part_fit(glm_rows=2_000_000, lgb_rows=3_000_000, horizons=HORIZONS):
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression, PoissonRegressor
    tuned = json.loads((TABLES / "forecast_tuning.json").read_text())
    rng = np.random.default_rng(SEED)
    imp_rows = []
    for h in horizons:
        tr = load_split(h, "fit")
        models = {}
        for weather in (False, True):
            tag = "weather" if weather else "no_weather"
            F = feats(weather)
            for objective, target in (("poisson", "y_count"), ("binary", "y_low")):
                ok = tr[target].notna().values
                lgb_idx = np.sort(np.random.default_rng(SEED).choice(np.flatnonzero(ok), min(lgb_rows, ok.sum()),
                                                                     replace=False))
                t0 = time.time()
                prm = dict(tuned[objective]["params"])
                rounds = prm.pop("num_boost_round")
                ds = lgb.Dataset(tr.iloc[lgb_idx][F], tr[target].values[lgb_idx].astype(float), categorical_feature=["cell_cat"])
                m = lgb.train(lgb_params(objective, prm), ds, num_boost_round=rounds)
                m.save_model(str(INTERIM / f"fc_lgb_{objective}_h{h}_{tag}.txt"))
                models[("lgb", objective, tag)] = m
                gain = pd.Series(m.feature_importance("gain"), index=F)
                imp_rows += [{"h": h, "model": f"lgb_{objective}_{tag}", "feature": k, "gain_share": v / gain.sum()}
                             for k, v in gain.items()]
                print(f"h={h} lgb {objective} {tag}: {len(lgb_idx):,} rows {time.time() - t0:.0f}s", flush=True)
                # regression
                idx = rng.choice(np.flatnonzero(ok), min(glm_rows, ok.sum()), replace=False)
                X, sc = glm_design(tr.iloc[idx], weather)
                y = tr[target].values[idx].astype(float)
                t0 = time.time()
                g = (PoissonRegressor(alpha=1e-6, max_iter=300) if objective == "poisson"
                     else LogisticRegression(C=1e6, max_iter=500))
                g.fit(X, y)
                models[("glm", objective, tag)] = (g, sc)
                print(f"h={h} glm {objective} {tag}: {time.time() - t0:.0f}s", flush=True)
        pd.to_pickle({k: v for k, v in models.items() if k[0] == "glm"}, INTERIM / f"fc_glm_h{h}.pkl")
        del tr
        gc.collect()
        for split in ("calib", "test"):
            d = load_split(h, split)
            out = d[["ts", "cell", "y_count", "y_low", "baseline_h", "mmh_h", "regime_h", "vacant", "seasonal_h",
                     "deficit_feasible_t", "clim_low", "mmh", "rain_ring", "rain_2km"]].copy()
            out["count_persistence"] = d.vacant.astype("float32")
            out["count_seasonal"] = d.seasonal_h
            out["score_persistence"] = d.deficit_feasible_t
            out["score_seasonal"] = d.clim_low
            for (kind, objective, tag), m in models.items():
                col = f"{'count' if objective == 'poisson' else 'score'}_{kind}_{tag}"
                if kind == "lgb":
                    out[col] = m.predict(d[feats(tag == "weather")]).astype("float32")
                else:
                    g, sc = m
                    X, _ = glm_design(d, tag == "weather", sc)
                    out[col] = (g.predict(X) if objective == "poisson" else g.predict_proba(X)[:, 1]).astype("float32")
            out.to_parquet(INTERIM / f"fc_pred_h{h}_{split}.parquet", index=False)
            if split == "test":
                log_test_scoring(f"06_forecast.py --part fit --h {h}", f"test-year predictions ({h} min) written",
                                 "primary", len(out))
                stamp = INTERIM / "test_year_first_scored.txt"
                if not stamp.exists():
                    stamp.write_text(datetime.now().isoformat(timespec="seconds"))
            print(f"h={h} predictions {split}: {len(out):,}", flush=True)
            # SHAP (TreeSHAP via LightGBM) on a test sample, weather binary model
            if split == "test":
                m = models[("lgb", "binary", "weather")]
                s = d[d.y_low.notna()].sample(20_000, random_state=SEED)
                contrib = m.predict(s[feats(True)], pred_contrib=True)[:, :-1]
                sh = pd.DataFrame({"feature": feats(True), "mean_abs_shap": np.abs(contrib).mean(0)})
                rain = (s.mmh.values > 0) | (s.rain_ring.fillna(0).values > 0)
                sh["mean_abs_shap_rain_nearby"] = np.abs(contrib[rain]).mean(0) if rain.any() else np.nan
                sh.sort_values("mean_abs_shap", ascending=False).to_csv(TABLES / f"forecast_shap_h{h}.csv", index=False,
                                                                        float_format="%.6f")
            del d, out
            gc.collect()
    pd.DataFrame(imp_rows).to_csv(TABLES / f"forecast_importance_gain_h{'_'.join(map(str, horizons))}.csv", index=False, float_format="%.6f")


# ============================================================================= evaluation
def binned_ap(score, y, day, n_days, W, n_bins=2000):
    """Average precision from per-day counts in score bins, for the observed data and for bootstrap day weights W.
    Scores are tied within a bin (2,000 quantile bins), so the observed value is a close approximation."""
    s = np.nan_to_num(np.asarray(score, float), nan=np.nanmin(score))
    edges = np.unique(np.quantile(s, np.linspace(0, 1, n_bins + 1)))
    bi = np.clip(np.searchsorted(edges, s, "right") - 1, 0, len(edges) - 2)
    nb = len(edges) - 1
    P = np.zeros((n_days, nb))
    N = np.zeros((n_days, nb))
    np.add.at(P, (day, bi), y)
    np.add.at(N, (day, bi), 1 - y)

    def ap(pos, neg):                     # pos, neg: (..., bins), highest score bin last
        pos, neg = pos[..., ::-1], neg[..., ::-1]
        tp, fp = np.cumsum(pos, -1), np.cumsum(neg, -1)
        prec = tp / np.maximum(tp + fp, 1e-12)
        return (pos * prec).sum(-1) / np.maximum(pos.sum(-1), 1e-12)

    return ap(P.sum(0), N.sum(0)), ap(W @ P, W @ N)


def evaluate_split(pr, split, h, thresholds=None):
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    count_models = ["count_persistence", "count_seasonal", "count_glm_no_weather", "count_glm_weather",
                    "count_lgb_no_weather", "count_lgb_weather"]
    score_models = ["score_persistence", "score_seasonal", "score_glm_no_weather", "score_glm_weather",
                    "score_lgb_no_weather", "score_lgb_weather"]
    subsets = {"all": np.ones(len(pr), bool), "rainy (rain at target time)": (pr.mmh_h.fillna(0) > 0).values,
               "rain at or near cell at issue": ((pr.mmh.fillna(0) > 0) | (pr.rain_ring.fillna(0) > 0)).values,
               "rain starts between issue and target": ((pr.mmh.fillna(0) == 0) & (pr.mmh_h.fillna(0) > 0)).values,
               "heavy rain at target time": (pr.mmh_h.fillna(0) > 10).values,
               "cell dry at issue, heavier rain 2-5 km away": ((pr.mmh.fillna(0) == 0)
                                                               & (pr.rain_ring.fillna(0) > 2.5)).values}
    if split == "test":
        subsets["test before 11 Jan 2026 (high coverage)"] = (pr.ts < COVERAGE_CHANGE).values
        subsets["test from 11 Jan 2026"] = (pr.ts >= COVERAGE_CHANGE).values
    from analysis.fc_eval import k_for, topk_alerts
    K = k_for(pr.cell.nunique())
    elig = (pr.seasonal_h.values >= 4)          # expected >= 4 known at issue time (deficit label defined)
    alerts = {c: topk_alerts(pr.ts.values, pr[c].values, K, elig) for c in score_models}
    ylow_all = np.nan_to_num(pr.y_low.astype(float).values, nan=0.0) > 0.5
    rows, thr_rows = [], []
    for sub, m in subsets.items():
        q = pr[m]
        for c in count_models:
            rows.append({"h": h, "split": split, "subset": sub, "task": "count", "model": c.replace("count_", ""),
                         "MAE": float(np.mean(np.abs(q[c] - q.y_count))), "rows": int(len(q))})
        cl = q[q.y_low.notna()]
        yl = cl.y_low.astype(int).values
        for c in score_models:
            s = cl[c].values.astype(float)
            s = np.nan_to_num(s, nan=np.nanmin(s))
            a = alerts[c][m]
            ya = ylow_all[m]
            r = {"h": h, "split": split, "subset": sub, "task": "low", "model": c.replace("score_", ""),
                 "base_rate": float(yl.mean()), "rows": int(len(cl)),
                 "PR_AUC": float(average_precision_score(yl, s)) if yl.any() else np.nan,
                 "ROC_AUC": float(roc_auc_score(yl, s)) if 0 < yl.mean() < 1 else np.nan,
                 "K_per_issue_time": K, "topk_alert_rate_all_cells": float(a.mean()),
                 "topk_precision": float(ya[a].mean()) if a.any() else np.nan,
                 "topk_recall": float(a[ya].mean()) if ya.any() else np.nan}
            if c.endswith(("glm_weather", "glm_no_weather", "lgb_weather", "lgb_no_weather")) and c + "_cal" in cl:
                r["brier_calibrated"] = float(brier_score_loss(yl, cl[c + "_cal"].values))
            rows.append(r)
            if thresholds is not None:
                at = s >= thresholds[c]
                thr_rows.append({"h": h, "split": split, "subset": sub, "model": c.replace("score_", ""),
                                 "note": "SECONDARY: threshold = calibration-period 95th percentile of the score on "
                                         "rows with a defined label; alert rates differ by model",
                                 "alert_rate_labelled_rows": float(at.mean()),
                                 "precision": float(yl[at].mean()) if at.any() else np.nan,
                                 "recall": float(at[yl == 1].mean()) if yl.any() else np.nan})
    return rows, thr_rows


def part_evaluate(n_boot=1000):
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import average_precision_score
    style()
    rng = np.random.default_rng(SEED)
    from analysis.fc_eval import k_for, lead_summary, topk_alerts
    from analysis.fc_eval import lead_times as lead_runs
    log_test_scoring("06_forecast.py --part evaluate", "primary test-year metrics (corrected top-K workload and lead "
                     "time; retrospective labels)", "primary")
    all_rows, boot_rows, lead_rows, conf_rows, calib_rows, thr_all, lead_thr = [], [], [], [], [], [], []
    for h in HORIZONS:
        ca = pd.read_parquet(INTERIM / f"fc_pred_h{h}_calib.parquet")
        te = pd.read_parquet(INTERIM / f"fc_pred_h{h}_test.parquet")
        score_models = [c for c in ca.columns if c.startswith("score_")]
        # calibration (isotonic, fitted on the calibration period) and alert thresholds at a fixed workload
        thresholds = {}
        for c in score_models:
            cl = ca[ca.y_low.notna()]
            s = np.nan_to_num(cl[c].values.astype(float), nan=np.nanmin(cl[c]))
            thresholds[c] = float(np.quantile(s, 1 - ALERT_RATE))
            if any(c.endswith(t) for t in ("glm_weather", "glm_no_weather", "lgb_weather", "lgb_no_weather")):
                iso = IsotonicRegression(out_of_bounds="clip").fit(s, cl.y_low.astype(int).values)
                for d in (ca, te):
                    d[c + "_cal"] = iso.predict(np.nan_to_num(d[c].values.astype(float), nan=np.nanmin(s)))
                # reliability table on the test year
                tl = te[te.y_low.notna()]
                bins = pd.cut(tl[c + "_cal"], np.linspace(0, 1, 11), include_lowest=True)
                rel = tl.groupby(bins, observed=True).agg(pred=(c + "_cal", "mean"), obs=("y_low", "mean"),
                                                          n=("y_low", "size")).reset_index(drop=True)
                rel["h"], rel["model"] = h, c
                calib_rows.append(rel)
        for d_, nm in ((ca, "calib"), (te, "test")):
            r1, r2 = evaluate_split(d_, nm, h, thresholds)
            all_rows += r1
            thr_all += r2
        # day-block bootstrap of the weather gain on the test year (LightGBM and regression)
        tl = te[te.y_low.notna()].reset_index(drop=True)
        days = tl.ts.dt.normalize()
        ud = np.sort(days.unique())
        di = np.searchsorted(ud, days.values)
        rainy = (tl.mmh_h.fillna(0) > 0).values
        W = rng.multinomial(len(ud), np.full(len(ud), 1 / len(ud)), size=n_boot).astype(float)
        for kind in ("lgb", "glm"):
            a, b = f"score_{kind}_weather", f"score_{kind}_no_weather"
            starts = ((tl.mmh.fillna(0) == 0) & (tl.mmh_h.fillna(0) > 0)).values
            for sub, msk in (("all", np.ones(len(tl), bool)), ("rainy (rain at target time)", rainy),
                             ("rain starts between issue and target", starts)):
                y = tl.y_low.values[msk].astype(int)
                exact = (average_precision_score(y, tl[a].values[msk]) - average_precision_score(y, tl[b].values[msk]))
                ap_a = binned_ap(tl[a].values[msk], y, di[msk], len(ud), W)
                ap_b = binned_ap(tl[b].values[msk], y, di[msk], len(ud), W)
                diffs = ap_a[1] - ap_b[1]
                boot_rows.append({"h": h, "model": kind, "subset": sub, "pr_auc_gain": exact,
                                  "pr_auc_gain_binned": ap_a[0] - ap_b[0],
                                  "lo": float(np.quantile(diffs, 0.025)), "hi": float(np.quantile(diffs, 0.975)),
                                  "share_draws_gain_positive": float((diffs > 0).mean()), "boot": n_boot})
                print(boot_rows[-1], flush=True)
        # lead times: main = fixed top-K workload per issue time; secondary = calibration thresholds
        K = k_for(te.cell.nunique())
        for c in score_models:
            for kind, a in (("top-K", topk_alerts(te.ts.values, te[c].values, K, te.seasonal_h.values >= 4)),
                            ("calibration threshold", np.nan_to_num(te[c].values.astype(float), nan=-np.inf) >= thresholds[c])):
                runs = lead_runs(te.ts.values, te.cell.values, a, te.y_low.values, h)
                row = {"h": h, "model": c.replace("score_", ""), "alerts": kind, "label": "retrospective",
                       **lead_summary(runs)}
                (lead_rows if kind == "top-K" else lead_thr).append(row)
        # split-conformal count ranges (scaled residuals), calibrated on Apr-Sep 2025
        for c in [c for c in ca.columns if c.startswith("count_")]:
            r_ca = np.abs(ca.y_count - ca[c]) / np.sqrt(ca[c].clip(lower=0) + 1)
            n = len(r_ca)
            qhat = float(np.quantile(r_ca, min(1, np.ceil((n + 1) * CONFORMAL_LEVEL) / n)))
            for sub, d in (("test all", te), ("test rainy", te[te.mmh_h.fillna(0) > 0]),
                           ("test before 11 Jan 2026", te[te.ts < COVERAGE_CHANGE]),
                           ("test from 11 Jan 2026", te[te.ts >= COVERAGE_CHANGE])):
                half = qhat * np.sqrt(d[c].clip(lower=0) + 1)
                cov = ((d.y_count >= d[c] - half) & (d.y_count <= d[c] + half)).mean()
                conf_rows.append({"h": h, "model": c.replace("count_", ""), "subset": sub, "target": CONFORMAL_LEVEL,
                                  "achieved_coverage": float(cov), "mean_width": float((2 * half).mean()), "qhat": qhat})
        del ca, te
        gc.collect()
    res = pd.DataFrame(all_rows)
    res.to_csv(TABLES / "forecast_metrics.csv", index=False, float_format="%.5f")
    pd.DataFrame(boot_rows).to_csv(TABLES / "forecast_weather_gain.csv", index=False, float_format="%.5f")
    pd.DataFrame(lead_rows).to_csv(TABLES / "forecast_lead_times.csv", index=False, float_format="%.4f")
    pd.DataFrame(lead_thr).to_csv(TABLES / "forecast_lead_times_calibration_threshold.csv", index=False, float_format="%.4f")
    pd.DataFrame(thr_all).to_csv(TABLES / "forecast_calibration_threshold.csv", index=False, float_format="%.5f")
    pd.DataFrame(conf_rows).to_csv(TABLES / "forecast_conformal.csv", index=False, float_format="%.4f")
    pd.concat(calib_rows).to_csv(TABLES / "forecast_reliability.csv", index=False, float_format="%.4f")
    charts()


def charts():
    import matplotlib.pyplot as plt
    style()
    res = pd.read_csv(TABLES / "forecast_metrics.csv")
    gain = pd.read_csv(TABLES / "forecast_weather_gain.csv")
    order = ["persistence", "seasonal", "glm_no_weather", "glm_weather", "lgb_no_weather", "lgb_weather"]
    labels = ["Persistence", "Seasonal\nbaseline", "Regression", "Regression\n+ weather", "LightGBM", "LightGBM\n+ weather"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, h in zip(axes, HORIZONS):
        for k, (sub, col) in enumerate((("all", BLUE_DARK), ("rainy (rain at target time)", ORANGE))):
            t = res[(res.h == h) & (res.split == "test") & (res.task == "low") & (res.subset == sub)].set_index("model").loc[order]
            x = np.arange(len(order)) + (k - 0.5) * 0.36
            bars = ax.bar(x, t.PR_AUC, 0.34, color=col, label="All slots" if sub == "all" else "Rainy slots")
            ax.bar_label(bars, fmt="%.3f", fontsize=6.5, color=MUTED, padding=1)
            ax.axhline(t.base_rate.iloc[0], color=col, lw=0.8, ls=":")
        ax.set_xticks(range(len(order)), labels, fontsize=7.5)
        ax.set_title(f"{h}-minute horizon", fontsize=9.5)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("PR-AUC, test year (dotted: base rate)")
    axes[0].legend(fontsize=8, loc="upper center", bbox_to_anchor=(1.05, -0.16), ncol=2)
    g = gain[(gain.model == "lgb") & gain.subset.isin(["all", "rainy (rain at target time)"])]
    txt = "; ".join(f"{r.h} min, {('all slots' if r.subset == 'all' else 'rainy slots')}: {r.pr_auc_gain:+.4f} "
                    f"[{r.lo:+.4f}, {r.hi:+.4f}]" for r in g.itertuples())
    fig.suptitle("Early warning of unusually low availability: what weather adds beyond current taxi numbers",
                 x=0.01, ha="left", fontsize=10.5)
    fig.text(0.01, 0.915, f"LightGBM PR-AUC gain from weather, 95% day-bootstrap CI. {txt}", fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.91))
    save(fig, "forecast_pr_auc", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall and 2-hour forecasts. "
         "Test year Oct 2025 - Sep 2026, scored once. Low = deficit >= 50% where expected >= 4.")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["features", "tune", "fit", "evaluate", "charts"])
    ap.add_argument("--h", type=int, nargs="*", default=list(HORIZONS))
    a = ap.parse_args()
    if a.part == "fit":
        return part_fit(horizons=a.h)
    {"features": part_features, "tune": part_tune, "evaluate": part_evaluate, "charts": charts}[a.part]()


if __name__ == "__main__":
    main()
