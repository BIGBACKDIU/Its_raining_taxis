"""Step 16: dose, duration and after-effects (pre-registration: decision 114). Fit period, main sample.

(a) intensity-response spline, (b) intensity x wet-spell length, (c) post-rain hangover, (d) recovery time by
rain-response type. Supply associations only.
Usage: .venv/bin/python -m analysis.16_dose
"""
from __future__ import annotations

import gc
import importlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.common import BLUE, BLUE_DARK, MUTED, ORANGE, TABLES, save, style
from analysis.fepois_hd import fepois, pct

M = importlib.import_module("analysis.03_effects_more")
E = importlib.import_module("analysis.03_effects")
KNOTS = (1, 2.5, 5, 10, 20, 40)
CAP = 80.0
GRID = np.r_[0, 0.5, 1, 2, 2.5, 4, 5, 7.5, 10, 15, 20, 30, 40, 60]


def spline_basis(x):
    from patsy import dmatrix
    x = np.round(np.minimum(np.asarray(x, float), CAP), 3)
    spec = f"cr(x, knots={KNOTS}, lower_bound=0, upper_bound={CAP}) - 1"
    ux, inv = np.unique(x, return_inverse=True)          # rain takes few distinct values: evaluate once
    Bu = np.asarray(dmatrix(spec, {"x": np.r_[0.0, ux]}))
    Bu = (Bu[1:] - Bu[0])[:, 1:]       # centred at 0 mm/h; cr columns sum to one, so drop one to keep full rank
    return Bu[inv].astype("float32"), spec


def curve(r, names, spec):
    from patsy import dmatrix
    Gf = np.asarray(dmatrix(spec, {"x": np.r_[0.0, GRID]}))
    G = (Gf[1:] - Gf[0])[:, 1:]
    b = r.coef[names].values
    V = r.attrs["vcov"].loc[names, names].values
    f = G @ b
    se = np.sqrt(np.einsum("ij,jk,ik->i", G, V, G))
    return pd.DataFrame({"mmh": GRID, "pct": 100 * (np.exp(f) - 1), "lo": 100 * (np.exp(f - 1.96 * se) - 1),
                         "hi": 100 * (np.exp(f + 1.96 * se) - 1)})


