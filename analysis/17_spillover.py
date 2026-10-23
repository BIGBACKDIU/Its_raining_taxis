"""Step 17: redistribution in island-wide rain and spatial spillovers (pre-registration: decision 115).
Fit period, main sample; supply associations only.
Usage: .venv/bin/python -m analysis.17_spillover
"""
from __future__ import annotations

import gc
import importlib

import numpy as np
import pandas as pd

from analysis.common import SEED, TABLES, save, style
from analysis.fepois_hd import fepois, pct

M = importlib.import_module("analysis.03_effects_more")
F = importlib.import_module("analysis.12_factors")


def main():
    style()
    inf = importlib.import_module("analysis.04_inference")
    # (a) island-wide rain redistribution
    p = M.load(extra=["gauges_wet_share", "rain_2km", "rain_ring", "daytype"])
    f0, _ = inf.fit0(p)
    p["fit0"] = f0
    ok = np.isfinite(p.fit0.values)
    tot = p[ok].groupby("ts")[["vacant", "fit0"]].transform("sum")
    p.loc[ok, "fit0s"] = p.loc[ok, "fit0"] * tot.vacant / tot.fit0
    isl = ok & (p.gauges_wet_share.fillna(0).values >= 0.5)
    h = p[isl]
    days = np.sort(h.ts.dt.normalize().unique())
    di = np.searchsorted(days, h.ts.dt.normalize().values)
    cc, cl = pd.factorize(h.cell)
    V, S = np.zeros((len(days), len(cl))), np.zeros((len(days), len(cl)))
    np.add.at(V, (di, cc), h.vacant.values)
    np.add.at(S, (di, cc), h.fit0s.values)
    W = np.random.default_rng(SEED).multinomial(len(days), np.full(len(days), 1 / len(days)), size=1000).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        b = (W @ V) / (W @ S) - 1
    names = pd.read_csv(TABLES / "names_cells.csv")
    r = pd.DataFrame({"cell": cl, "rows": np.bincount(cc, minlength=len(cl)),
                      "share_pct": 100 * (V.sum(0) / S.sum(0) - 1), "lo": 100 * np.nanquantile(b, 0.025, 0),
                      "hi": 100 * np.nanquantile(b, 0.975, 0)})
    r["direction"] = np.where(r.lo > 0, "gains share", np.where(r.hi < 0, "loses share", "no clear change"))
    r = r.merge(names[["cell", "planning_area", "subzone", "nearest_mrt", "landmarks", "place", "lon", "lat"]], on="cell")
    r.sort_values("share_pct").to_csv(TABLES / "spillover_islandwide_share.csv", index=False, float_format="%.3f")
    print("island-wide rain snapshots:", h.ts.nunique(), "days:", len(days))
    print(r.direction.value_counts().to_dict())
    print(r.sort_values("share_pct").head(10)[["planning_area", "subzone", "landmarks", "share_pct", "lo", "hi"]]
          .round(1).to_string(index=False))
    print(r.sort_values("share_pct", ascending=False).head(10)[["planning_area", "subzone", "landmarks", "share_pct",
                                                                 "lo", "hi"]].round(1).to_string(index=False))
    # characteristics of gainers vs losers (WLS on kept step-12 characteristics)
    import statsmodels.api as sm
    c = pd.read_csv(TABLES / "cell_characteristics.csv")
    d = r.merge(c, on="cell", suffixes=("", "_c"))
    keep = [k for k in pd.read_csv(TABLES / "factors_cell_wls.csv").query("outcome == 'share'").characteristic.unique()]
    X = F.design_matrix(d, [k for k in keep if k in F.NUM])
    for bcol in [k for k in keep if k in F.BOOL]:
        X[bcol] = d[bcol].astype(float).values
    y = np.log1p(d.share_pct / 100)
    se = (np.log1p(d.hi / 100) - np.log1p(d.lo / 100)) / 3.92
    good = np.isfinite(y) & np.isfinite(se) & (se > 0)
    m = sm.WLS(y[good], sm.add_constant(X[good]), weights=1 / se[good] ** 2).fit(cov_type="HC1")
    ct = pd.DataFrame({"coef_log_per_sd": m.params, "se": m.bse, "p": m.pvalues})
    ct["pct_per_sd"] = 100 * (np.exp(ct.coef_log_per_sd) - 1)
    ct.to_csv(TABLES / "spillover_islandwide_characteristics.csv", float_format="%.5f")
    print(ct[ct.p < 0.05].round(3).to_string())
    # (b) spillover model: own + within 2 km + 2-5 km ring together
    near, ring = p.rain_2km.fillna(0).values, p.rain_ring.fillna(0).values
    cols = M.base_X(p) + [(near > 0) & (near <= 2.5), near > 2.5, (ring > 0) & (ring <= 2.5), ring > 2.5]
    nm = M.REGS + ["near2km_light", "near2km_heavier", "ring2_5km_light", "ring2_5km_heavier"]
    res = M.fit("spillover", p, cols, nm)
    for x in res:
        x.attrs = {}
    out = pd.concat(res)
    out.index.name = "term"
    out.to_csv(TABLES / "spillover_model.csv", float_format="%.5f")


if __name__ == "__main__":
    main()
