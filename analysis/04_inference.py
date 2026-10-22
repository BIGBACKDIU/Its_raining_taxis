"""Step 4: inference (HANDOFF section 6, step 4).

Clustered errors from step 3 are the primary inference. This step adds:
  1. Day-block bootstrap of a fast ratio statistic T = log(sum vacant / sum fit0) over rain slots of each band,
     where fit0 is a no-rain Poisson model (cell + how^month + ym^regime) fitted on dry rows only
     (no rain in the cell for the past 90 minutes). Multi-day storm blocks (consecutive days with heavy rain
     anywhere) as a check.
  2. Permutation test (supporting evidence only): whole days' rain patterns are swapped among days in the same
     month and day type (weekday / weekend / holiday); T is recomputed with each day's own vacant and fit0.
  3. Cell hotspots: per-cell T for heavy rain with day-bootstrap standard errors; Benjamini-Hochberg FDR 10%.

Sample: fit period, main sample. Outputs: outputs/tables/inference_*.csv, figures inference_permutation,
inference_hotspots.
Usage: .venv/bin/python -m analysis.04_inference
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Patch

from analysis.common import (BLUE, BLUE_DARK, FIT, INTERIM, MUTED, NOT_ANALYSED, ORANGE, RAIN_BANDS, SEED, TABLES,
                             load_panel, save, style)

B_BOOT = 2000
N_PERM = 1000
FDR_Q = 0.10
MIN_HEAVY_ROWS = 100


def ipf_poisson(y, groups, n_iter=500, tol=1e-10):
    """Poisson MLE of log mu = sum of group effects (no regressors), by iterative proportional fitting."""
    codes = [pd.factorize(g)[0] for g in groups]
    eff = [np.zeros(c.max() + 1) for c in codes]
    for it in range(n_iter):
        step = 0.0
        for c, e in zip(codes, eff):
            eta = sum(ee[cc] for cc, ee in zip(codes, eff))
            num = np.bincount(c, y, len(e))
            den = np.bincount(c, np.exp(eta), len(e))
            d = np.log(np.maximum(num, 1e-12) / den)
            e += d
            step = max(step, np.abs(d).max())
        if step < tol:
            break
    return codes, eff


def load():
    cols = ["ts", "cell", "vacant", "rain_band", "mmh", "mmh_lag1", "mmh_lag2", "how", "month", "ym", "regime_id",
            "daytype", "drop_main", "baseline"]
    p = load_panel(range(2022, 2026), columns=cols, filters=[("ts", ">=", FIT[0]), ("ts", "<=", FIT[1])])
    p = p[~p.drop_main & (p.rain_band >= 0) & p.mmh_lag1.notna() & p.mmh_lag2.notna() & p.baseline.notna()]
    return p.reset_index(drop=True)


def fit0(p):
    """No-rain model fitted on dry rows; predictions for every row."""
    hm = p.how.values.astype(np.int32) * 100 + p.month.values
    ymr = p.ym.values.astype(np.int64) * 100 + p.regime_id.values
    dry = ((p.mmh.values == 0) & (p.mmh_lag1.values == 0) & (p.mmh_lag2.values == 0))
    groups = [p.cell.values, hm, ymr]
    codes, eff = ipf_poisson(p.vacant.values[dry].astype(float), [g[dry] for g in groups])
    pred = np.zeros(len(p))
    for g, c, e in zip(groups, codes, eff):
        lev = pd.Series(np.arange(c.max() + 1), index=pd.unique(g[dry]))   # factorize order = first appearance
        idx = pd.Series(g).map(lev).values
        pred += np.where(np.isnan(idx), np.nan, e[np.nan_to_num(idx).astype(int)])
    return np.exp(pred), dry


def main():
    style()
    rng = np.random.default_rng(SEED)
    p = load()
    f0, dry = fit0(p)
    p["fit0"] = f0
    p = p[np.isfinite(p.fit0)].reset_index(drop=True)
    p["day"] = p.ts.dt.normalize()
    days = np.sort(p.day.unique())
    di = np.searchsorted(days, p.day.values)
    D = len(days)
    # per-day sums by band
    out = {"rows": int(len(p)), "days": int(D), "dry_rows_used_for_fit0": int(dry.sum())}
    VD = np.zeros((D, 4))
    FD = np.zeros((D, 4))
    for b in range(4):
        m = p.rain_band.values == b
        VD[:, b] = np.bincount(di[m], p.vacant.values[m], D)
        FD[:, b] = np.bincount(di[m], p.fit0.values[m], D)
    T = np.log(VD.sum(0) / FD.sum(0))
    # day bootstrap
    W = rng.multinomial(D, np.full(D, 1 / D), size=B_BOOT).astype(float)
    Tb = np.log((W @ VD) / (W @ FD))
    # storm blocks: consecutive days with heavy rain anywhere form one block
    heavy_day = FD[:, 3] > 0
    gap = np.r_[True, np.diff(days.astype("datetime64[D]").astype(int)) > 1]
    block = np.cumsum(~(heavy_day & np.r_[False, heavy_day[:-1]]) | gap)
    nb = block.max() + 1
    VB = np.zeros((nb, 4))
    FB = np.zeros((nb, 4))
    np.add.at(VB, block, VD)
    np.add.at(FB, block, FD)
    WB = rng.multinomial(nb, np.full(nb, 1 / nb), size=B_BOOT).astype(float)
    Tbb = np.log((WB @ VB) / (WB @ FB))
    rows = []
    for b, name in enumerate(RAIN_BANDS):
        rows.append({"band": name, "T": T[b], "pct": 100 * (np.exp(T[b]) - 1),
                     "day_boot_lo": 100 * (np.exp(np.quantile(Tb[:, b], 0.025)) - 1),
                     "day_boot_hi": 100 * (np.exp(np.quantile(Tb[:, b], 0.975)) - 1),
                     "storm_block_lo": 100 * (np.exp(np.quantile(Tbb[:, b], 0.025)) - 1),
                     "storm_block_hi": 100 * (np.exp(np.quantile(Tbb[:, b], 0.975)) - 1),
                     "rows": int((p.rain_band == b).sum())})
    out["storm_blocks"] = int(nb)
    out["multi_day_blocks"] = int((np.bincount(block) > 1).sum())

    # permutation: swap whole days' rain patterns within month x day type
    slot = ((p.ts - p.day).dt.total_seconds() // 1800).astype(int).values
    cell_codes, cell_lev = pd.factorize(p.cell)
    C = len(cell_lev)
    V = np.zeros((D, 48, C), "float32")
    F = np.zeros((D, 48, C), "float32")
    Bd = np.full((D, 48, C), -1, "int8")
    V[di, slot, cell_codes] = p.vacant.values
    F[di, slot, cell_codes] = p.fit0.values
    Bd[di, slot, cell_codes] = p.rain_band.values
    dmeta = p.groupby("day").agg(ym=("ym", "first"), daytype=("daytype", "max"))
    strata = (dmeta.ym.astype(str) + "_" + np.where(dmeta.daytype.values > 0, "we", "wd")).values
    perm_T = np.zeros((N_PERM, 3))
    groups = [np.flatnonzero(strata == s) for s in np.unique(strata)]
    for i in range(N_PERM):
        perm = np.arange(D)
        for g in groups:
            perm[g] = rng.permutation(g)
        M = Bd[perm]
        for k, b in enumerate((1, 2, 3)):
            mk = M == b
            perm_T[i, k] = np.log(V[mk].sum() / F[mk].sum())
    for k, b in enumerate((1, 2, 3)):
        r = rows[b]
        r["perm_null_mean_pct"] = 100 * (np.exp(perm_T[:, k].mean()) - 1)
        r["perm_p_two_sided"] = float((np.abs(perm_T[:, k] - perm_T[:, k].mean()) >= abs(T[b] - perm_T[:, k].mean())).mean())
        r["perm_draws"] = N_PERM
    tab = pd.DataFrame(rows)
    tab.to_csv(TABLES / "inference_ratio_statistic.csv", index=False, float_format="%.4f")
    pd.DataFrame(perm_T, columns=["light", "moderate", "heavy"]).to_csv(TABLES / "inference_permutation_draws.csv",
                                                                        index=False, float_format="%.5f")
    print(tab.round(3).to_string())

    # cell hotspots (heavy rain)
    m = p.rain_band.values == 3
    VC = np.zeros((D, C))
    FC = np.zeros((D, C))
    np.add.at(VC, (di[m], cell_codes[m]), p.vacant.values[m])
    np.add.at(FC, (di[m], cell_codes[m]), p.fit0.values[m])
    nrows = np.bincount(cell_codes[m], minlength=C)
    Tc = np.log(VC.sum(0) / FC.sum(0))
    with np.errstate(divide="ignore", invalid="ignore"):
        Tcb = np.log((W @ VC) / (W @ FC))
    se = np.nanstd(Tcb, axis=0, ddof=1)
    from scipy.stats import norm
    z = Tc / se
    pv = 2 * norm.sf(np.abs(z))
    ok = (nrows >= MIN_HEAVY_ROWS) & np.isfinite(pv)
    q = np.full(C, np.nan)
    order = np.argsort(pv[ok])
    ranked = pv[ok][order] * ok.sum() / (np.arange(ok.sum()) + 1)
    qv = np.minimum.accumulate(ranked[::-1])[::-1]
    q_ok = np.empty(ok.sum())
    q_ok[order] = np.minimum(qv, 1)
    q[ok] = q_ok
    hs = pd.DataFrame({"cell": cell_lev, "heavy_rows": nrows, "T": Tc, "pct": 100 * (np.exp(Tc) - 1), "se": se, "z": z,
                       "p": pv, "q_bh": q})
    hs["hotspot"] = np.where(hs.q_bh <= FDR_Q, np.where(hs["T"] < 0, "significantly lower", "significantly higher"),
                             np.where(ok, "not significant", "too few heavy-rain rows"))
    hs.to_csv(TABLES / "inference_hotspots.csv", index=False, float_format="%.5f")
    out["hotspots"] = hs.hotspot.value_counts().to_dict()
    out["bh_fdr"] = FDR_Q
    (TABLES / "inference_summary.json").write_text(json.dumps(out, indent=2, default=int))
    print(out)
    charts(tab, perm_T, hs)


def charts(tab, perm_T, hs):
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=False)
    for k, (ax, b) in enumerate(zip(axes, ["light", "moderate", "heavy"])):
        ax.hist(100 * (np.exp(perm_T[:, k]) - 1), bins=40, color="#c8c7c2", label="Permutation null (rain days swapped)")
        r = tab.set_index("band").loc[b]
        ax.axvline(r.pct, color=BLUE_DARK, lw=2, label="Observed")
        ax.axvspan(r.day_boot_lo, r.day_boot_hi, color=BLUE, alpha=0.2, lw=0, label="95% day-bootstrap CI")
        ax.set_title(f"{b.capitalize()} rain (permutation p = {r.perm_p_two_sided:.3f})", fontsize=9.5)
        ax.set_xlabel("% vacant taxis vs no-rain model")
        ax.grid(False)
    axes[0].set_ylabel("Permutation draws")
    axes[0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Observed rain associations are far outside what shuffled rain days produce", x=0.01, ha="left",
                 fontsize=10.5)
    fig.tight_layout()
    save(fig, "inference_permutation", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025. "
         f"{N_PERM} permutations within month x day type; {B_BOOT} day-bootstrap draws.")
    plt.close(fig)
    # hotspot map
    d02 = __import__("importlib").import_module("analysis.02_describe")
    allc = pd.read_parquet(INTERIM / "cells.parquet")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    d02.draw_base(ax)
    div = LinearSegmentedColormap.from_list("d", ["#b8431c", ORANGE, "#f2f1ed", "#7fb0e8", BLUE_DARK])
    norm = TwoSlopeNorm(vcenter=0, vmin=-40, vmax=20)
    v = np.where(hs.hotspot.str.startswith("significantly"), hs.pct.clip(-40, 20), np.nan)
    d02.cell_squares(ax, hs.cell.values, v, div, norm, allc)
    # non-significant cells: pale outline fill
    ns = hs[hs.hotspot == "not significant"]
    from pipeline.grid import to_lonlat
    for c in ns.cell:
        x, y = c // 1000, c % 1000
        lon0, lat0 = to_lonlat(x * 1000, y * 1000)
        lon1, lat1 = to_lonlat((x + 1) * 1000, (y + 1) * 1000)
        ax.add_patch(plt.Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0, facecolor="#f2f1ed", edgecolor="white",
                                   lw=0.3, zorder=3))
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=div), ax=ax, orientation="horizontal", fraction=0.05, pad=0.02,
                 label="Heavy rain vs no-rain model, % vacant taxis (significant cells only)")
    n_low = int((hs.hotspot == "significantly lower").sum())
    ax.legend(handles=[Patch(color="#f2f1ed", label="Not significant"), Patch(color=NOT_ANALYSED, label="Not analysed")],
              loc="upper left", fontsize=8)
    ax.set_title(f"{n_low} cells have significantly fewer vacant taxis in heavy rain (Benjamini-Hochberg FDR 10%)",
                 fontsize=10)
    fig.tight_layout()
    save(fig, "inference_hotspots", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025. "
         "Per-cell ratio statistic with day-bootstrap standard errors.")
    plt.close(fig)


if __name__ == "__main__":
    main()
