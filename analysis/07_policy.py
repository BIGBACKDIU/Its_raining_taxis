"""Step 7: conditional driver-repositioning policy (HANDOFF section 6, step 7) plus a rain planning layer.

Policy (PuLP, CBC), solved at a decision time t for lead time h:
    maximise  sum_j w_j sum_k r_jk y_jk  -  lambda sum_ij t_ij x_ij
    r_jk = S_j(k-1) - S_j(k),  S_j(m) = E[max(0, base_j - (Y_j + m))] / max(1, base_j),  Y_j ~ Poisson(mu_j)
    sum_k y_jk = sum_i x_ij,  0 <= y_jk <= 1,  sum_j x_ij <= movable_i,  sum_ij x_ij <= N,  x_ij integer >= 0,
    x_ij = 0 if t_ij > h.
All inputs are known at t (rules in outputs/decisions.md, items 67-71). Results describe vacant-taxi availability;
"expected shortfall reduction" is a model quantity, not served demand.

Planning layer: which planning areas and hours lose the most availability when rain is forecast (and when heavy
rain falls), absolute and share, from the fit-period association data.

Usage: .venv/bin/python -m analysis.07_policy --part choose | evaluate | planning | charts
Outputs: outputs/tables/policy_*.csv, planning_*.csv, figures policy_*, planning_*.
"""
from __future__ import annotations

import argparse
import gc
import importlib
import json
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pulp
from scipy.stats import poisson

from analysis.common import (BLUE, BLUE_DARK, FIT, INTERIM, MUTED, ORANGE, SEED, STATIC, TABLES, save, style)
from pipeline.grid import to_xy

SPEED_KMH = {"dry": 30.0, "rain": 20.0}
DETOUR = 1.3
BASE = {"N": 200, "lam": 0.005, "h": 60, "congestion": "observed", "weights": "equal"}
SENS = [("N", 50), ("N", 500), ("lam", 0.001), ("lam", 0.02), ("h", 30), ("congestion", "dry"),
        ("congestion", "rain"), ("weights", "station"), ("weights", "landuse")]
K_MAX = 20
S0_MIN = 0.05


# ============================================================================= inputs
def cells_info():
    c = pd.read_parquet(INTERIM / "cells.parquet")
    c = c[c.eligible].set_index("cell")
    x, y = to_xy(c.lon.values, c.lat.values)
    c["x"], c["y"] = x, y
    st = 1 + c.mrt_exits_in_cell
    lu = np.where(c.city_centre, 2.0, 1.0)
    c["w_equal"] = 1.0
    c["w_station"] = st / st.mean()
    c["w_landuse"] = lu / lu.mean()
    return c


def cdg_share():
    s = pd.read_csv(STATIC / "lta_cdg_share_monthly.csv", parse_dates=["month"]).set_index("month").cdg_share
    return s


def decision_frame(h, split, use_weather):
    pr = pd.read_parquet(INTERIM / f"fc_pred_h{h}_{split}.parquet",
                         columns=["ts", "cell", "y_low", "y_count", "vacant", "seasonal_h",
                                  "count_lgb_weather", "count_lgb_no_weather"])
    f = pd.read_parquet(INTERIM / f"fc_h{h}_{split}.parquet", columns=["ts", "cell", "pattern_t", "lev_7d", "mmh_island"])
    d = pr.merge(f, on=["ts", "cell"], how="left")
    d["mu"] = d.count_lgb_weather if use_weather else d.count_lgb_no_weather
    d["base_j"] = d.seasonal_h
    d["base_i"] = d.pattern_t * d.lev_7d
    return d


def sample_times(d, n_rainy, n_dry, seed=SEED):
    snap = d.groupby("ts").mmh_island.first().fillna(0)
    rng = np.random.default_rng(seed)
    wet = snap.index[snap > 0].values
    dry = snap.index[snap == 0].values
    return (np.sort(rng.choice(wet, min(n_rainy, len(wet)), replace=False)),
            np.sort(rng.choice(dry, min(n_dry, len(dry)), replace=False)))


def shortfall_values(base, mu, kmax=K_MAX):
    """S(m) for m = 0..kmax (rows: destinations) and the marginal values r_k = S(k-1) - S(k)."""
    ys = np.arange(0, int(np.ceil(base.max())) + 2)
    pmf = poisson.pmf(ys[None, :], mu[:, None])                       # (J, Y)
    S = np.zeros((len(base), kmax + 1))
    for m in range(kmax + 1):
        gap = np.maximum(0, base[:, None] - (ys[None, :] + m))
        S[:, m] = (gap * pmf).sum(1) / np.maximum(1, base)
    return S, S[:, :-1] - S[:, 1:]


