"""Step 18: rain measurement error (pre-registration: decision 116). Fit period, main sample.

Effects for cell-days near (<= 1 km) vs far (> 1 km) from the nearest working gauge; heavy x far interactions;
reliability ratio of the cell rain measure using the 2nd/3rd nearest gauges.
Usage: .venv/bin/python -m analysis.18_gauges
"""
from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from analysis.common import INTERIM, TABLES
from analysis.fepois_hd import fepois, pct
from pipeline.grid import to_xy

M = importlib.import_module("analysis.03_effects_more")


def gauge_distance():
    P1 = importlib.import_module("analysis.01_panel")
    rain = P1.Rain()
    cells = pd.read_parquet(INTERIM / "cells.parquet")
    cells = cells[cells.eligible].sort_values("cell").reset_index(drop=True)
    cx, cy = to_xy(cells.lon.values, cells.lat.values)
    rows = []
    for d, day in enumerate(rain.days):
        w = np.flatnonzero(rain.working[d])
        if not len(w):
            continue
        dist = cKDTree(np.c_[rain.gx[w], rain.gy[w]]).query(np.c_[cx, cy])[0]
        rows.append(pd.DataFrame({"date": day, "cell": cells.cell.values, "gauge_dist_m": dist}))
    return pd.concat(rows, ignore_index=True)


def main():
    gd = gauge_distance()
    gd.to_parquet(INTERIM / "gauge_distance_by_day.parquet", index=False)
    p = M.load(extra=["mmh_3g"])
    p["date"] = p.ts.dt.normalize()
    p = p.merge(gd, on=["date", "cell"], how="left")
    far = (p.gauge_dist_m.values > 1000)
    print("cell-days > 1 km from a working gauge:", round(float(far.mean()), 3))
    rows = []
    for lab, m in (("near (<= 1 km)", ~far), ("far (> 1 km)", far)):
        q = p[m].reset_index(drop=True)
        for r in M.fit(lab, q, M.base_X(q), M.REGS):
            r = r.loc[M.BANDS].reset_index(names="term")
            r.attrs = {}
            r["rows"] = len(q)
            rows.append(r)
    b = p.rain_band.values
    cols = M.base_X(p) + [(b == 1) & far, (b == 2) & far, (b == 3) & far]
    nm = M.REGS + ["light_x_far", "moderate_x_far", "heavy_x_far"]
    for r in M.fit("interaction", p, cols, nm):
        r = r.loc[["light", "moderate", "heavy", "light_x_far", "moderate_x_far", "heavy_x_far"]].reset_index(names="term")
        r.attrs = {}
        rows.append(r)
    t = pd.concat(rows)
    # reliability ratio: nearest gauge vs mean of 2nd and 3rd nearest (from the 3-gauge mean)
    m1 = p.mmh.values.astype(float)
    m3 = p.mmh_3g.values.astype(float)
    r23 = (3 * m3 - m1) / 2
    ok = np.isfinite(m1) & np.isfinite(r23)
    lam = float(np.cov(m1[ok], r23[ok])[0, 1] / np.var(m1[ok]))
    corr = float(np.corrcoef(m1[ok], r23[ok])[0, 1])
    t["reliability_ratio"] = lam
    t["corr_nearest_vs_2nd3rd"] = corr
    t.to_csv(TABLES / "gauges_measurement_error.csv", index=False, float_format="%.5f")
    print(t[["variant", "model", "term", "pct", "pct_lo", "pct_hi"]].round(2).to_string(index=False))
    print("reliability ratio", round(lam, 3), "corr", round(corr, 3))


if __name__ == "__main__":
    main()
