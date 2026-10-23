"""Step 20: simulation v2 (pre-registration: decisions 119-122). Scenario-based operational model, never "validation".

Parts:
  diagnose      why the 24 step-8 combinations fail the plausibility rule (level, timing, spatial, noise floor)
  prep          v2 inputs: drive-time matrices between eligible 1 km cells, request/destination weights,
                per-cell rain sensitivity, place names -> sim/v2/data.json
  tune          Optuna per combination on the 20 fit storms (same settings as step 8)
  plausibility  same pre-registered rule on the 10 held-out storms
  charts        held-out storms chart for the best training fit
  page          build sim/v2/index.html with the dispatcher panel and run the node parity check
"""
from __future__ import annotations

import argparse
import importlib
import itertools
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from analysis.common import (BLUE, BLUE_DARK, INTERIM, MUTED, ORANGE, SEED, TABLES, log_test_scoring, rain_band, save,
                             style)
from analysis.sim_engine import simulate
from pipeline.grid import cell_ids, coarsen, to_xy

S8 = importlib.import_module("analysis.08_simulation")
V2 = Path("sim/v2")
COMBOS = list(itertools.product(["demand", "supply", "mix"], ["characteristics", "observed"], ["dry", "rain"],
                                ["nearest", "widening"]))
LABEL = "simulated, conditional on scenario"


def rel(s):
    s = np.asarray(s, float)
    return s / s[..., :1]


def within_rule(sim_rel, obs_rel):
    return float(np.mean(np.abs(sim_rel - obs_rel) <= 0.20 * np.abs(obs_rel)))


def obs_cells(st, order):
    """Observed vacant taxis per eligible cell at each snapshot of a storm (same de-duplication as step 8)."""
    c = pd.DataFrame({"cell": order})
    pos = {cid: k for k, cid in enumerate(order)}
    cc = pd.read_parquet(INTERIM / "cells.parquet").set_index("cell").loc[order]
    x, y = to_xy(cc.lon.values, cc.lat.values)
    tree = cKDTree(np.c_[x, y])
    pp = pd.read_parquet(f"data/raw/storm_positions/{st['date']}_positions.parquet")
    out = []
    for t in sorted(pp.req_ts.unique()):
        q = pp[pp.req_ts == t]
        qx, qy = to_xy(q.lon.values, q.lat.values)
        drop = set(j for i, j in cKDTree(np.c_[qx, qy]).query_pairs(5.0))
        keep = np.array([k not in drop for k in range(len(q))])
        cid = coarsen(cell_ids(q.lon.values[keep], q.lat.values[keep], 500))
        idx = np.array([pos.get(int(v), -1) for v in cid])
        miss = idx < 0
        if miss.any():
            idx[miss] = tree.query(np.c_[qx[keep][miss], qy[keep][miss]])[1]
        out.append(np.bincount(idx, minlength=len(c)))
    return np.array(out)