# ============================================================================= one decision
def solve(snap: pd.DataFrame, cells, share, N, lam, h, congestion, weights, rain_now):
    s = snap.set_index("cell")
    movable = np.floor(share * np.maximum(0, s.vacant - s.base_i)).astype(int)
    orig = movable[movable > 0]
    S, r = shortfall_values(s.base_j.values, s.mu.values)
    s0 = pd.Series(S[:, 0], index=s.index)
    stage = cells.taxi_stands_300m.reindex(s.index).fillna(0) > 0
    dest_mask = (s.base_j >= 4) & stage & (s0 >= S0_MIN)
    dest = s.index[dest_mask.values]
    if len(orig) == 0 or len(dest) == 0:
        return {"moved": 0, "objective": 0.0, "dest": {}, "n_dest_candidates": int(len(dest))}
    cond = ("rain" if rain_now else "dry") if congestion == "observed" else congestion
    v = SPEED_KMH[cond] * 1000 / 60                                    # metres per minute
    ox, oy = cells.loc[orig.index, "x"].values, cells.loc[orig.index, "y"].values
    dx, dy = cells.loc[dest, "x"].values, cells.loc[dest, "y"].values
    T = DETOUR * np.hypot(ox[:, None] - dx[None, :], oy[:, None] - dy[None, :]) / v
    pos = {c: k for k, c in enumerate(s.index)}
    w = cells.loc[dest, f"w_{weights}"].values
    prob = pulp.LpProblem("reposition", pulp.LpMaximize)
    pairs = [(a, b) for a in range(len(orig)) for b in range(len(dest)) if T[a, b] <= h and orig.index[a] != dest[b]]
    if not pairs:
        return {"moved": 0, "objective": 0.0, "dest": {}, "n_dest_candidates": int(len(dest))}
    x = {(a, b): pulp.LpVariable(f"x_{a}_{b}", lowBound=0, cat="Integer") for a, b in pairs}
    kj = {b: max(1, min(K_MAX, int(np.ceil(s.base_j.loc[dest[b]])))) for b in range(len(dest))}
    yv = {(b, k): pulp.LpVariable(f"y_{b}_{k}", lowBound=0, upBound=1) for b in range(len(dest)) for k in range(kj[b])}
    prob += (pulp.lpSum(w[b] * r[pos[dest[b]], k] * yv[(b, k)] for (b, k) in yv)
             - lam * pulp.lpSum(T[a, b] * x[(a, b)] for (a, b) in pairs))
    inflow = {b: [] for b in range(len(dest))}
    outflow = {a: [] for a in range(len(orig))}
    for (a, b), var in x.items():
        inflow[b].append(var)
        outflow[a].append(var)
    for b in range(len(dest)):
        prob += pulp.lpSum(yv[(b, k)] for k in range(kj[b])) == pulp.lpSum(inflow[b])
    for a in range(len(orig)):
        if outflow[a]:
            prob += pulp.lpSum(outflow[a]) <= int(orig.iloc[a])
    prob += pulp.lpSum(x.values()) <= N
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=30))
    moves = {(orig.index[a], dest[b]): int(round(var.value() or 0)) for (a, b), var in x.items() if (var.value() or 0) > 0.5}
    got = {}
    for (i, j), n in moves.items():
        got[j] = got.get(j, 0) + n
    gain = sum(w[list(dest).index(j)] * r[pos[j], :min(n, K_MAX)].sum() for j, n in got.items())
    ttime = sum(T[list(orig.index).index(i), list(dest).index(j)] * n for (i, j), n in moves.items())
    return {"moved": int(sum(moves.values())), "objective": float(pulp.value(prob.objective) or 0),
            "expected_shortfall_reduction": float(gain), "taxi_minutes": float(ttime), "dest": got,
            "n_dest_candidates": int(len(dest)), "n_origins": int(len(orig)),
            "shortfall_before": float((s0.loc[dest] * w).sum())}


