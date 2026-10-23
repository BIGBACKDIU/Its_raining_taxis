"""Step 13: new MRT stations as a natural experiment (pre-registration: decisions 109-111).

Stacked difference-in-differences by opening cohort: cells within 800 m of a newly opened station vs matched
cells > 2 km from any new station; (a) dry-weather vacant supply (event study, cell-month), (b) the heavy-rain
effect (Poisson FE triple interaction on the cell-snapshot panel).
Usage: .venv/bin/python -m analysis.13_mrt_did
"""
from __future__ import annotations

import importlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis import geo
from analysis.common import (BLUE, BLUE_DARK, INTERIM, MUTED, ORANGE, SEED, TABLES, TEST, load_panel,
                             log_test_scoring, save, style)
from analysis.fepois_hd import fepois, pct
from pipeline.grid import to_xy

COHORTS = {"TEL3": "2022-11-13", "TEL4": "2024-06-23", "NEL extension": "2024-12-10", "DTL infill": "2025-02-28"}
WIN = 12
COLS = ["ts", "cell", "vacant", "rain_band", "mmh", "mmh_lag1", "mmh_lag2", "how", "month", "ym", "regime_id",
        "drop_main"]


def treated_and_controls():
    st, _ = geo.mrt()
    c = pd.read_csv(TABLES / "cell_characteristics.csv")
    c = c[c.eligible].reset_index(drop=True)
    x, y = to_xy(c.lon.values, c.lat.values)
    new = st[st.opened.notna()]
    nx_, ny_ = to_xy(new.lon.values, new.lat.values)
    dmin_new = np.hypot(x[:, None] - nx_[None, :], y[:, None] - ny_[None, :])
    far = dmin_new.min(1) > 2000
    rows = []
    for coh, date in COHORTS.items():
        stc = new[new.stage.str.startswith(coh.split()[0]) & (new.opened == pd.Timestamp(date))]
        sx, sy = to_xy(stc.lon.values, stc.lat.values)
        d = np.hypot(x[:, None] - sx[None, :], y[:, None] - sy[None, :]).min(1)
        tr = np.flatnonzero(d <= 800)
        for i in tr:
            rows.append({"cohort": coh, "opened": pd.Timestamp(date), "cell": int(c.cell[i]), "treated": 1,
                         "stations": ", ".join(stc.name[np.hypot(x[i] - sx, y[i] - sy) <= 800])})
    T = pd.DataFrame(rows)
    return c, T, far


def monthly_dry(cells, start, end):
    years = range(start.year, end.year + 1)
    p = load_panel(years, columns=COLS, filters=[("ts", ">=", start), ("ts", "<=", end)])
    p = p[p.cell.isin(cells) & ~p.drop_main]
    dry = (p.mmh == 0) & (p.mmh_lag1 == 0) & (p.mmh_lag2 == 0)
    q = p[dry]
    return q.groupby(["cell", q.ts.dt.to_period("M")]).vacant.mean().rename("dry_mean").reset_index()


def match(c, T, far, pre_means):
    out = []
    feats = ["pre_log", "dist_city_km", "central_area", "dist_mrt_m"]
    for coh, g in T.groupby("cohort"):
        pm = pre_means[coh]
        cc = c.assign(pre_log=c.cell.map(pm)).dropna(subset=["pre_log"])
        Z = cc[feats].astype(float)
        S = np.linalg.pinv(np.cov(Z.values.T))
        pool = cc[far[cc.index] & ~cc.cell.isin(T.cell)]
        used = set()
        for cell in g.cell:
            if cell not in set(cc.cell):
                continue
            z0 = Z[cc.cell == cell].values[0]
            dz = pool[feats].astype(float).values - z0
            md = np.einsum("ij,jk,ik->i", dz, S, dz)
            order = np.argsort(md)
            k = 0
            for j in order:
                cid = int(pool.cell.iloc[j])
                if cid in used:
                    continue
                used.add(cid)
                out.append({"cohort": coh, "opened": g.opened.iloc[0], "cell": cid, "treated": 0, "matched_to": cell})
                k += 1
                if k == 3:
                    break
    return pd.concat([T, pd.DataFrame(out)], ignore_index=True)