def reference_paths(st, beta):
    """Normal path (baseline only) and statistical path (baseline x main-model band effect), relative to start."""
    base = np.asarray(st["base"], float)
    rain = np.asarray(st["rain"], float)
    slots = np.minimum(np.array(st["snap_minutes"]) // 30, base.shape[0] - 1)
    normal = base[slots].sum(1)
    eff = np.exp(np.select([rain_band(rain[slots]) == k for k in (1, 2, 3)], [beta[1], beta[2], beta[3]], 0.0))
    stat = (base[slots] * eff).sum(1)
    return rel(normal), rel(stat)


# ============================================================================= diagnose
def diagnose():
    world, storms, data = S8.load()
    order = data["cells"]["cell"]
    tun = pd.read_csv(TABLES / "sim_tuning.csv")
    em = pd.read_csv(TABLES / "effects_main.csv").query("model == 'abs'").set_index("term").coef
    beta = {1: em["light"], 2: em["moderate"], 3: em["heavy"]}
    log_test_scoring("20_sim_v2.py --part diagnose", "step-8 combinations re-run on held-out storms for the failure "
                     "diagnosis (no tuning)", "step 20")
    rows, refs = [], []
    for k, st in enumerate(storms):
        oc = obs_cells(st, order)
        obs_rel = rel(st["obs_city"])
        pk = int(np.argmin(np.abs(np.array(st["snap_minutes"]) - st["peak_minute"])))
        nrm, stat = reference_paths(st, beta)
        refs.append({"storm": st["date"], "period": st["period"], "snapshots": len(obs_rel),
                     "obs_rel_at_peak": obs_rel[pk], "obs_rel_min": obs_rel.min(),
                     "obs_snapshot_noise": float(np.median(np.abs(np.diff(obs_rel)))),
                     "normal_path_within": within_rule(nrm, obs_rel), "stat_path_within": within_rule(stat, obs_rel),
                     "normal_path_passes": within_rule(nrm, obs_rel) >= 0.7, "stat_path_passes": within_rule(stat, obs_rel) >= 0.7,
                     "normal_rel_at_peak": nrm[pk], "stat_rel_at_peak": stat[pk]})
        dchg_obs = oc[pk] - oc[0]
        for r in tun.itertuples():
            scen = {"mechanism": r.mechanism, "dest": r.dest, "travel": r.travel, "dispatch": r.dispatch}
            out = simulate(world, st, scen, S8.params_of(r), S=4, seed=SEED + 500 + k, record_cells=True)
            sr = rel(out["city"]).mean(0)
            rows.append({**scen, "storm": st["date"], "period": st["period"],
                         "level_bias": float(np.mean(sr - obs_rel)), "rmse": float(np.sqrt(np.mean((sr - obs_rel) ** 2))),
                         "time_corr": float(np.corrcoef(sr, obs_rel)[0, 1]) if sr.std() > 0 else np.nan,
                         "min_gap_minutes": int(st["snap_minutes"][int(np.argmin(sr))] - st["snap_minutes"][int(np.argmin(obs_rel))]),
                         "sim_rel_at_peak": sr[pk], "obs_rel_at_peak": obs_rel[pk],
                         "cell_mean_corr": float(np.corrcoef(out["cells_mean"].mean(0), oc.mean(0))[0, 1]),
                         "cell_change_corr": float(np.corrcoef(out["cells_mean"][pk] - out["cells_mean"][0], dchg_obs)[0, 1]),
                         "within": within_rule(sr, obs_rel)})
        print(st["date"], st["period"], flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(TABLES / "sim2_diagnosis_by_storm.csv", index=False, float_format="%.4f")
    R = pd.DataFrame(refs)
    R.to_csv(TABLES / "sim2_noise_floor.csv", index=False, float_format="%.4f")
    s = d.groupby(["period"]).agg(level_bias=("level_bias", "mean"), abs_level_bias=("level_bias", lambda x: x.abs().mean()),
                                  rmse=("rmse", "mean"), time_corr=("time_corr", "median"),
                                  min_gap_abs=("min_gap_minutes", lambda x: x.abs().median()),
                                  cell_mean_corr=("cell_mean_corr", "mean"), cell_change_corr=("cell_change_corr", "mean"),
                                  within=("within", "mean"))
    rs = R.groupby("period").agg(normal_within=("normal_path_within", "mean"), stat_within=("stat_path_within", "mean"),
                                 normal_passes=("normal_path_passes", "sum"), stat_passes=("stat_path_passes", "sum"),
                                 storms=("storm", "size"), noise=("obs_snapshot_noise", "median"))
    out = s.join(rs)
    out.to_csv(TABLES / "sim2_diagnosis_summary.csv", float_format="%.4f")
    print(out.round(3).T.to_string())
    print(R.round(3).to_string(index=False))



# ============================================================================= prep
def prep():
    import statsmodels.api as sm
    F = importlib.import_module("analysis.12_factors")
    V2.mkdir(parents=True, exist_ok=True)
    d1 = json.loads(Path("sim/data.json").read_text())
    cells = d1["cells"]
    order = np.array(cells["cell"])
    # drive minutes between eligible 1 km cells: row = 1 km cell, column = 500 m land cell nearest its centre
    el = pd.read_csv(INTERIM / "drive_cells1km_eligible.csv")
    c5 = pd.read_csv(INTERIM / "drive_cells500.csv")
    M = np.load(INTERIM / "drive_1kmelig_to_500_dry.npy")
    row = pd.Series(np.arange(len(el)), index=el.cell).loc[order].values
    x5, y5 = to_xy(c5.lon.values, c5.lat.values)
    xc, yc = to_xy(np.array(cells["lon"]), np.array(cells["lat"]))
    col = cKDTree(np.c_[x5, y5]).query(np.c_[xc, yc])[1]
    T = M[np.ix_(row, col)].astype(float)
    np.fill_diagonal(T, 0.0)
    assert np.isfinite(T).all(), "unreachable cell pair"
    T = np.maximum(T, 1.0 - np.eye(len(T)))                          # at least 1 minute between different cells
    print("drive minutes between cells: median", round(float(np.median(T[T > 0])), 1), "max", round(float(T.max()), 1))
    # weights: observed dry daytime supply (07-24, hours-weighted bands) and a Poisson model on characteristics
    ds = pd.read_csv(TABLES / "dry_supply_by_band.csv")
    hrs = {"07-10": 3, "10-17": 7, "17-20": 3, "20-24": 4}
    ds = ds[ds.band.isin(hrs)].assign(h=lambda q: q.band.map(hrs))
    obs_w = ds.groupby("cell").apply(lambda q: np.average(q.mean_vacant_dry, weights=q.h), include_groups=False)
    obs_w = obs_w.reindex(order).fillna(0.05).clip(lower=0.05).values
    ch = pd.read_csv(TABLES / "cell_characteristics.csv").set_index("cell").loc[order].reset_index()
    import joblib
    rfm = joblib.load(INTERIM / "rf_rain_abs.joblib")                 # step-12 training imputation and scaling
    keep = rfm["keep_wls"]
    X = F.design_matrix(ch, [k for k in keep if k in F.NUM], rfm["scaling"])
    for b in [k for k in keep if k in F.BOOL]:
        X[b] = ch[b].astype(float).values
    glm = sm.GLM(obs_w, sm.add_constant(X.fillna(0)), family=sm.families.Poisson()).fit()
    ch_w = np.clip(glm.predict(sm.add_constant(X.fillna(0))), 0.05, None)
    print("characteristics weights vs observed: r =", round(float(np.corrcoef(np.log(ch_w), np.log(obs_w))[0, 1]), 3))
    # per-cell rain sensitivity (step-12 random forest via step 14), mean 1 over cells, gains -> 0
    pr = pd.read_csv(TABLES / "stands_predicted_sensitivity_cells.csv").set_index("cell").pred_heavy_abs_pct
    loss = np.maximum(0.0, -pr.reindex(order).fillna(pr.median()).values)
    off_scale = loss / loss.mean()
    names = pd.read_csv(TABLES / "names_cells.csv").set_index("cell").loc[order]
    ty = pd.read_csv(TABLES / "risk_types.csv").set_index("cell").type.reindex(order)
    cells2 = {**cells, "place": names.place.tolist(), "subzone": names.subzone.str.title().str.replace("'S", "'s").tolist(),
              "planning_area": names.planning_area.str.title().str.replace("'S", "'s").tolist(), "type0": (ty == 0).astype(int).tolist(),
              "pred_heavy_pct": np.round(pr.reindex(order).values, 1).tolist()}
    data = {"cells": cells2, "T": np.round(T, 1).ravel().tolist(),
            "weights": {"characteristics": np.round(ch_w, 3).tolist(), "observed": np.round(obs_w, 3).tolist()},
            "off_scale": np.round(off_scale, 3).tolist(), "storms": d1["storms"], "land": d1["land"], "label": LABEL}
    (V2 / "data.json").write_text(json.dumps(data, separators=(",", ":")))
    pd.DataFrame({"cell": order, "weight_observed": obs_w, "weight_characteristics": ch_w, "off_scale": off_scale}).to_csv(
        TABLES / "sim2_cell_inputs.csv", index=False, float_format="%.4f")
    print("sim/v2/data.json", round((V2 / "data.json").stat().st_size / 1e6, 2), "MB")


def load2():
    from analysis.sim_engine_v2 import World
    d = json.loads((V2 / "data.json").read_text())
    return World(d["cells"], d["T"], d["weights"], d["off_scale"]), d["storms"], d


def loss2(world, storms, scen, params, S=2, seed=SEED):
    from analysis.sim_engine_v2 import simulate as sim2
    errs, cors = [], []
    for k, st in enumerate(storms):
        out = sim2(world, st, scen, params, S=S, seed=seed + k)
        errs.append(np.sqrt(np.mean((rel(out["city"]).mean(0) - rel(st["obs_city"])) ** 2)))
        cors.append(np.corrcoef(out["cells_mean"].mean(0), st["obs_cells_mean"])[0, 1])
    return float(np.mean(errs) + 0.5 * (1 - np.mean(cors))), float(np.mean(errs)), float(np.mean(cors))


# ============================================================================= tune
def tune(mechanisms, n_trials=12):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    world, storms, _ = load2()
    fit = [s for s in storms if s["period"] == "fit"]
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
            return loss2(world, fit, scen, p)[0]

        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=SEED))
        study.optimize(objective, n_trials=n_trials)
        bp = {"occ0": 0.4, "kappa": 1.0, "beta_dem": 0.0, "beta_off": 0.0, **study.best_params}
        L, rmse, cor = loss2(world, fit, scen, bp, S=4)
        rows.append({**scen, **bp, "loss": L, "rmse_rel": rmse, "cell_corr": cor, "trials": n_trials,
                     "seconds": round(time.time() - t0)})
        print(rows[-1], flush=True)
    parts = INTERIM / "sim2_tuning_parts"                    # one file per process so mechanisms can run in parallel
    parts.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(parts / f"{'_'.join(mechanisms)}.csv", index=False)
    out = pd.concat([pd.read_csv(p) for p in sorted(parts.glob("*.csv"))])
    out = out.drop_duplicates(["mechanism", "dest", "travel", "dispatch"], keep="last")
    out.to_csv(TABLES / "sim2_tuning.csv", index=False, float_format="%.5f")


