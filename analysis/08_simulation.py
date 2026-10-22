"""Step 8: scenario-based simulation of vacant taxis in storms (HANDOFF section 6, step 8).

A scenario-based operational model, never "validation". Engine: analysis/sim_engine.py (Python) and
sim/engine.js (JavaScript port for sim/index.html). Rules: outputs/decisions.md items 72-79.

Parts:
  prep          storms (20 fit, 10 held-out test-year storms), cells, rain, baselines, observed series -> sim/data.json
  tune          Optuna per mechanism x destinations x travel x dispatch on the 20 fit storms (--mechanism to split)
  plausibility  pass / fail per tuned combination on the 10 held-out storms (rule fixed in advance)
  grid          50 seeds per grid cell on the held-out storms (--mechanism to split)
  greedy        check the greedy policy solver against PuLP on step-7 decisions
  page          build sim/index.html (self-contained) and run the node parity check
  charts        summary charts and tables
"""
from __future__ import annotations

import argparse
import gc
import itertools
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from analysis.common import (BLUE, BLUE_DARK, INTERIM, MUTED, ORANGE, SEED, STATIC, TABLES, save, style)
from analysis.sim_engine import World, simulate
from pipeline.grid import cell_ids, coarsen, to_xy, to_lonlat

SIM = Path("sim")
COMBOS = list(itertools.product(["demand", "supply", "mix"], ["mrt", "landuse"], ["dry", "rain"], ["nearest", "widening"]))
LABEL = "simulated, conditional on scenario"


