"""Step 14: taxi stands and the planning map (pre-registration: decision 112). Supply associations only.

(a) heavy-rain effect with vs without a taxi stop / stand or OSM taxi point within 300 m, with controls;
(b) ranked candidate stand locations (rain-hit or taxi-desert cells without a stand nearby), qualitative notes;
(c) predicted heavy-rain effect for every land cell (step-12 random forest), by planning area and subzone.
Usage: .venv/bin/python -m analysis.14_stands
"""
from __future__ import annotations

import importlib

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from analysis.common import BLUE_DARK, INTERIM, ORANGE, TABLES, save, style
from analysis.fepois_hd import fepois, pct

E = importlib.import_module("analysis.03_effects")
F = importlib.import_module("analysis.12_factors")
N = importlib.import_module("analysis.10_names")


def part_a(c):
    p = E.load_fit()
    p = p[E.sample(p)].reset_index(drop=True)
    X, fe_abs, fe_share, day = E.design(p)
    heavy = p.rain_band.values == 3
    stand = (c.taxi_stands_300m + c.osm_taxi_points_300m) > 0
    dm = p.cell.map(c.dist_mrt_m).values
    cc = c[c.eligible]
    z = lambda s: (s - s.mean()) / s.std()
    terms = {"heavy_x_stand_or_taxi_point_300m": heavy & p.cell.map(stand).values.astype(bool),
             "heavy_x_mrt_lt300m": heavy & (dm < 300), "heavy_x_mrt_300_1000m": heavy & (dm >= 300) & (dm < 1000),
             "heavy_x_central_area": heavy & p.cell.map(c.central_area).values.astype(bool),
             "heavy_x_mall": heavy & (p.cell.map(c.malls).values > 0),
             "heavy_x_hdb_units_sd": heavy * p.cell.map(z(np.log1p(cc.hdb_units)) if "hdb_units" in cc else 0).fillna(0).values,
             "heavy_x_dist_city_sd": heavy * p.cell.map(z(cc.dist_city_km)).fillna(0).values}
    names = E.REGS + list(terms)
    XX = np.column_stack([X] + [np.asarray(v, "float32") for v in terms.values()]).astype("float32")
    rows = []
    for kind, fes in (("abs", fe_abs), ("share", fe_share)):
        r = fepois(p.vacant.values, XX, names, fes, day, xt_dtype="float32")
        V = r.attrs["vcov"]
        rr = pct(r)
        rr.attrs = {}
        rr.insert(0, "model", kind)
        rows.append(rr.reset_index(names="term"))
        for lab, t in (("heavy, with stand / taxi point within 300 m", ["heavy", "heavy_x_stand_or_taxi_point_300m"]),
                       ("heavy, without (reference)", ["heavy"])):
            b = r.coef[t].sum()
            se = np.sqrt(V.loc[t, t].values.sum())
            rows.append(pd.DataFrame([{"model": kind, "term": "CONTRAST: " + lab, "coef": b, "se": se,
                                       "pct": 100 * (np.exp(b) - 1), "pct_lo": 100 * (np.exp(b - 1.96 * se) - 1),
                                       "pct_hi": 100 * (np.exp(b + 1.96 * se) - 1)}]))
    t = pd.concat(rows)
    t.to_csv(TABLES / "stands_effect.csv", index=False, float_format="%.5f")
    print(t[t.term.str.contains("stand|CONTRAST")][["model", "term", "pct", "pct_lo", "pct_hi"]].round(2).to_string(index=False))
    print("cells with a stand or taxi point within 300 m:", int(stand[c.eligible].sum()), "of", int(c.eligible.sum()))


def notes(r):
    n = []
    n.append("arterial road in cell" if r.road_km_arterial > 0.3 else "no arterial road in cell")
    if r.dist_mrt_m < 300:
        n.append("MRT exit within 300 m")
    if r.malls > 0:
        n.append("mall in cell")
    if r.hospitals > 0:
        n.append("hospital in cell")
    if r.lu_residential > 0.3:
        n.append("mainly residential")
    return "; ".join(n)


