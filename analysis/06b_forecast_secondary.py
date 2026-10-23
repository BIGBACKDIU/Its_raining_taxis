"""Secondary forecasting analysis S1 - added after the first test-year scoring (pre-registered in
outputs/decisions.md, items 55-64, committed before this code was run).

Asks whether weather adds more early-warning skill when the "low" label is noise-aware and when vacant taxis are
aggregated to larger units. Scales: 1 km cells, 2 km blocks (2 x 2 eligible cells), planning areas.
Labels: deficit >= 0.5 (baseline >= 4) and "below the 5th percentile of a negative binomial with mean = baseline"
(one NB2 dispersion per scale, fitted on the fit period). Horizons 30, 60, 120 minutes. Models: persistence and
LightGBM with / without weather (primary tuned settings; boosting rounds by early stopping on the calibration
period). Test year scored once more for S1.

Every output is labelled "secondary analysis (S1), added after first test scoring".

Parts: --part build | features | fit --scale ... | evaluate | notes
Outputs: data/interim/s1_* (not in git), outputs/tables/s1_*.csv, outputs/figures/s1_weather_gain.*
"""
from __future__ import annotations

import argparse
import gc
import importlib
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import special, stats
from scipy.optimize import minimize_scalar

from analysis.common import CALIB, FIT, INTERIM, MUTED, SEED, TABLES, TEST, log_test_scoring, save, style
from analysis.fc_eval import k_for, lead_summary, lead_times, topk_alerts

P = importlib.import_module("analysis.06_forecast")
LABEL = "Secondary analysis (S1), added after first test scoring"
SCALES = ("1km", "2km", "pa")
SCALE_NAMES = {"1km": "1 km cells", "2km": "2 km blocks", "pa": "Planning areas"}
HORIZONS = (30, 60, 120)
TARGETS = ("def", "nb")
TARGET_NAMES = {"def": "deficit >= 50%", "nb": "below NB 5th percentile"}
YEARS = range(2022, 2027)
FIT_FRAC = {"1km": 0.35, "2km": 0.35, "pa": 1.0}
CELL_COLS = ["ts", "cell", "vacant", "vacant_lag1", "vacant_lag2", "baseline", "citywide", "glitch", "drop_main",
             "how", "hod", "dow", "month", "daytype", "school_holiday", "mmh", "mmh_lag1", "mmh_lag2", "mmh_3g",
             "rain_2km", "rain_ring", "wet_min", "dry_min", "wet5_min", "dry5_min", "mmh_island", "gauges_wet_share",
             "fc_code", "fc_age_min"]
BASE_F = ["log_y0", "log_y1", "log_y2", "pattern_t", "pattern_h", "log_pattern_ratio", "lev_t", "lev_1d", "lev_7d",
          "seasonal_h", "deficit_feasible_t", "nbtail_feasible_t", "log_citywide", "citywide_change", "clim_def",
          "clim_nb", "hod_h", "dow_h", "daytype", "month", "school_holiday", "n_cells", "unit_cat"]
WEATHER_F = ["mmh_mean", "mmh_max", "lag1_mean", "lag2_mean", "mmh3g_mean", "rain2km_mean", "ring_mean",
             "wet_min_mean", "dry_min_mean", "wet5_max", "dry5_min", "mmh_island", "gauges_wet_share", "fc_max",
             "fc_nb_max", "fc_age_mean"]
ALERT_RATE = 0.05