def main():
    style()
    p = M.load(extra=["wet_min", "dry_min"])
    fe_abs, fe_share, day = M.fes(p)
    y = p.vacant.values
    rows, curves = [], []
    # (a) spline
    B, spec = spline_basis(p.mmh.values)
    sn = [f"s{k}" for k in range(B.shape[1])]
    X = np.column_stack([B, p.mmh_lag1.values, p.mmh_lag2.values]).astype("float32")
    for kind, fes in (("abs", fe_abs), ("share", fe_share)):
        r = fepois(y, X, sn + ["mmh_lag1", "mmh_lag2"], fes, day, xt_dtype="float32")
        c = curve(r, sn, spec)
        c.insert(0, "model", kind)
        curves.append(c)
        print(kind, c.round(2).to_string(index=False), flush=True)
    del X, B
    gc.collect()
    # (b) duration x intensity
    w = p.wet_min.values
    wb = np.select([w <= 30, w <= 60, w <= 120], [0, 1, 2], 3)
    labs = ["<=30", "31-60", "61-120", ">120"]
    cols, names = [], []
    for k, band in ((1, "light"), (2, "moderate"), (3, "heavy")):
        for j, lab in enumerate(labs):
            cols.append((p.rain_band.values == k) & (wb == j))
            names.append(f"{band}_wet{lab}")
    X = np.column_stack(cols + [p.mmh_lag1.values, p.mmh_lag2.values]).astype("float32")
    for kind, fes in (("abs", fe_abs), ("share", fe_share)):
        r = pct(fepois(y, X, names + ["mmh_lag1", "mmh_lag2"], fes, day, xt_dtype="float32"))
        r.attrs = {}
        r = r.loc[names].reset_index(names="term")
        r.insert(0, "part", "duration")
        r.insert(1, "model", kind)
        r["rows"] = [int(c.sum()) for c in cols]
        rows.append(r)
    del X
    gc.collect()
    # (c) hangover
    dm = p.dry_min.values
    dry_now = p.mmh.values == 0
    bins = [(30, 60), (60, 90), (90, 120), (120, 150), (150, 180), (180, 360)]
    cols = [p.rain_band.values == 1, p.rain_band.values == 2, p.rain_band.values == 3]
    names = ["light", "moderate", "heavy"]
    for a, b in bins:
        cols.append(dry_now & (dm >= a) & (dm < b))
        names.append(f"dry_{a}-{b}min_after_rain")
    X = np.column_stack(cols).astype("float32")
    for kind, fes in (("abs", fe_abs), ("share", fe_share)):
        r = pct(fepois(y, X, names, fes, day, xt_dtype="float32"))
        r.attrs = {}
        r = r.reset_index(names="term")
        r.insert(0, "part", "hangover (reference: dry >= 6 h)")
        r.insert(1, "model", kind)
        r["rows"] = [int(c.sum()) for c in cols]
        rows.append(r)
    del X, p
    gc.collect()
    t = pd.concat(rows)
    t.to_csv(TABLES / "dose_duration_hangover.csv", index=False, float_format="%.5f")
    cv = pd.concat(curves)
    cv.to_csv(TABLES / "dose_spline_curve.csv", index=False, float_format="%.4f")
    print(t[["part", "model", "term", "pct", "pct_lo", "pct_hi", "rows"]].round(2).to_string(index=False), flush=True)
    # (d) recovery by type
    ty = pd.read_csv(TABLES / "risk_types.csv").set_index("cell").type
    q = E.load_fit()
    ev, _ = E.onsets(q)
    s = E.sample(q)
    q, ev = q[s].reset_index(drop=True), ev[s]
    rec = []
    for tval in (0, 1):
        m = q.cell.map(ty).values == tval
        qq = q[m].reset_index(drop=True)
        evt = np.where(np.isnan(ev[m]), -999, ev[m]).astype(int)
        _, fa, fs, dd = E.design(qq)
        for kind, f in (("abs", fa), ("share", fs)):
            es = E.event_study(f"type{tval}_{kind}", qq.vacant.values, evt, f, dd)
            es["type"] = tval
            after = es[es.event_min >= 0].sort_values("event_min")
            ok = (after.pct_lo <= 0) & (after.pct_hi >= 0)
            rt = next((int(r.event_min) for i, r in enumerate(after.itertuples()) if ok.iloc[i:].all()), None)
            es["recovery_min"] = rt
            rec.append(es)
    R = pd.concat(rec)
    R.to_csv(TABLES / "dose_recovery_by_type.csv", index=False, float_format="%.4f")
    print(R.groupby(["model", "type"]).recovery_min.first().to_string())
    # chart: spline + hangover
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    for kind, col in (("abs", BLUE_DARK), ("share", BLUE)):
        c = cv[cv.model == kind]
        ax.fill_between(c.mmh, c.lo, c.hi, color=col, alpha=0.15, lw=0)
        ax.plot(c.mmh, c.pct, color=col, lw=2, label="Absolute" if kind == "abs" else "Share of citywide")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("Rain in the previous 30 min at the cell (mm/h)")
    ax.set_ylabel("% vacant taxis vs dry")
    ax.legend(fontsize=8)
    ax.set_title("Intensity: the drop deepens with intensity, then levels off", fontsize=9.5)
    ax = axes[1]
    h = t[t.part.str.startswith("hangover") & t.term.str.startswith("dry_")]
    for kind, col, off in (("abs", BLUE_DARK, -4), ("share", BLUE, 4)):
        hh = h[h.model == kind]
        x = np.array([int(s.split("_")[1].split("-")[0]) for s in hh.term]) + off
        ax.errorbar(x + 15, hh.pct, yerr=[hh.pct - hh.pct_lo, hh.pct_hi - hh.pct], fmt="o", color=col, capsize=2,
                    label="Absolute" if kind == "abs" else "Share")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("Minutes since rain stopped at the cell (bin start + 15)")
    ax.set_ylabel("% vacant taxis vs cells dry for >= 6 h")
    ax.legend(fontsize=8)
    ax.set_title("After rain: how long vacant taxis stay below normal", fontsize=9.5)
    fig.tight_layout()
    save(fig, "dose_intensity_hangover", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025; "
         "Poisson FE, 95% CI clustered by day. Association, not cause.")
    plt.close(fig)


if __name__ == "__main__":
    main()