def run(d, times, cells, shares, cfg, label):
    rows, plans = [], []
    for t in times:
        snap = d[d.ts == t]
        if snap.empty:
            continue
        sh = float(shares.asof(pd.Timestamp(t)))
        rain_now = bool(snap.mmh_island.fillna(0).iloc[0] > 0)
        res = solve(snap, cells, sh, cfg["N"], cfg["lam"], cfg["h"], cfg["congestion"], cfg["weights"], rain_now)
        lowmap = snap.set_index("cell").y_low
        tgt = list(res["dest"])
        cand = snap[(snap.base_j >= 4)]
        rows.append({"setting": label, "ts": t, "rain_at_t": rain_now, "moved": res["moved"],
                     "n_targeted": len(tgt), "n_dest_candidates": res["n_dest_candidates"],
                     "expected_shortfall_reduction": res.get("expected_shortfall_reduction", 0.0),
                     "shortfall_before": res.get("shortfall_before", np.nan),
                     "taxi_minutes": res.get("taxi_minutes", 0.0),
                     "targeted_low_rate": float(lowmap.reindex(tgt).dropna().astype(float).mean()) if tgt else np.nan,
                     "candidates_low_rate": float(cand.y_low.dropna().astype(float).mean()) if len(cand) else np.nan,
                     "all_eligible_low_rate": float(snap.y_low.dropna().astype(float).mean())})
        for j, n in res["dest"].items():
            plans.append({"setting": label, "ts": t, "rain_at_t": rain_now, "cell": j, "taxis": n,
                          "low_at_target": lowmap.get(j)})
    return pd.DataFrame(rows), pd.DataFrame(plans)


# ============================================================================= parts
def part_choose():
    cells, shares = cells_info(), cdg_share()
    out = []
    for h in (60,):
        for use_weather in (False, True):
            d = decision_frame(h, "calib", use_weather)
            wet, dry = sample_times(d, 75, 75)
            r, _ = run(d, np.r_[wet, dry], cells, shares, dict(BASE, h=h), f"calib weather={use_weather}")
            out.append({"h": h, "weather": use_weather, "snapshots": len(r),
                        "targeted_low_rate": r.targeted_low_rate.mean(),
                        "candidates_low_rate": r.candidates_low_rate.mean(),
                        "expected_shortfall_reduction": r.expected_shortfall_reduction.mean()})
            print(out[-1], flush=True)
    o = pd.DataFrame(out)
    dev = {False: 1.2734, True: 1.2695}           # calibration Poisson deviance, h = 60 (decision 67)
    o["calib_poisson_deviance"] = o.weather.map(dev)
    keep = bool(o.set_index("weather").targeted_low_rate[True] > o.set_index("weather").targeted_low_rate[False]
                and dev[True] < dev[False])
    o["weather_kept"] = keep
    o.to_csv(TABLES / "policy_forecast_choice.csv", index=False, float_format="%.5f")
    print("weather kept in step 7:", keep)


def part_evaluate():
    cells, shares = cells_info(), cdg_share()
    keep = bool(pd.read_csv(TABLES / "policy_forecast_choice.csv").weather_kept.iloc[0])
    rows, plans = [], []
    t0 = time.time()
    d60 = decision_frame(60, "test", keep)
    wet, dry = sample_times(d60, 150, 150)
    r, p = run(d60, np.r_[wet, dry], cells, shares, BASE, "base")
    rows.append(r)
    plans.append(p)
    print("base", time.time() - t0, flush=True)
    sw, sd = wet[:50], dry[:50]
    for key, val in SENS:
        cfg = dict(BASE, **{key: val})
        d = decision_frame(30, "test", keep) if (key == "h") else d60
        r, p = run(d, np.r_[sw, sd], cells, shares, cfg, f"{key}={val}")
        rows.append(r)
        plans.append(p)
        print(key, val, f"{time.time() - t0:.0f}s", flush=True)
    R = pd.concat(rows)
    R.to_csv(TABLES / "policy_runs.csv", index=False, float_format="%.5f")
    P = pd.concat(plans)
    P.to_csv(TABLES / "policy_plans_long.csv", index=False)
    summary(R, P, cells)