# ============================================================================= units, levels, unit panels
def unit_map(scale):
    c = pd.read_parquet(INTERIM / "cells.parquet")
    c = c[c.eligible]
    if scale == "1km":
        u = c.cell
    elif scale == "2km":
        u = (c.cx // 2) * 1000 + (c.cy // 2)
    else:
        u = pd.Series(pd.factorize(c.planning_area)[0], index=c.index)
    return pd.Series(u.values.astype(int), index=c.cell.values)


def levels_and_fcmax():
    """Citywide coverage level per snapshot (as primary) and, per cell, the max forecast code within 5 km."""
    f1, f2 = INTERIM / "s1_levels.parquet", INTERIM / "s1_fcmax.parquet"
    if f1.exists() and f2.exists():
        return pd.read_parquet(f1), pd.read_parquet(f2)
    pat = P.pattern_table()
    cells, nb5 = P.forecast_neighbours()
    snaps, fcs = [], []
    for y in range(2021, 2027):
        p = pd.read_parquet(INTERIM / f"panel30_{y}.parquet", columns=["ts", "cell", "vacant", "glitch", "how", "month",
                                                                       "citywide", "fc_code"])
        p = p.merge(pat, on=["cell", "how", "month"], how="left")
        snaps.append(p[~p.glitch].groupby("ts").agg(v=("vacant", "sum"), pt=("pattern", "sum"), cw=("citywide", "first")))
        fc = p.pivot_table(index="ts", columns="cell", values="fc_code", aggfunc="first").reindex(columns=cells)
        F = fc.values.astype("float32")
        F[np.isnan(F)] = -1
        fmax = np.stack([F[:, nb5[j]].max(1) for j in range(len(cells))], axis=1).astype("int8")
        fcs.append(pd.DataFrame(fmax, index=fc.index, columns=cells).stack().rename("fc_code_nb5").reset_index()
                   .rename(columns={"level_1": "cell"}))
        del p
        gc.collect()
    s = pd.concat(snaps).sort_index()
    s["lev_t"] = s.v / s.pt
    s["lev_1d"] = s.lev_t.rolling("1D").median()
    s["lev_7d"] = s.lev_t.rolling("7D").median()
    s["citywide_change"] = s.cw / s.cw.shift(1)
    s.loc[s.index.to_series().diff() > pd.Timedelta(minutes=31), "citywide_change"] = np.nan
    lev = s[["lev_t", "lev_1d", "lev_7d", "citywide_change"]].astype("float32").reset_index()
    fcm = pd.concat(fcs, ignore_index=True)
    fcm.columns = ["ts", "cell", "fc_code_nb5"]
    lev.to_parquet(f1, index=False)
    fcm.to_parquet(f2, index=False)
    return lev, fcm


def unit_panel_year(scale, y, umap, pat, fcm):
    p = pd.read_parquet(INTERIM / f"panel30_{y}.parquet", columns=CELL_COLS)
    p = p.merge(pat, on=["cell", "how", "month"], how="left")
    p = p.merge(fcm, on=["ts", "cell"], how="left")
    p["unit"] = p.cell.map(umap).values
    g = p.groupby(["ts", "unit"], sort=True)
    u = g.agg(Y=("vacant", "sum"), Y1=("vacant_lag1", "sum"), Y1c=("vacant_lag1", "count"),
              Y2=("vacant_lag2", "sum"), Y2c=("vacant_lag2", "count"), n_cells=("cell", "size"),
              B=("baseline", "sum"), Bc=("baseline", "count"), pattern_u=("pattern", "sum"),
              mmh_mean=("mmh", "mean"), mmh_max=("mmh", "max"), lag1_mean=("mmh_lag1", "mean"),
              lag2_mean=("mmh_lag2", "mean"), mmh3g_mean=("mmh_3g", "mean"), rain2km_mean=("rain_2km", "mean"),
              ring_mean=("rain_ring", "mean"), wet_min_mean=("wet_min", "mean"), dry_min_mean=("dry_min", "mean"),
              wet5_max=("wet5_min", "max"), dry5_min=("dry5_min", "min"), fc_max=("fc_code", "max"),
              fc_nb_max=("fc_code_nb5", "max"), fc_age_mean=("fc_age_min", "mean")) if scale != "1km" else None
    if scale == "1km":
        u = p.rename(columns={"vacant": "Y", "vacant_lag1": "Y1", "vacant_lag2": "Y2", "mmh_lag1": "lag1_mean",
                              "mmh_lag2": "lag2_mean", "mmh_3g": "mmh3g_mean", "rain_2km": "rain2km_mean",
                              "rain_ring": "ring_mean", "wet_min": "wet_min_mean", "dry_min": "dry_min_mean",
                              "wet5_min": "wet5_max", "dry5_min": "dry5_min", "fc_code": "fc_max",
                              "fc_code_nb5": "fc_nb_max", "fc_age_min": "fc_age_mean"})
        u["mmh_mean"] = u.mmh
        u["mmh_max"] = u.mmh
        u["n_cells"] = 1
        u["B"] = u.baseline
        u["pattern_u"] = u.pattern
        u = u.set_index(["ts", "unit"])
    else:
        # a unit-level sum is missing if any member cell is missing
        u["Y1"] = u.Y1.where(u.Y1c == u.n_cells)
        u["Y2"] = u.Y2.where(u.Y2c == u.n_cells)
        u["B"] = u.B.where(u.Bc == u.n_cells)
    snap = p.groupby("ts").agg(citywide=("citywide", "first"), glitch=("glitch", "first"), drop_main=("drop_main", "first"),
                               how=("how", "first"), hod=("hod", "first"), dow=("dow", "first"), month=("month", "first"),
                               daytype=("daytype", "first"), school_holiday=("school_holiday", "first"),
                               mmh_island=("mmh_island", "first"), gauges_wet_share=("gauges_wet_share", "first"))
    keep = ["Y", "Y1", "Y2", "B", "pattern_u", "n_cells"] + [c for c in WEATHER_F if c not in ("mmh_island", "gauges_wet_share")]
    u = u[keep].reset_index().join(snap, on="ts")
    for c in u.columns:
        if u[c].dtype == "float64":
            u[c] = u[c].astype("float32")
    return u


# ============================================================================= negative binomial
def nb_params(mu, alpha):
    n = 1.0 / alpha
    return n, n / (n + np.asarray(mu, float))


def fit_alpha(y, mu):
    y, mu = np.asarray(y, float), np.asarray(mu, float)

    def nll(la):
        a = np.exp(la)
        n = 1 / a
        return -np.sum(special.gammaln(y + n) - special.gammaln(n) - special.gammaln(y + 1)
                       + n * np.log(n / (n + mu)) + y * np.log(mu / (n + mu)))

    r = minimize_scalar(nll, bounds=(-9, 3), method="bounded")
    return float(np.exp(r.x))


def part_build():
    lev, fcm = levels_and_fcmax()
    pat = P.pattern_table()
    out = {}
    rng = np.random.default_rng(SEED)
    for scale in SCALES:
        umap = unit_map(scale)
        for y in YEARS:
            t0 = time.time()
            u = unit_panel_year(scale, y, umap, pat, fcm)
            u.to_parquet(INTERIM / f"s1_{scale}_{y}.parquet", index=False)
            print(f"{scale} {y}: {len(u):,} unit-snapshots {time.time() - t0:.0f}s", flush=True)
            del u
            gc.collect()
        # NB dispersion on fit-period main-sample unit-snapshots
        fit = pd.concat([pd.read_parquet(INTERIM / f"s1_{scale}_{y}.parquet", columns=["ts", "Y", "B", "drop_main"],
                                         filters=[("ts", ">=", FIT[0]), ("ts", "<=", FIT[1])]) for y in range(2022, 2026)])
        fit = fit[~fit.drop_main & fit.B.notna() & (fit.B > 0)]
        if len(fit) > 2_000_000:
            fit = fit.iloc[rng.choice(len(fit), 2_000_000, replace=False)]
        a = fit_alpha(fit.Y.values, fit.B.values)
        out[scale] = {"alpha": a, "rows_used": int(len(fit)), "units": int(umap.nunique())}
        print(scale, out[scale], flush=True)
        # labels
        clim_rows = []
        for y in YEARS:
            f = INTERIM / f"s1_{scale}_{y}.parquet"
            u = pd.read_parquet(f)
            ok = u.B.notna() & (u.B > 0)
            n, pp = nb_params(u.B.where(ok, 1).values, a)
            q05 = stats.nbinom.ppf(0.05, n, pp)
            u["low_nb"] = pd.array(np.where(ok, u.Y.values < q05, pd.NA), dtype="boolean")
            dfc = (u.B - u.Y) / np.maximum(1, u.B)
            u["low_def"] = pd.array(np.where(ok & (u.B >= 4), dfc >= 0.5, pd.NA), dtype="boolean")
            u.to_parquet(f, index=False)
            m = (u.ts >= FIT[0]) & (u.ts <= FIT[1]) & ~u.drop_main
            if m.any():
                clim_rows.append(u[m].groupby(["unit", "hod", "daytype"]).agg(
                    def_s=("low_def", "sum"), def_n=("low_def", "count"), nb_s=("low_nb", "sum"), nb_n=("low_nb", "count")))
        c = pd.concat(clim_rows).groupby(level=[0, 1, 2]).sum()
        c["clim_def"] = (c.def_s + 1) / (c.def_n + 6)
        c["clim_nb"] = (c.nb_s + 0.3) / (c.nb_n + 6)
        c[["clim_def", "clim_nb"]].reset_index().to_parquet(INTERIM / f"s1_{scale}_clim.parquet", index=False)
    pd.DataFrame(out).T.to_csv(TABLES / "s1_nb_dispersion.csv")


# ============================================================================= features
def part_features():
    lev, _ = levels_and_fcmax()
    lev = lev.set_index("ts")
    alpha = pd.read_csv(TABLES / "s1_nb_dispersion.csv", index_col=0).alpha
    rng = np.random.default_rng(SEED)
    for scale in SCALES:
        clim = pd.read_parquet(INTERIM / f"s1_{scale}_clim.parquet")
        a = alpha[scale]
        for h in HORIZONS:
            for split, (s0, s1) in (("fit", FIT), ("calib", CALIB), ("test", TEST)):
                parts = []
                for y in range(s0.year, s1.year + 1):
                    U = pd.read_parquet(INTERIM / f"s1_{scale}_{y}.parquet")
                    nxt = INTERIM / f"s1_{scale}_{y + 1}.parquet"
                    if nxt.exists():
                        U = pd.concat([U, pd.read_parquet(nxt, filters=[("ts", "<=", pd.Timestamp(f"{y + 1}-01-01")
                                                                          + pd.Timedelta(minutes=h))])], ignore_index=True)
                    parts.append(features_chunk(U, y, h, split, s0, s1, scale, clim, lev, a, rng))
                    del U
                    gc.collect()
                d = pd.concat(parts, ignore_index=True)
                d.to_parquet(INTERIM / f"s1_fc_{scale}_h{h}_{split}.parquet", index=False)
                print(f"{scale} h={h} {split}: {len(d):,}", flush=True)
                del d, parts
                gc.collect()


def features_chunk(U, y, h, split, s0, s1, scale, clim, lev, a, rng):
    U = U.join(lev, on="ts")
    tgt = U[["ts", "unit", "Y", "B", "low_def", "low_nb", "drop_main", "mmh_mean", "pattern_u", "hod", "dow"]].copy()
    tgt["ts"] = tgt.ts - pd.Timedelta(minutes=h)
    tgt.columns = ["ts", "unit", "y_h", "B_h", "y_def", "y_nb", "drop_h", "mmh_h", "pattern_h", "hod_h", "dow_h"]
    lo, hi = max(s0, pd.Timestamp(f"{y}-01-01")), min(s1, pd.Timestamp(f"{y}-12-31 23:59"))
    iss = U[(U.ts >= lo) & (U.ts <= hi) & ~U.drop_main]
    if split == "fit" and FIT_FRAC[scale] < 1:
        times = iss.ts.unique()
        iss = iss[iss.ts.isin(rng.choice(times, int(len(times) * FIT_FRAC[scale]), replace=False))]
    d = iss.merge(tgt, on=["ts", "unit"], how="inner")
    d = d[~d.drop_h & d.pattern_h.notna()].drop(columns=["drop_h"])
    d = d.merge(clim.rename(columns={"hod": "hod_h"}), on=["unit", "hod_h", "daytype"], how="left")
    d["clim_def"] = d.clim_def.fillna(0.17)
    d["clim_nb"] = d.clim_nb.fillna(0.05)
    d["log_y0"], d["log_y1"], d["log_y2"] = np.log1p(d.Y), np.log1p(d.Y1), np.log1p(d.Y2)
    d["pattern_t"] = d.pattern_u
    d["log_pattern_ratio"] = np.log(d.pattern_h / d.pattern_t)
    d["seasonal_h"] = d.pattern_h * d.lev_7d
    sea_t = (d.pattern_t * d.lev_7d).astype(float)
    d["deficit_feasible_t"] = (sea_t - d.Y) / np.maximum(1, sea_t)
    n, pp = nb_params(sea_t.clip(lower=1e-3).values, a)
    d["nbtail_feasible_t"] = stats.nbinom.cdf(d.Y.values, n, pp).astype("float32")
    d["log_citywide"] = np.log(d.citywide.astype(float))
    d["unit_cat"] = d.unit.astype("int32")
    keep = ["ts", "unit", "y_h", "B_h", "y_def", "y_nb", "mmh_h"] + BASE_F + WEATHER_F
    d = d[list(dict.fromkeys(keep))]
    for c in d.columns:
        if d[c].dtype == "float64":
            d[c] = d[c].astype("float32")
    return d


# ============================================================================= fit and predict
def part_fit(scales):
    import lightgbm as lgb
    tuned = json.loads((TABLES / "forecast_tuning.json").read_text())["binary"]["params"]
    prm = {k: v for k, v in tuned.items() if k != "num_boost_round"}
    rng = np.random.default_rng(SEED)
    rows = []
    for scale in scales:
        for h in HORIZONS:
            tr = pd.read_parquet(INTERIM / f"s1_fc_{scale}_h{h}_fit.parquet")
            ca = pd.read_parquet(INTERIM / f"s1_fc_{scale}_h{h}_calib.parquet")
            te = pd.read_parquet(INTERIM / f"s1_fc_{scale}_h{h}_test.parquet")
            out = {s: d[["ts", "unit", "y_def", "y_nb", "mmh_h", "deficit_feasible_t", "nbtail_feasible_t"]].copy()
                   for s, d in (("calib", ca), ("test", te))}
            for s in out.values():
                s["score_def_persistence"] = s.deficit_feasible_t
                s["score_nb_persistence"] = 1 - s.nbtail_feasible_t
            for target in TARGETS:
                yc = f"y_{target}"
                ok = np.flatnonzero(tr[yc].notna().values)
                idx = np.sort(rng.choice(ok, min(3_000_000, len(ok)), replace=False))
                okc = ca[yc].notna().values
                for weather in (False, True):
                    F = BASE_F + (WEATHER_F if weather else [])
                    tag = "weather" if weather else "no_weather"
                    t0 = time.time()
                    dt = lgb.Dataset(tr.iloc[idx][F], tr[yc].values[idx].astype(float), categorical_feature=["unit_cat"])
                    dv = lgb.Dataset(ca.loc[okc, F], ca.loc[okc, yc].astype(float), reference=dt)
                    m = lgb.train(P.lgb_params("binary", prm), dt, num_boost_round=2000, valid_sets=[dv],
                                  callbacks=[lgb.early_stopping(50, verbose=False)])
                    for s, d in (("calib", ca), ("test", te)):
                        out[s][f"score_{target}_lgb_{tag}"] = m.predict(d[F], num_iteration=m.best_iteration).astype("float32")
                    rows.append({"scale": scale, "h": h, "target": target, "model": f"lgb_{tag}",
                                 "rounds": m.best_iteration, "train_rows": len(idx), "seconds": round(time.time() - t0)})
                    print(rows[-1], flush=True)
            for s, d in out.items():
                d.to_parquet(INTERIM / f"s1_pred_{scale}_h{h}_{s}.parquet", index=False)
            log_test_scoring(f"06b_forecast_secondary.py --part fit --scale {scale}", f"S1 test-year predictions h={h}",
                             "S1", len(te))
            stamp = INTERIM / "s1_test_scored.txt"
            if not stamp.exists():
                stamp.write_text(datetime.now().isoformat(timespec="seconds"))
            del tr, ca, te, out
            gc.collect()
    f = TABLES / "s1_models.csv"
    prev = pd.read_csv(f) if f.exists() else pd.DataFrame()
    pd.concat([prev, pd.DataFrame(rows)]).drop_duplicates(["scale", "h", "target", "model"], keep="last").to_csv(f, index=False)


# ============================================================================= evaluate
def part_evaluate(n_boot=1000):
    from sklearn.metrics import average_precision_score
    log_test_scoring("06b_forecast_secondary.py --part evaluate", "S1 test-year metrics (retrospective labels)", "S1")
    rng = np.random.default_rng(SEED)
    res, base = [], []
    for scale in SCALES:
        # base rates by period
        for split, (s0, s1) in (("fit", FIT), ("calib", CALIB), ("test", TEST)):
            u = pd.concat([pd.read_parquet(INTERIM / f"s1_{scale}_{y}.parquet", columns=["ts", "low_def", "low_nb", "drop_main"],
                                           filters=[("ts", ">=", s0), ("ts", "<=", s1)]) for y in YEARS])
            u = u[~u.drop_main]
            base.append({"scale": scale, "period": split, "base_rate_def": float(u.low_def.mean()),
                         "base_rate_nb": float(u.low_nb.mean()), "defined_share_def": float(u.low_def.notna().mean()),
                         "unit_snapshots": int(len(u))})
        for h in HORIZONS:
            ca = pd.read_parquet(INTERIM / f"s1_pred_{scale}_h{h}_calib.parquet")
            te = pd.read_parquet(INTERIM / f"s1_pred_{scale}_h{h}_test.parquet")
            for target in TARGETS:
                yc = f"y_{target}"
                cc, tt = ca[ca[yc].notna()], te[te[yc].notna()].reset_index(drop=True)
                models = [f"score_{target}_persistence", f"score_{target}_lgb_no_weather", f"score_{target}_lgb_weather"]
                thr = {m: float(np.quantile(cc[m].astype(float), 1 - ALERT_RATE)) for m in models}
                days = tt.ts.dt.normalize()
                ud = np.sort(days.unique())
                di = np.searchsorted(ud, days.values)
                W = rng.multinomial(len(ud), np.full(len(ud), 1 / len(ud)), size=n_boot).astype(float)
                rainy = (tt.mmh_h.fillna(0) > 0).values
                for sub, msk in (("all", np.ones(len(tt), bool)), ("rainy", rainy)):
                    y = tt[yc].values[msk].astype(int)
                    r = {"analysis": LABEL, "scale": scale, "h": h, "target": target, "subset": sub,
                         "rows_test": int(msk.sum()), "base_rate_test": float(y.mean())}
                    cmsk = (cc.mmh_h.fillna(0) > 0).values if sub == "rainy" else np.ones(len(cc), bool)
                    for m in models:
                        short = m.replace(f"score_{target}_", "")
                        r[f"pr_auc_calib_{short}"] = float(average_precision_score(cc[yc].values[cmsk].astype(int),
                                                                                   cc[m].values[cmsk]))
                        r[f"pr_auc_test_{short}"] = float(average_precision_score(y, tt[m].values[msk]))
                    a = P.binned_ap(tt[models[2]].values[msk], y, di[msk], len(ud), W)
                    b = P.binned_ap(tt[models[1]].values[msk], y, di[msk], len(ud), W)
                    diffs = a[1] - b[1]
                    r["weather_gain"] = r["pr_auc_test_lgb_weather"] - r["pr_auc_test_lgb_no_weather"]
                    r["gain_lo"], r["gain_hi"] = float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))
                    r["materially_useful"] = bool(r["weather_gain"] >= 0.01 and r["gain_lo"] > 0)
                    r["detectable"] = bool(r["gain_lo"] > 0 or r["gain_hi"] < 0)
                    # lead times and fixed-workload metrics: see analysis/06d_label_versions.py
                    res.append(r)
                    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()
                           if k in ("scale", "h", "target", "subset", "base_rate_test", "pr_auc_test_lgb_no_weather",
                                    "pr_auc_test_lgb_weather", "weather_gain", "gain_lo", "gain_hi")}, flush=True)
    b = pd.DataFrame(base)
    b.insert(0, "analysis", LABEL)
    b.to_csv(TABLES / "s1_base_rates.csv", index=False, float_format="%.4f")
    pd.DataFrame(res).to_csv(TABLES / "s1_results.csv", index=False, float_format="%.5f")
    chart()