def main():
    style()
    c, T, far = treated_and_controls()
    print(T.groupby("cohort").agg(cells=("cell", "nunique"), stations=("stations", "first")).to_string())
    start = min(pd.Timestamp(d) for d in COHORTS.values()) - pd.DateOffset(months=WIN + 1)
    end = max(pd.Timestamp(d) for d in COHORTS.values()) + pd.DateOffset(months=WIN + 1)
    if end > TEST[0]:
        log_test_scoring("13_mrt_did.py", "post-opening months of NEL extension / DTL infill cohorts fall in the test "
                         "year (association analysis, no forecasting)", "step 13")
    m = monthly_dry(c.cell.values, start, end)
    pre_means = {}
    for coh, date in COHORTS.items():
        o = pd.Period(pd.Timestamp(date), "M")
        q = m[(m.ts >= o - WIN) & (m.ts < o)]
        pre_means[coh] = np.log(q.groupby("cell").dry_mean.mean() + 0.1)
    S = match(c, T, far, pre_means)
    S.to_csv(TABLES / "mrt_did_sample.csv", index=False)
    print(S.groupby(["cohort", "treated"]).cell.nunique().unstack().to_string())
    # (a) event study on dry supply
    rows = []
    for coh, g in S.groupby("cohort"):
        o = pd.Period(g.opened.iloc[0], "M")
        q = m[m.cell.isin(g.cell)].copy()
        q["rel"] = (q.ts - o).apply(lambda x: x.n)
        q = q[(q.rel >= -WIN) & (q.rel <= WIN)]
        q = q.merge(g[["cell", "treated"]].drop_duplicates("cell"), on="cell")
        q["cohort"] = coh
        rows.append(q)
    D = pd.concat(rows, ignore_index=True)
    D["y"] = np.log(D.dry_mean + 0.1)
    import pyfixest as pf
    D["cc"] = D.cohort + "_" + D.cell.astype(str)
    D["mc"] = D.cohort + "_" + D.ts.astype(str)
    D["cell_id"] = D.cell
    rels = [r for r in range(-WIN, WIN + 1) if r != -1]
    for r in rels:
        D[f"e{r + WIN}"] = ((D.rel == r) & (D.treated == 1)).astype(float)
    es = pf.feols("y ~ " + " + ".join(f"e{r + WIN}" for r in rels) + " | cc + mc", data=D, vcov={"CRV1": "cell_id"})
    co, se_ = es.coef(), es.se()
    ev = pd.DataFrame({"rel_month": rels, "coef": [co[f"e{r + WIN}"] for r in rels],
                       "se": [se_[f"e{r + WIN}"] for r in rels]})
    ev["pct"] = 100 * (np.exp(ev.coef) - 1)
    ev["lo"] = 100 * (np.exp(ev.coef - 1.96 * ev.se) - 1)
    ev["hi"] = 100 * (np.exp(ev.coef + 1.96 * ev.se) - 1)
    pre = [f"e{r + WIN}" for r in rels if r < -1]
    b = co[pre].values
    V = es._vcov[np.ix_([list(co.index).index(p) for p in pre], [list(co.index).index(p) for p in pre])]
    from scipy.stats import chi2
    wstat = float(b @ np.linalg.pinv(V) @ b)

    class _W:
        pvalue = float(chi2.sf(wstat, len(pre)))
    wt = _W()
    D["post_t"] = ((D.rel >= 0) & (D.treated == 1)).astype(float)
    dd = pf.feols("y ~ post_t | cc + mc", data=D, vcov={"CRV1": "cell_id"})

    class _Did:
        params = dd.coef()
        bse = dd.se()
    did = _Did()
    ev.to_csv(TABLES / "mrt_did_event_study_supply.csv", index=False, float_format="%.5f")
    summ = {"treated_cells": int(S[S.treated == 1].cell.nunique()), "control_cells": int(S[S.treated == 0].cell.nunique()),
            "pretrend_wald_p": float(wt.pvalue), "did_supply_pct": float(100 * (np.exp(did.params.post_t) - 1)),
            "did_supply_lo": float(100 * (np.exp(did.params.post_t - 1.96 * did.bse.post_t) - 1)),
            "did_supply_hi": float(100 * (np.exp(did.params.post_t + 1.96 * did.bse.post_t) - 1))}
    print(summ, flush=True)
    # (b) heavy-rain effect DiD on the cell-snapshot panel
    parts = []
    for coh, g in S.groupby("cohort"):
        o = g.opened.iloc[0]
        a, b = o - pd.DateOffset(months=WIN), o + pd.DateOffset(months=WIN)
        p = load_panel(range(a.year, b.year + 1), columns=COLS, filters=[("ts", ">=", a), ("ts", "<=", b)])
        p = p[p.cell.isin(g.cell) & ~p.drop_main & (p.rain_band >= 0) & p.mmh_lag1.notna()]
        p = p.merge(g[["cell", "treated"]].drop_duplicates("cell"), on="cell")
        p["post"] = (p.ts >= o).astype(int)
        p["cohort_id"] = list(COHORTS).index(coh)
        parts.append(p)
    P = pd.concat(parts, ignore_index=True)
    hv = (P.rain_band.values == 3).astype("float32")
    names = ["light", "moderate", "heavy", "heavy_x_post", "heavy_x_treated", "heavy_x_treated_x_post", "mmh_lag1",
             "mmh_lag2"]
    P["heavy"] = hv
    P["light"] = (P.rain_band.values == 1).astype(float)
    P["moderate"] = (P.rain_band.values == 2).astype(float)
    P["heavy_x_post"] = hv * P.post.values
    P["heavy_x_treated"] = hv * P.treated.values
    P["heavy_x_treated_x_post"] = hv * P.treated.values * P.post.values
    P["fe_cell"] = P.cohort_id.astype(str) + "_" + P.cell.astype(str)
    P["fe_hm"] = P.cohort_id.astype(str) + "_" + (P.how.astype(int) * 100 + P.month.astype(int)).astype(str)
    P["fe_ymr"] = P.cohort_id.astype(str) + "_" + (P.ym.astype(int) * 100 + P.regime_id.astype(int)).astype(str)
    P["day"] = P.ts.dt.normalize().astype(str)
    import pyfixest as pf
    m = pf.fepois("vacant ~ " + " + ".join(names) + " | fe_cell + fe_hm + fe_ymr", data=P, vcov={"CRV1": "day"})
    r = pd.DataFrame({"coef": m.coef(), "se": m.se()})
    r = pct(r)
    r.attrs = {}
    r.to_csv(TABLES / "mrt_did_heavy_rain.csv", float_format="%.5f")
    print(r[["pct", "pct_lo", "pct_hi"]].round(2).to_string())
    summ.update({"heavy_did_pct": float(r.loc["heavy_x_treated_x_post", "pct"]),
                 "heavy_did_lo": float(r.loc["heavy_x_treated_x_post", "pct_lo"]),
                 "heavy_did_hi": float(r.loc["heavy_x_treated_x_post", "pct_hi"]),
                 "heavy_rows_treated_post": int(((P.rain_band == 3) & (P.treated == 1) & (P.post == 1)).sum())})
    pd.Series(summ).to_csv(TABLES / "mrt_did_summary.csv")
    print(summ)
    chart()