def part_b(c):
    e = pd.read_csv(TABLES / "cell_rain_effects.csv")
    d = pd.read_csv(TABLES / "taxi_deserts.csv")
    no_stand = c.set_index("cell").eval("taxi_stands_300m + osm_taxi_points_300m == 0")
    hit = e[e.tested].sort_values("taxis_lost_per_heavy_half_hour", ascending=False).head(100)
    hit = hit[hit.cell.map(no_stand).fillna(False).astype(bool)]
    hit = hit.merge(c, on="cell", suffixes=("", "_c"))
    hit["reason"] = "rain-hit (top 100 by taxis lost in heavy rain)"
    hit["feasibility_notes"] = hit.apply(notes, axis=1)
    des = d[d.cell.map(no_stand).fillna(False).astype(bool)].merge(c, on="cell", suffixes=("", "_c"))
    des["reason"] = "taxi desert (few vacant taxis per resident)"
    des["feasibility_notes"] = des.apply(notes, axis=1)
    cols = ["reason", "planning_area", "subzone", "nearest_mrt", "landmarks", "feasibility_notes", "cell"]
    out = pd.concat([hit.assign(score=hit.taxis_lost_per_heavy_half_hour)[cols + ["score"]],
                     des.assign(score=des.residents)[cols + ["score"]]], ignore_index=True)
    names = pd.read_csv(TABLES / "names_cells.csv").set_index("cell")
    for k in ("planning_area", "subzone", "nearest_mrt", "landmarks"):
        out[k] = out.cell.map(names[k])
    out["planning_area"] = out.planning_area.str.title()
    out["subzone"] = out.subzone.str.title()
    out["note"] = "No cost, kerb-space or traffic-safety data were available; feasibility notes are qualitative."
    out.to_csv(TABLES / "stands_candidates.csv", index=False, float_format="%.2f")
    print(out.groupby("reason").head(10)[["reason", "planning_area", "subzone", "landmarks", "score",
                                          "feasibility_notes"]].to_string(index=False))


def part_c(c):
    m = joblib.load(INTERIM / "rf_rain_abs.joblib")
    cols = m["columns"]
    X = F.design_matrix(c, [k for k in cols if k in F.NUM])
    for b in [k for k in cols if k in F.BOOL]:
        X[b] = c[b].astype(float).values
    pred = m["model"].predict(X[cols])
    c = c.copy()
    c["pred_heavy_abs_pct"] = 100 * (np.exp(pred) - 1)
    c["status"] = np.where(c.eligible, "analysed (prediction shown; measured effect in cell_rain_effects.csv)",
                           "predicted (no reliable taxi data)")
    e = pd.read_csv(TABLES / "cell_rain_effects.csv").set_index("cell")
    c["measured_heavy_abs_pct"] = c.cell.map(e.abs_pct)
    c[["cell", "planning_area", "subzone", "eligible", "land", "status", "residents", "pred_heavy_abs_pct",
       "measured_heavy_abs_pct"]].to_csv(TABLES / "stands_predicted_sensitivity_cells.csv", index=False, float_format="%.3f")
    land = c[c.land]
    w = land.residents.clip(lower=1)
    for lvl in ("planning_area", "subzone"):
        g = land.assign(w=w).groupby(lvl).apply(lambda q: pd.Series({
            "cells": len(q), "residents": q.residents.sum(),
            "pred_heavy_abs_pct_resident_weighted": np.average(q.pred_heavy_abs_pct, weights=q.w),
            "share_cells_predicted_only": (~q.eligible).mean()}), include_groups=False).reset_index()
        g[lvl] = g[lvl].str.title()
        g.sort_values("pred_heavy_abs_pct_resident_weighted").to_csv(TABLES / f"stands_predicted_by_{lvl}.csv",
                                                                     index=False, float_format="%.3f")
    print(g.sort_values("pred_heavy_abs_pct_resident_weighted").head(15).round(2).to_string(index=False))
    style()
    d02 = importlib.import_module("analysis.02_describe")
    fig, ax = plt.subplots(figsize=(9, 5.4))
    d02.draw_base(ax)
    div = LinearSegmentedColormap.from_list("d", ["#b8431c", ORANGE, "#f2f1ed", "#7fb0e8", BLUE_DARK])
    norm = TwoSlopeNorm(vcenter=0, vmin=-30, vmax=10)
    N.draw_cells(ax, land.cell.values, land.pred_heavy_abs_pct.clip(-30, 10).values, div, norm)
    for x_, y_ in zip(land[~land.eligible].lon, land[~land.eligible].lat):
        ax.plot(x_, y_, ".", ms=1.5, color="#52514e", zorder=4)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=div), ax=ax, orientation="horizontal", fraction=0.05, pad=0.02,
                 label="Predicted heavy-rain effect on vacant taxis (%, random forest on place characteristics)")
    ax.set_title("Predicted rain sensitivity for every land cell (dots: predicted only, no reliable taxi data)",
                 fontsize=10)
    fig.tight_layout()
    save(fig, "stands_predicted_sensitivity", "Sources: model from step 12 (data.gov.sg taxi availability, NEA rainfall, "
         "URA MP2019, HDB, Census 2020, OSM, LTA). Predictions outside analysed cells are extrapolations.")
    plt.close(fig)


def main():
    c = pd.read_csv(TABLES / "cell_characteristics.csv")
    part_a(c)
    part_b(c)
    part_c(c)


if __name__ == "__main__":
    main()