def chart():
    import matplotlib.pyplot as plt
    style()
    r = pd.read_csv(TABLES / "s1_results.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    colors = {"1km": "#a9c9ef", "2km": "#2a78d6", "pa": "#0d2f5c"}
    for ax, target in zip(axes, TARGETS):
        k = 0
        ticks, labels = [], []
        for h in HORIZONS:
            for sub in ("all", "rainy"):
                for j, scale in enumerate(SCALES):
                    t = r[(r.target == target) & (r.h == h) & (r.subset == sub) & (r.scale == scale)]
                    if t.empty:
                        continue
                    t = t.iloc[0]
                    x = k + j * 0.25
                    ax.errorbar(x, t.weather_gain, yerr=[[t.weather_gain - t.gain_lo], [t.gain_hi - t.weather_gain]],
                                fmt="o", ms=5, capsize=2, color=colors[scale],
                                label=SCALE_NAMES[scale] if (h == 30 and sub == "all") else None)
                ticks.append(k + 0.25)
                labels.append(f"{h} min\n{sub}")
                k += 1
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.axhline(0.01, color=MUTED, lw=0.8, ls="--")
        ax.set_xticks(ticks, labels, fontsize=7.5)
        ax.set_title(f"Label: {TARGET_NAMES[target]}", fontsize=9.5)
    axes[0].set_ylabel("PR-AUC gain from weather, test year\n(dashed: pre-registered materiality, 0.01)")
    axes[0].legend(fontsize=8, loc="lower left")
    fig.suptitle("S1 (secondary, added after first test scoring): weather's added early-warning skill by scale, "
                 "horizon and label", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "s1_weather_gain", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall and 2-hour forecasts. "
         "LightGBM with vs without weather; 95% CI from 1,000 day-block bootstrap draws. Test Oct 2025 - Sep 2026.")
    plt.close(fig)


# ============================================================================= notes on primary outputs
def part_notes():
    m = pd.read_csv(TABLES / "forecast_metrics.csv")
    post = {"rain starts between issue and target", "heavy rain at target time",
            "cell dry at issue, heavier rain 2-5 km away"}
    m["subset_status"] = np.where(m.subset.isin(post), "post-hoc subset (added after first test scoring)",
                                  "pre-specified")
    m.to_csv(TABLES / "forecast_metrics.csv", index=False, float_format="%.5f")
    g = pd.read_csv(TABLES / "forecast_weather_gain.csv")
    g["subset_status"] = np.where(g.subset.isin(post), "post-hoc subset (added after first test scoring)", "pre-specified")
    g.to_csv(TABLES / "forecast_weather_gain.csv", index=False, float_format="%.5f")
    (TABLES / "forecast_README.md").write_text("""# Forecasting tables: how to read them

- `forecast_*.csv` = primary step-6 analysis, pre-specified. Test year (Oct 2025 - Sep 2026) first scored
  2026-10-23 00:08:41; no model was refitted afterwards.
- Subsets marked `post-hoc subset (added after first test scoring)` in `forecast_metrics.csv` and
  `forecast_weather_gain.csv` ("rain starts between issue and target", "heavy rain at target time",
  "cell dry at issue, heavier rain 2-5 km away") were added after the first test scoring. Read them as
  exploratory.
- `s1_*.csv` = secondary analysis S1, added after first test scoring and pre-registered in
  `outputs/decisions.md` (items 55-64) before it was run.
- **Test-year labels.** The baseline that defines "low" in the test year uses each test regime's own level,
  estimated from that regime's own rows: the fit period contains no data from those regimes. Model inputs never
  use that baseline.
- **Base-rate shift.** The primary 1 km deficit label occurs in 18.4% of eligible cell-snapshots in the
  calibration period (Apr - Sep 2025) and 26.5% in the test year. Precision and recall at a fixed alert
  workload, and calibrated probabilities, are affected by this shift; PR-AUC values should be compared with
  each period's base rate.
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["build", "features", "fit", "evaluate", "chart", "notes"])
    ap.add_argument("--scale", nargs="*", default=list(SCALES))
    a = ap.parse_args()
    if a.part == "fit":
        return part_fit(a.scale)
    {"build": part_build, "features": part_features, "evaluate": part_evaluate, "chart": chart, "notes": part_notes}[a.part]()


if __name__ == "__main__":
    main()