# ============================================================================= prep
def prep():
    SIM.mkdir(exist_ok=True)
    c = pd.read_parquet(INTERIM / "cells.parquet")
    c = c[c.eligible].sort_values("cell").reset_index(drop=True)
    x, y = to_xy(c.lon.values, c.lat.values)
    pos = {cid: k for k, cid in enumerate(c.cell)}
    tree = cKDTree(np.c_[x, y])
    cells = {"cell": c.cell.tolist(), "x_km": (x / 1000).round(4).tolist(), "y_km": (y / 1000).round(4).tolist(),
             "lon": c.lon.round(5).tolist(), "lat": c.lat.round(5).tolist(),
             "mrt_exits": c.mrt_exits_in_cell.astype(int).tolist(), "stands": c.taxi_stands_300m.astype(int).tolist(),
             "centre": c.city_centre.astype(int).tolist(), "area": c.planning_area.tolist()}
    sd = pd.read_csv("data/raw/storm_positions/storm_days.csv", parse_dates=["date", "peak_end"])
    share = pd.read_csv(STATIC / "lta_cdg_share_monthly.csv", parse_dates=["month"]).set_index("month").cdg_share
    storms = []
    for r in sd.itertuples():
        pp = pd.read_parquet(f"data/raw/storm_positions/{r.date:%Y-%m-%d}_positions.parquet")
        times = sorted(pp.req_ts.unique())
        t0 = pd.Timestamp(times[0])
        M = int((pd.Timestamp(times[-1]) - t0).total_seconds() // 60) + 1
        obs = []
        for t in times:
            q = pp[pp.req_ts == t]
            qx, qy = to_xy(q.lon.values, q.lat.values)
            drop = set(j for i, j in cKDTree(np.c_[qx, qy]).query_pairs(5.0))   # de-duplicate within 5 m
            keep = np.array([k not in drop for k in range(len(q))])
            cid = coarsen(cell_ids(q.lon.values[keep], q.lat.values[keep], 500))
            idx = np.array([pos.get(int(v), -1) for v in cid])
            miss = idx < 0
            if miss.any():
                idx[miss] = tree.query(np.c_[qx[keep][miss], qy[keep][miss]])[1]
            obs.append(np.bincount(idx, minlength=len(c)))
        obs = np.array(obs)
        # rain and baseline on 30-minute slots from the panel
        slots = pd.date_range(t0, t0 + pd.Timedelta(minutes=M + 60), freq="30min")
        pan = pd.read_parquet(INTERIM / f"panel30_{t0.year}.parquet", columns=["ts", "cell", "mmh", "baseline"],
                              filters=[("ts", ">=", slots[0]), ("ts", "<=", slots[-1] + pd.Timedelta(minutes=30))])
        mm = pan.pivot_table(index="ts", columns="cell", values="mmh").reindex(columns=c.cell)
        bb = pan.pivot_table(index="ts", columns="cell", values="baseline").reindex(columns=c.cell)
        rain = mm.reindex(slots + pd.Timedelta(minutes=30)).ffill().bfill().fillna(0).values      # (t, t+30] -> slot t
        base = bb.reindex(slots).ffill().bfill().fillna(0.5).values
        snap_min = [int((pd.Timestamp(t) - t0).total_seconds() // 60) for t in times]
        peak_min = int((r.peak_end - t0).total_seconds() // 60)
        storms.append({"date": f"{r.date:%Y-%m-%d}", "period": r.period, "start": str(t0), "minutes": M,
                       "snap_minutes": snap_min, "peak_minute": peak_min, "peak_mmh": float(r.peak_mmh),
                       "share": float(share.asof(t0)), "v0": obs[0].astype(int).tolist(),
                       "obs_city": obs.sum(1).astype(int).tolist(), "obs_cells_mean": obs.mean(0).round(3).tolist(),
                       "rain": np.round(rain, 2).tolist(), "base": np.round(base, 2).tolist()})
        print(r.date.date(), r.period, len(times), "snapshots", M, "minutes", obs.sum(1)[0], "taxis at start", flush=True)
    land = json.load(open(STATIC / "sg_map.json"))["land"]
    data = {"cells": cells, "storms": storms, "land": land, "label": LABEL}
    (SIM / "data.json").write_text(json.dumps(data, separators=(",", ":")))
    print("sim/data.json", round((SIM / "data.json").stat().st_size / 1e6, 2), "MB")


def load():
    d = json.loads((SIM / "data.json").read_text())
    return World(d["cells"]), d["storms"], d


def rel(series):
    s = np.asarray(series, float)
    return s / s[..., :1]


def loss(world, storms, scen, params, S=2, seed=SEED):
    errs, cors = [], []
    for k, st in enumerate(storms):
        out = simulate(world, st, scen, params, S=S, seed=seed + k)
        sim_rel = rel(out["city"]).mean(0)
        obs_rel = rel(st["obs_city"])
        errs.append(np.sqrt(np.mean((sim_rel - obs_rel) ** 2)))
        cm = out["cells_mean"].mean(0)
        cors.append(np.corrcoef(cm, st["obs_cells_mean"])[0, 1])
    return float(np.mean(errs) + 0.5 * (1 - np.mean(cors))), float(np.mean(errs)), float(np.mean(cors))


# ============================================================================= tune
def tune(mechanisms, n_trials=12):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    world, storms, _ = load()
    fit = [s for s in storms if s["period"] == "fit"]
    f = TABLES / "sim_tuning.csv"
    prev = pd.read_csv(f) if f.exists() else pd.DataFrame()
    rows = []
    for mech, dest, travel, disp in COMBOS:
        if mech not in mechanisms:
            continue
        scen = {"mechanism": mech, "dest": dest, "travel": travel, "dispatch": disp}
        t0 = time.time()

        def objective(trial):
            p = {"occ0": trial.suggest_float("occ0", 0.2, 0.7), "kappa": trial.suggest_float("kappa", 0.7, 1.3),
                 "beta_dem": trial.suggest_float("beta_dem", 0.0, 2.0) if mech in ("demand", "mix") else 0.0,
                 "beta_off": trial.suggest_float("beta_off", 0.0, 0.05) if mech in ("supply", "mix") else 0.0}
            return loss(world, fit, scen, p)[0]

        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=SEED))
        study.optimize(objective, n_trials=n_trials)
        bp = {"occ0": 0.4, "kappa": 1.0, "beta_dem": 0.0, "beta_off": 0.0, **study.best_params}
        L, rmse, cor = loss(world, fit, scen, bp, S=4)
        rows.append({**scen, **bp, "loss": L, "rmse_rel": rmse, "cell_corr": cor, "trials": n_trials,
                     "seconds": round(time.time() - t0)})
        print(rows[-1], flush=True)
    out = pd.concat([prev, pd.DataFrame(rows)]).drop_duplicates(["mechanism", "dest", "travel", "dispatch"], keep="last")
    out.to_csv(f, index=False, float_format="%.5f")


def params_of(row):
    return {"occ0": row.occ0, "kappa": row.kappa, "beta_dem": row.beta_dem, "beta_off": row.beta_off}


# ============================================================================= plausibility
def plausibility():
    world, storms, _ = load()
    held = [s for s in storms if s["period"] == "test"]
    tun = pd.read_csv(TABLES / "sim_tuning.csv")
    rows = []
    for r in tun.itertuples():
        scen = {"mechanism": r.mechanism, "dest": r.dest, "travel": r.travel, "dispatch": r.dispatch}
        passes, signs = 0, 0
        for k, st in enumerate(held):
            out = simulate(world, st, scen, params_of(r), S=10, seed=SEED + 100 + k, record_cells=False)
            sim_rel = rel(out["city"]).mean(0)
            obs_rel = rel(st["obs_city"])
            within = np.mean(np.abs(sim_rel - obs_rel) <= 0.20 * np.abs(obs_rel))
            passes += within >= 0.70
            pk = int(np.argmin(np.abs(np.array(st["snap_minutes"]) - st["peak_minute"])))
            signs += np.sign(sim_rel[pk] - 1) == np.sign(obs_rel[pk] - 1)
            rows.append({**scen, "storm": st["date"], "share_within_20pct": within,
                         "sim_rel_at_peak": sim_rel[pk], "obs_rel_at_peak": obs_rel[pk]})
        for row in rows[-len(held):]:
            row["storms_passed"] = int(passes)
            row["sign_matches"] = int(signs)
            row["combination_passes"] = bool(passes >= 7 and signs >= 7)
        print(scen, "passed", passes, "signs", signs, flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(TABLES / "sim_plausibility_by_storm.csv", index=False, float_format="%.4f")
    s = t.groupby(["mechanism", "dest", "travel", "dispatch"]).agg(
        storms_passed=("storms_passed", "first"), sign_matches=("sign_matches", "first"),
        combination_passes=("combination_passes", "first"), mean_share_within=("share_within_20pct", "mean")).reset_index()
    s.to_csv(TABLES / "sim_plausibility.csv", index=False, float_format="%.4f")
    print(s.to_string())


# ============================================================================= grid
def grid(mechanisms, S=50):
    world, storms, _ = load()
    held = [s for s in storms if s["period"] == "test"]
    tun = pd.read_csv(TABLES / "sim_tuning.csv")
    f = TABLES / "sim_grid_runs.csv"
    prev = pd.read_csv(f) if f.exists() else pd.DataFrame()
    rows = []
    t0 = time.time()
    for r in tun.itertuples():
        if r.mechanism not in mechanisms:
            continue
        for dl in (0.8, 1.0, 1.2):
            for policy in (False, True):
                scen = {"mechanism": r.mechanism, "dest": r.dest, "travel": r.travel, "dispatch": r.dispatch,
                        "demand_level": dl}
                for k, st in enumerate(held):
                    out = simulate(world, st, scen, params_of(r), S=S, seed=SEED + 1000 + k, policy=policy,
                                   record_cells=False)
                    sr = rel(out["city"])
                    pk = int(np.argmin(np.abs(np.array(st["snap_minutes"]) - st["peak_minute"])))
                    base_ok = np.array(st["base"])[min(st["peak_minute"] // 30, len(st["base"]) - 1)] >= 4
                    zero = (out["final_V"][:, base_ok] == 0).mean(1)
                    for s_ in range(S):
                        rows.append({**scen, "policy": "step-7 repositioning" if policy else "as usual",
                                     "storm": st["date"], "seed": s_, "vacant_rel_at_peak": sr[s_, pk],
                                     "abandoned_share_rain": out["abandoned_rain"][s_] / max(1, out["requests_rain"][s_]),
                                     "abandoned_share_all": out["abandoned"][s_] / max(1, out["requests"][s_]),
                                     "mean_wait_min": out["wait_minutes"][s_] / max(1, out["served"][s_]),
                                     "zero_share_end": zero[s_]})
                print(r.mechanism, r.dest, r.travel, r.dispatch, dl, policy, f"{time.time() - t0:.0f}s", flush=True)
    out = pd.concat([prev, pd.DataFrame(rows)])
    out = out.drop_duplicates(["mechanism", "dest", "travel", "dispatch", "demand_level", "policy", "storm", "seed"],
                              keep="last")
    out.to_csv(f, index=False, float_format="%.5f")


def summarise():
    g = pd.read_csv(TABLES / "sim_grid_runs.csv")
    pl = pd.read_csv(TABLES / "sim_plausibility.csv")
    keys = ["mechanism", "dest", "travel", "dispatch", "demand_level", "policy"]
    q = lambda p: (lambda x: x.quantile(p))
    s = g.groupby(keys).agg(
        vacant_rel_peak_p05=("vacant_rel_at_peak", q(0.05)), vacant_rel_peak_mean=("vacant_rel_at_peak", "mean"),
        vacant_rel_peak_p95=("vacant_rel_at_peak", q(0.95)),
        abandoned_rain_p05=("abandoned_share_rain", q(0.05)), abandoned_rain_mean=("abandoned_share_rain", "mean"),
        abandoned_rain_p95=("abandoned_share_rain", q(0.95)), wait_mean=("mean_wait_min", "mean"),
        zero_share_mean=("zero_share_end", "mean"), runs=("seed", "size")).reset_index()
    s = s.merge(pl[["mechanism", "dest", "travel", "dispatch", "combination_passes"]], on=keys[:4])
    s.insert(0, "label", LABEL)
    s.to_csv(TABLES / "sim_grid_summary.csv", index=False, float_format="%.4f")
    # policy effect (paired by storm and seed)
    a = g[g.policy == "as usual"].set_index(keys[:5] + ["storm", "seed"])
    b = g[g.policy != "as usual"].set_index(keys[:5] + ["storm", "seed"])
    d = (b[["vacant_rel_at_peak", "abandoned_share_rain", "mean_wait_min"]]
         - a[["vacant_rel_at_peak", "abandoned_share_rain", "mean_wait_min"]]).dropna()
    e = d.groupby(level=keys[:5]).agg(["mean", lambda x: x.quantile(0.05), lambda x: x.quantile(0.95)])
    e.columns = [f"{a}_{b}".replace("<lambda_0>", "p05").replace("<lambda_1>", "p95") for a, b in e.columns]
    e = e.reset_index()
    e.insert(0, "label", LABEL)
    e.to_csv(TABLES / "sim_policy_effect.csv", index=False, float_format="%.5f")
    # sensitivity: one factor at a time around a reference scenario (mix, mrt, rain, nearest, 1.0, as usual)
    ref = {"mechanism": "mix", "dest": "mrt", "travel": "rain", "dispatch": "nearest", "demand_level": 1.0,
           "policy": "as usual"}
    rows = []
    levels = {"mechanism": ["demand", "supply", "mix"], "dest": ["mrt", "landuse"], "travel": ["dry", "rain"],
              "dispatch": ["nearest", "widening"], "demand_level": [0.8, 1.0, 1.2],
              "policy": ["as usual", "step-7 repositioning"]}
    for k, vals in levels.items():
        for v in vals:
            sel = dict(ref, **{k: v})
            m = np.ones(len(s), bool)
            for kk, vv in sel.items():
                m &= (s[kk] == vv).values
            if m.any():
                rows.append({"factor": k, "value": v, **s[m].iloc[0][["vacant_rel_peak_mean", "abandoned_rain_mean",
                                                                      "wait_mean", "combination_passes"]].to_dict()})
    t = pd.DataFrame(rows)
    t.insert(0, "label", LABEL + " (reference: mix, MRT pattern, rain congestion, nearest, demand 1.0, as usual)")
    t.to_csv(TABLES / "sim_sensitivity.csv", index=False, float_format="%.4f")
    print(t.to_string())


# ============================================================================= greedy check
def greedy_check(n=60):
    """Compare the greedy plan used in the simulation with the PuLP optimum on step-7 test decisions."""
    import importlib
    from analysis.sim_engine import greedy_plan
    pol = importlib.import_module("analysis.07_policy")
    cells, shares = pol.cells_info(), pol.cdg_share()
    d = pol.decision_frame(60, "test", False)
    wet, dry = pol.sample_times(d, n // 2, n // 2, seed=SEED + 7)
    cfg = pol.BASE
    world, _, data = load()
    order = data["cells"]["cell"]
    rows = []
    for t in np.r_[wet, dry]:
        snap = d[d.ts == t].set_index("cell").reindex(order)
        if snap.vacant.isna().any():
            snap = snap.fillna({"vacant": 0, "base_i": 0.5, "base_j": 0.5, "mu": 0.5, "mmh_island": 0})
        sh = float(shares.asof(pd.Timestamp(t)))
        rain_now = bool(snap.mmh_island.fillna(0).iloc[0] > 0)
        opt = pol.solve(snap.reset_index(), cells, sh, cfg["N"], cfg["lam"], cfg["h"], cfg["congestion"],
                        cfg["weights"], rain_now)
        plan = greedy_plan(world, snap.vacant.values, snap.base_i.values, snap.base_j.values, snap.mu.values,
                           np.full(world.C, 1.0 if rain_now else 0.0), sh, travel="rain")
        S_obj = objective_value(snap, plan, world, cfg)
        rows.append({"ts": t, "pulp_objective": opt["objective"], "greedy_objective": S_obj,
                     "pulp_moved": opt["moved"], "greedy_moved": int(sum(v for v, _ in plan.values()))})
    t = pd.DataFrame(rows)
    t["ratio"] = t.greedy_objective / t.pulp_objective.replace(0, np.nan)
    t.to_csv(TABLES / "sim_greedy_vs_pulp.csv", index=False, float_format="%.5f")
    print(t.describe().round(4).to_string())


def objective_value(snap, plan, world, cfg):
    from scipy.stats import poisson
    base, mu = snap.base_j.values, np.maximum(snap.mu.values, 1e-6)
    got = np.zeros(world.C, int)
    cost = 0.0
    for (i, j), (n, tt) in plan.items():
        got[j] += n
        cost += cfg["lam"] * tt * n
    val = 0.0
    for j in np.flatnonzero(got):
        ys = np.arange(0, int(np.ceil(base[j])) + 25)
        p = poisson.pmf(ys, mu[j])
        S = lambda m: (np.maximum(0, base[j] - (ys + m)) * p).sum() / max(1, base[j])
        val += S(0) - S(min(got[j], 20))
    return val - cost


# ============================================================================= page and parity check
def page():
    import shutil
    data = (SIM / "data.json").read_text()
    tun = pd.read_csv(TABLES / "sim_tuning.csv").to_dict(orient="records")
    pl = pd.read_csv(TABLES / "sim_plausibility.csv").to_dict(orient="records")
    engine = (SIM / "engine.js").read_text()
    shell = (SIM / "page_template.html").read_text()
    html = (shell.replace("/*__ENGINE__*/", engine)
            .replace("/*__DATA__*/", f"const DATA = {data};\nconst TUNED = {json.dumps(tun)};\nconst PLAUS = {json.dumps(pl)};"))
    (SIM / "index.html").write_text(html)
    print("sim/index.html", round((SIM / "index.html").stat().st_size / 1e6, 2), "MB")
    parity()


def parity(S=50):
    world, storms, _ = load()
    tun = pd.read_csv(TABLES / "sim_tuning.csv")
    held = [s for s in storms if s["period"] == "test"]
    cases = [(tun.iloc[0], held[0]), (tun.iloc[len(tun) // 2], held[3]), (tun.iloc[-1], held[7])]
    rows = []
    for r, st in cases:
        scen = {"mechanism": r.mechanism, "dest": r.dest, "travel": r.travel, "dispatch": r.dispatch, "demand_level": 1.0}
        out = simulate(world, st, scen, params_of(r), S=S, seed=SEED, record_cells=False)
        py_mean = float(rel(out["city"]).mean())
        pk = int(np.argmin(np.abs(np.array(st["snap_minutes"]) - st["peak_minute"])))
        py_peak = float(rel(out["city"])[:, pk].mean())
        arg = json.dumps({"scen": scen, "params": params_of(r), "storm": st["date"], "seeds": S})
        res = subprocess.run(["node", str(SIM / "parity.mjs"), arg], capture_output=True, text=True, timeout=1800)
        js = json.loads(res.stdout.strip().splitlines()[-1])
        rows.append({**scen, "storm": st["date"], "python_mean_rel": py_mean, "js_mean_rel": js["mean_rel"],
                     "python_peak_rel": py_peak, "js_peak_rel": js["peak_rel"],
                     "diff_mean_pct": 100 * (js["mean_rel"] / py_mean - 1), "diff_peak_pct": 100 * (js["peak_rel"] / py_peak - 1)})
        print(rows[-1], flush=True)
    t = pd.DataFrame(rows)
    t["within_5pct"] = (t.diff_mean_pct.abs() <= 5) & (t.diff_peak_pct.abs() <= 5)
    t.to_csv(TABLES / "sim_parity_check.csv", index=False, float_format="%.4f")


# ============================================================================= charts
def charts():
    style()
    import matplotlib.pyplot as plt
    world, storms, _ = load()
    tun = pd.read_csv(TABLES / "sim_tuning.csv").sort_values("loss")
    best = tun.iloc[0]
    held = [s for s in storms if s["period"] == "test"]
    fig, axes = plt.subplots(2, 5, figsize=(14, 5.5), sharey=True)
    scen = {"mechanism": best.mechanism, "dest": best.dest, "travel": best.travel, "dispatch": best.dispatch}
    for ax, st in zip(axes.ravel(), held):
        out = simulate(world, st, scen, params_of(best), S=50, seed=SEED, record_cells=False)
        sr = rel(out["city"]) * 100
        tm = np.array(st["snap_minutes"]) / 60
        ax.fill_between(tm, np.quantile(sr, 0.05, 0), np.quantile(sr, 0.95, 0), color=BLUE, alpha=0.2, lw=0)
        ax.plot(tm, sr.mean(0), color=BLUE, lw=1.5, label="Simulated (mean, 5-95%)")
        ax.plot(tm, rel(st["obs_city"]) * 100, color="black", lw=1.2, label="Observed feed")
        ax.axvline(st["peak_minute"] / 60, color=ORANGE, lw=1, ls="--")
        ax.set_title(st["date"], fontsize=8.5)
        ax.set_xlabel("Hours from start", fontsize=7.5)
    axes[0, 0].set_ylabel("Vacant taxis, % of start")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(f"Held-out storms: simulated vs observed vacant taxis ({best.mechanism}, {best.dest}, {best.travel} travel, "
                 f"{best.dispatch} dispatch) - {LABEL}", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, "sim_heldout_storms", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Dashed: rain peak. "
         "Scenario-based operational model, not validation.")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True,
                    choices=["prep", "tune", "plausibility", "grid", "summarise", "greedy", "page", "parity", "charts"])
    ap.add_argument("--mechanism", nargs="*", default=["demand", "supply", "mix"])
    a = ap.parse_args()
    if a.part == "tune":
        return tune(a.mechanism)
    if a.part == "grid":
        return grid(a.mechanism)
    {"prep": prep, "plausibility": plausibility, "summarise": summarise, "greedy": greedy_check, "page": page,
     "parity": parity, "charts": charts}[a.part]()


if __name__ == "__main__":
    main()