def summary(R, P, cells):
    g = R.groupby(["setting", "rain_at_t"]).agg(snapshots=("ts", "size"), moved=("moved", "mean"),
                                                 targeted=("n_targeted", "mean"),
                                                 exp_shortfall_reduction=("expected_shortfall_reduction", "mean"),
                                                 shortfall_before=("shortfall_before", "mean"),
                                                 taxi_minutes=("taxi_minutes", "mean"),
                                                 targeted_low_rate=("targeted_low_rate", "mean"),
                                                 candidates_low_rate=("candidates_low_rate", "mean"),
                                                 all_eligible_low_rate=("all_eligible_low_rate", "mean")).reset_index()
    g["share_of_shortfall_removed"] = g.exp_shortfall_reduction / g.shortfall_before
    g.to_csv(TABLES / "policy_sensitivity.csv", index=False, float_format="%.4f")
    print(g.round(3).to_string())
    # ranked staging plans per weights scenario (test sample; base = equal weights)
    names = cells.planning_area
    out = []
    for setting in ("base", "weights=station", "weights=landuse"):
        q = P[P.setting == setting]
        n_snap = R[R.setting == setting].groupby("rain_at_t").size()
        for rain in (True, False):
            z = q[q.rain_at_t == rain].groupby("cell").agg(times_targeted=("ts", "nunique"), taxis=("taxis", "sum"),
                                                          low_rate=("low_at_target", lambda v: pd.Series(v).dropna().astype(float).mean()))
            z["share_of_decisions"] = z.times_targeted / n_snap.get(rain, np.nan)
            z["taxis_per_decision"] = z.taxis / n_snap.get(rain, np.nan)
            z = z.sort_values("taxis", ascending=False).head(15).reset_index()
            z["planning_area"] = z.cell.map(names)
            z["rank"] = np.arange(1, len(z) + 1)
            z.insert(0, "scenario", setting.replace("base", "weights=equal"))
            z.insert(1, "rain_at_decision", rain)
            out.append(z)
    pd.concat(out).to_csv(TABLES / "policy_staging_plans.csv", index=False, float_format="%.4f")


def part_planning(n_boot=500):
    inf = importlib.import_module("analysis.04_inference")
    from analysis.common import load_panel
    cols = ["ts", "cell", "vacant", "rain_band", "mmh", "mmh_lag1", "mmh_lag2", "how", "month", "ym", "regime_id",
            "daytype", "drop_main", "baseline", "fc_code", "hod"]
    p = load_panel(range(2022, 2026), columns=cols, filters=[("ts", ">=", FIT[0]), ("ts", "<=", FIT[1])])
    p = p[~p.drop_main & (p.rain_band >= 0) & p.mmh_lag1.notna() & p.mmh_lag2.notna() & p.baseline.notna()].reset_index(drop=True)
    f0, _ = inf.fit0(p)
    p["fit0"] = f0
    p = p[np.isfinite(p.fit0)].reset_index(drop=True)
    tot = p.groupby("ts")[["vacant", "fit0"]].transform("sum")
    p["fit0s"] = p.fit0 * tot.vacant / tot.fit0                          # share benchmark
    pa = pd.read_parquet(INTERIM / "cells.parquet").set_index("cell").planning_area
    p["pa"] = p.cell.map(pa)
    h = p.hod // 2
    p["band"] = np.select([h < 7, h < 10, h < 17, h < 20], ["00-07", "07-10", "10-17", "17-20"], "20-24")
    p["day"] = np.where(p.daytype == 0, "weekday", "weekend/holiday")
    p["date"] = p.ts.dt.normalize()
    rng = np.random.default_rng(SEED)
    rows = []
    n_cells = p.groupby("pa").cell.nunique()
    for cond, m in (("NEA forecast showers/thundery (issued before t)", p.fc_code.values >= 2),
                    ("observed heavy rain (> 10 mm/h)", p.rain_band.values == 3)):
        q = p[m].reset_index(drop=True)
        days = np.sort(q.date.unique())
        di = np.searchsorted(days, q.date.values)
        W = rng.multinomial(len(days), np.full(len(days), 1 / len(days)), size=n_boot).astype(float)
        for (a, b, dd), g in q.groupby(["pa", "band", "day"]).groups.items():
            idx = np.asarray(g)
            if len(idx) < 200:
                continue
            dsel = di[idx]
            V = np.bincount(dsel, q.vacant.values[idx], len(days))
            F = np.bincount(dsel, q.fit0.values[idx], len(days))
            Fs = np.bincount(dsel, q.fit0s.values[idx], len(days))
            n_slots = q.ts.values[idx].astype("datetime64[m]")
            n_slots = len(np.unique(n_slots))
            abs_loss = (F.sum() - V.sum()) / n_slots                       # taxis per half hour, whole area
            pct = V.sum() / F.sum() - 1
            share = V.sum() / Fs.sum() - 1
            bp = (W @ V) / (W @ F) - 1
            bs = (W @ V) / (W @ Fs) - 1
            rows.append({"condition": cond, "planning_area": a, "time_band": b, "day": dd, "cells": int(n_cells.get(a, 0)),
                         "half_hours": int(n_slots), "cell_snapshots": int(len(idx)),
                         "expected_taxis_per_half_hour": F.sum() / n_slots,
                         "abs_loss_taxis_per_half_hour": abs_loss, "pct_change": 100 * pct,
                         "pct_lo": 100 * np.quantile(bp, 0.025), "pct_hi": 100 * np.quantile(bp, 0.975),
                         "share_change": 100 * share, "share_lo": 100 * np.quantile(bs, 0.025),
                         "share_hi": 100 * np.quantile(bs, 0.975)})
    t = pd.DataFrame(rows)
    t.to_csv(TABLES / "planning_rain_losses.csv", index=False, float_format="%.4f")
    top = (t[t.condition.str.startswith("NEA")].sort_values("abs_loss_taxis_per_half_hour", ascending=False).head(20))
    top.to_csv(TABLES / "planning_top_forecast_rain.csv", index=False, float_format="%.3f")
    print(top[["planning_area", "time_band", "day", "abs_loss_taxis_per_half_hour", "pct_change", "pct_lo", "pct_hi",
               "share_change"]].round(2).to_string(index=False))