# ============================================================================= plausibility
def plausibility():
    from analysis.sim_engine_v2 import simulate as sim2
    world, storms, _ = load2()
    held = [s for s in storms if s["period"] == "test"]
    tun = pd.read_csv(TABLES / "sim2_tuning.csv")
    log_test_scoring("20_sim_v2.py --part plausibility", "simulation v2 on held-out test-year storms: simulated vs "
                     "observed (pre-registered rule, no tuning)", "step 20")
    rows = []
    for r in tun.itertuples():
        scen = {"mechanism": r.mechanism, "dest": r.dest, "travel": r.travel, "dispatch": r.dispatch}
        passes, signs = 0, 0
        for k, st in enumerate(held):
            out = sim2(world, st, scen, S8.params_of(r), S=10, seed=SEED + 100 + k)
            sr, orl = rel(out["city"]).mean(0), rel(st["obs_city"])
            w = within_rule(sr, orl)
            passes += w >= 0.70
            pk = int(np.argmin(np.abs(np.array(st["snap_minutes"]) - st["peak_minute"])))
            signs += np.sign(sr[pk] - 1) == np.sign(orl[pk] - 1)
            rows.append({**scen, "storm": st["date"], "share_within_20pct": w, "sim_rel_at_peak": sr[pk],
                         "obs_rel_at_peak": orl[pk], "level_bias": float(np.mean(sr - orl)),
                         "time_corr": float(np.corrcoef(sr, orl)[0, 1]),
                         "cell_mean_corr": float(np.corrcoef(out["cells_mean"].mean(0), st["obs_cells_mean"])[0, 1])})
        for row in rows[-len(held):]:
            row["storms_passed"], row["sign_matches"] = int(passes), int(signs)
            row["combination_passes"] = bool(passes >= 7 and signs >= 7)
        print(scen, "passed", passes, "signs", signs, flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(TABLES / "sim2_plausibility_by_storm.csv", index=False, float_format="%.4f")
    s = t.groupby(["mechanism", "dest", "travel", "dispatch"]).agg(
        storms_passed=("storms_passed", "first"), sign_matches=("sign_matches", "first"),
        combination_passes=("combination_passes", "first"), mean_share_within=("share_within_20pct", "mean"),
        level_bias=("level_bias", "mean"), time_corr=("time_corr", "median"),
        cell_mean_corr=("cell_mean_corr", "mean")).reset_index()
    s.to_csv(TABLES / "sim2_plausibility.csv", index=False, float_format="%.4f")
    print(s.to_string())


# ============================================================================= charts
def charts():
    import matplotlib.pyplot as plt
    from analysis.sim_engine_v2 import simulate as sim2
    style()
    world, storms, _ = load2()
    tun = pd.read_csv(TABLES / "sim2_tuning.csv").sort_values("loss")
    best = tun.iloc[0]
    held = [s for s in storms if s["period"] == "test"]
    log_test_scoring("20_sim_v2.py --part charts", "held-out chart: simulation v2 vs observed feed", "step 20")
    pl = pd.read_csv(TABLES / "sim2_plausibility.csv").set_index(["mechanism", "dest", "travel", "dispatch"])
    ok = bool(pl.loc[(best.mechanism, best.dest, best.travel, best.dispatch), "combination_passes"])
    em = pd.read_csv(TABLES / "effects_main.csv").query("model == 'abs'").set_index("term").coef
    beta = {1: em["light"], 2: em["moderate"], 3: em["heavy"]}
    fig, axes = plt.subplots(2, 5, figsize=(14, 5.5), sharey=True)
    scen = {"mechanism": best.mechanism, "dest": best.dest, "travel": best.travel, "dispatch": best.dispatch}
    for ax, st in zip(axes.ravel(), held):
        out = sim2(world, st, scen, S8.params_of(best), S=50, seed=SEED, record_cells=False)
        sr = rel(out["city"]) * 100
        tm = np.array(st["snap_minutes"]) / 60
        ax.fill_between(tm, np.quantile(sr, 0.05, 0), np.quantile(sr, 0.95, 0), color=BLUE, alpha=0.2, lw=0)
        ax.plot(tm, sr.mean(0), color=BLUE, lw=1.5, label="Simulated v2 (mean, 5-95%)")
        ax.plot(tm, reference_paths(st, beta)[1] * 100, color=MUTED, lw=1, ls=":", label="Statistical path")
        ax.plot(tm, rel(st["obs_city"]) * 100, color="black", lw=1.2, label="Observed feed")
        ax.axvline(st["peak_minute"] / 60, color=ORANGE, lw=1, ls="--")
        ax.set_title(st["date"], fontsize=8.5)
        ax.set_xlabel("Hours from start", fontsize=7.5)
    axes[0, 0].set_ylabel("Vacant taxis, % of start")
    axes[0, 0].legend(fontsize=6.5)
    fig.suptitle(f"Simulation v2, held-out storms, best training fit ({best.mechanism}, {best.dest} pattern, {best.travel} "
                 f"roads, {best.dispatch}): {'passes' if ok else 'does NOT pass'} the pre-registered plausibility rule - "
                 f"{LABEL}", x=0.01, ha="left", fontsize=9.5)
    fig.tight_layout()
    save(fig, "sim2_heldout_storms", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, OpenStreetMap roads. "
         "Dashed: rain peak; dotted: baseline x main-model rain effects. Scenario-based operational model, not validation.")
    plt.close(fig)
    diag_chart()


def diag_chart():
    """Diagnosis chart from the saved tables (step-8 combinations): where the mismatch is."""
    import matplotlib.pyplot as plt
    style()
    d = pd.read_csv(TABLES / "sim2_diagnosis_by_storm.csv")
    R = pd.read_csv(TABLES / "sim2_noise_floor.csv")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    for ax, col, lab in ((axes[0], "level_bias", "Level: mean(sim - observed), relative units"),
                         (axes[1], "time_corr", "Timing: correlation over time"),
                         (axes[2], "cell_change_corr", "Spatial: correlation of cell changes")):
        for k, (per, cc) in enumerate((("fit", BLUE_DARK), ("test", ORANGE))):
            for j, mech in enumerate(["demand", "supply", "mix"]):
                v = d[(d.period == per) & (d.mechanism == mech)][col].dropna()
                ax.boxplot(v, positions=[j * 3 + k], widths=0.8, patch_artist=True, showfliers=False,
                           boxprops=dict(facecolor=cc, alpha=0.35, color=cc), medianprops=dict(color=cc))
        ax.set_xticks([0.5, 3.5, 6.5], ["demand", "supply", "mix"])
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_title(lab, fontsize=9)
    axes[0].plot([], [], color=BLUE_DARK, lw=6, alpha=0.35, label="20 training storms")
    axes[0].plot([], [], color=ORANGE, lw=6, alpha=0.35, label="10 held-out storms")
    axes[0].legend(fontsize=7)
    sp = R.groupby("period").stat_path_passes.sum()
    lb = d.groupby("period").level_bias.mean()
    fig.suptitle(f"Why step-8 scenarios fail: average level gap {100 * lb['fit']:+.0f}% (training) / {100 * lb['test']:+.0f}% "
                 f"(held-out), but timing and which cells lose taxis match weakly; the statistical path passes only "
                 f"{sp.get('test', 0)}/10 held-out storms", x=0.01, ha="left", fontsize=9)
    fig.tight_layout()
    save(fig, "sim2_diagnosis", "Sources: step-8 simulation, data.gov.sg taxi availability (LTA), NEA rainfall. "
         "Each box: 8 tuned combinations x storms.")
    plt.close(fig)



# ============================================================================= page and parity check
def diag_text():
    d = pd.read_csv(TABLES / "sim2_diagnosis_summary.csv").set_index("period")
    pl = pd.read_csv(TABLES / "sim2_plausibility.csv")
    f, t = d.loc["fit"], d.loc["test"]
    return (f"Why: in the step-8 version the simulated citywide path sat on average {abs(100 * f.level_bias):.0f}% below the "
            f"observed one on training storms, its timing matched only moderately (correlation {f.time_corr:.2f} training, "
            f"{t.time_corr:.2f} held-out) and the pattern of which cells lost taxis matched poorly (correlation "
            f"{f.cell_change_corr:.2f} / {t.cell_change_corr:.2f}). Held-out storms show deeper, noisier drops: even a "
            f"non-simulation path (baseline x estimated rain effects) meets the rule on only {int(t.stat_passes)} of 10. "
            f"v2 (road times, place characteristics) reaches a mean level gap of {100 * pl.level_bias.mean():+.0f}% on held-out "
            f"storms. Use the page to explore mechanisms, not to read off numbers.")


def page():
    data = (V2 / "data.json").read_text()
    tun = pd.read_csv(TABLES / "sim2_tuning.csv").to_dict(orient="records")
    pl = pd.read_csv(TABLES / "sim2_plausibility.csv").to_dict(orient="records")
    engine = (V2 / "engine_v2.js").read_text()
    shell = (V2 / "page_template_v2.html").read_text()
    html = (shell.replace("/*__ENGINE__*/", engine)
            .replace("/*__DATA__*/", f"const DATA = {data};\nconst TUNED = {json.dumps(tun)};\nconst PLAUS = {json.dumps(pl)};"
                     f"\nconst DIAG = {json.dumps(diag_text())};"))
    (V2 / "index.html").write_text(html)
    print("sim/v2/index.html", round((V2 / "index.html").stat().st_size / 1e6, 2), "MB")
    parity()


def parity(S=50):
    from analysis.sim_engine_v2 import simulate as sim2
    world, storms, _ = load2()
    tun = pd.read_csv(TABLES / "sim2_tuning.csv")
    held = [s for s in storms if s["period"] == "test"]
    cases = [(tun.iloc[0], held[0]), (tun.iloc[len(tun) // 2], held[3]), (tun.iloc[-1], held[7])]
    rows = []
    for r, st in cases:
        scen = {"mechanism": r.mechanism, "dest": r.dest, "travel": r.travel, "dispatch": r.dispatch, "demand_level": 1.0}
        out = sim2(world, st, scen, S8.params_of(r), S=S, seed=SEED, record_cells=False)
        pk = int(np.argmin(np.abs(np.array(st["snap_minutes"]) - st["peak_minute"])))
        py_mean, py_peak = float(rel(out["city"]).mean()), float(rel(out["city"])[:, pk].mean())
        arg = json.dumps({"scen": scen, "params": S8.params_of(r), "storm": st["date"], "seeds": S})
        res = subprocess.run(["node", str(V2 / "parity_v2.mjs"), arg], capture_output=True, text=True, timeout=3600)
        js = json.loads(res.stdout.strip().splitlines()[-1])
        rows.append({**scen, "storm": st["date"], "python_mean_rel": py_mean, "js_mean_rel": js["mean_rel"],
                     "python_peak_rel": py_peak, "js_peak_rel": js["peak_rel"],
                     "diff_mean_pct": 100 * (js["mean_rel"] / py_mean - 1), "diff_peak_pct": 100 * (js["peak_rel"] / py_peak - 1)})
        print(rows[-1], flush=True)
    t = pd.DataFrame(rows)
    ok_peak = (t.diff_peak_pct.abs() <= 5) | ((t.js_peak_rel - t.python_peak_rel).abs() <= 0.01)
    t["within_5pct"] = (t.diff_mean_pct.abs() <= 5) & ok_peak
    t.to_csv(TABLES / "sim2_parity_check.csv", index=False, float_format="%.4f")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True)
    ap.add_argument("--mechanism", nargs="*", default=["demand", "supply", "mix"])
    a = ap.parse_args()
    if a.part == "tune":
        return tune(a.mechanism)
    globals()[a.part]()


if __name__ == "__main__":
    main()