def chart():
    """Event-study chart from the saved tables (reference month -1 drawn at 0)."""
    ev = pd.read_csv(TABLES / "mrt_did_event_study_supply.csv")
    ev = pd.concat([ev, pd.DataFrame([{"rel_month": -1, "pct": 0.0, "lo": 0.0, "hi": 0.0}])]).sort_values("rel_month")
    summ = pd.read_csv(TABLES / "mrt_did_summary.csv", index_col=0).iloc[:, 0]
    style()
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.fill_between(ev.rel_month, ev.lo, ev.hi, color=BLUE, alpha=0.2, lw=0)
    ax.plot(ev.rel_month, ev.pct, "o-", color=BLUE_DARK, ms=4)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.axvline(-0.5, color=ORANGE, lw=1, ls="--")
    ax.set_xlabel("Months from station opening (reference: month -1)")
    ax.set_ylabel("% dry-weather vacant taxis,\nnear new station vs matched cells")
    clear = summ["did_supply_lo"] > 0 or summ["did_supply_hi"] < 0
    verdict = (f"dry-weather supply nearby changed {summ['did_supply_pct']:+.1f}% after opening" if clear else
               "no clear change in nearby dry-weather taxi supply")
    ax.set_title(f"New MRT stations: {verdict}\n(DiD CI {summ['did_supply_lo']:+.1f} to {summ['did_supply_hi']:+.1f}%; "
                 f"pre-trends differ, p = {summ['pretrend_wald_p']:.3f}, so read with caution)", fontsize=10)
    fig.tight_layout()
    save(fig, "mrt_did_event_study", "Sources: data.gov.sg taxi availability (LTA), LTA station openings. TEL3, TEL4, "
         "Punggol Coast, Hume; cells within 800 m vs 3 matched cells > 2 km away; 95% CI clustered by cell.")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    chart() if sys.argv[1:] == ["chart"] else main()