def charts():
    style()
    # policy sensitivity: targeting precision vs low-rate of candidates
    g = pd.read_csv(TABLES / "policy_sensitivity.csv")
    fig, ax = plt.subplots(figsize=(9, 4))
    order = ["base"] + [f"{k}={v}" for k, v in SENS]
    for k, (rain, col) in enumerate(((False, BLUE), (True, ORANGE))):
        t = g[g.rain_at_t == rain].set_index("setting").reindex(order)
        x = np.arange(len(order)) + (k - 0.5) * 0.36
        ax.bar(x, t.targeted_low_rate * 100, 0.34, color=col, label=f"{'Rain' if rain else 'No rain'} at decision: targeted cells")
        ax.scatter(x, t.candidates_low_rate * 100, marker="_", s=120, color="black", zorder=3,
                   label="All candidate cells (expected >= 4)" if k == 0 else None)
    ax.set_xticks(range(len(order)), [o.replace("=", "\n") for o in order], fontsize=7.5)
    ax.set_ylabel("% of cells really low at t+h (test year)")
    ax.legend(fontsize=7.5, loc="upper right")
    ax.set_title("Targeting check: cells chosen by the repositioning plan are more often truly low", fontsize=10.5)
    fig.tight_layout()
    save(fig, "policy_targeting", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall; LTA fleet by company. Test year "
         "sample of decision times. Travel times and weights are modelled scenarios.")
    plt.close(fig)
    # planning heatmap
    t = pd.read_csv(TABLES / "planning_rain_losses.csv")
    t = t[t.condition.str.startswith("NEA") & (t.day == "weekday")]
    top_pa = t.groupby("planning_area").abs_loss_taxis_per_half_hour.max().sort_values(ascending=False).head(15).index
    bands = ["00-07", "07-10", "10-17", "17-20", "20-24"]
    M = t[t.planning_area.isin(top_pa)].pivot_table(index="planning_area", columns="time_band",
                                                     values="abs_loss_taxis_per_half_hour").reindex(index=top_pa, columns=bands)
    P = t[t.planning_area.isin(top_pa)].pivot_table(index="planning_area", columns="time_band",
                                                    values="pct_change").reindex(index=top_pa, columns=bands)
    fig, ax = plt.subplots(figsize=(8, 5.5))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("o", ["#fbe3d6", ORANGE, "#8a2f10"])
    im = ax.imshow(M.clip(lower=0).values, cmap=cmap, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M.values[i, j]):
                ax.text(j, i, f"{M.values[i, j]:.1f}\n({P.values[i, j]:+.0f}%)", ha="center", va="center", fontsize=7,
                        color="white" if M.values[i, j] > np.nanmax(M.values) * 0.6 else "black")
    ax.set_xticks(range(len(bands)), bands)
    ax.set_yticks(range(len(top_pa)), [a.title() for a in top_pa], fontsize=8)
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="Fewer vacant taxis per half hour vs no-rain level (whole area)")
    ax.set_title("Weekday planning view: where and when availability drops most when NEA forecasts showers", fontsize=10)
    fig.tight_layout()
    save(fig, "planning_forecast_rain", "Sources: data.gov.sg taxi availability (LTA), NEA 2-hour forecasts. Apr 2022 - Mar 2025. "
         "Association, not cause; numbers in brackets: % vs no-rain model.")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["choose", "evaluate", "planning", "charts"])
    a = ap.parse_args()
    {"choose": part_choose, "evaluate": part_evaluate, "planning": part_planning, "charts": charts}[a.part]()


if __name__ == "__main__":
    main()
