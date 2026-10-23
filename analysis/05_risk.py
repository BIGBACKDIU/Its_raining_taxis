"""Step 5: risk of unusually low availability (HANDOFF section 6, step 5).

  1. Logit models for low (deficit >= 0.5; 0.4 and 0.6 as checks) and zero vacant taxis, only where the
     baseline is >= 4: low ~ light + moderate + heavy + lags | cell + how^month + ym^regime, errors clustered by
     day (analysis/fepois_hd.felogit, checked against pyfixest in tests/). Odds ratios with 95% CI.
  2. Vulnerability map: per cell, the chance of low availability in heavy rain minus the chance when dry
     (percentage points), with 95% day-bootstrap CI.
  3. Severity multinomial (appendix): normal / mild / low / severe on a 1-million-row random sample, with
     controls instead of fixed effects; relative risk ratios, errors clustered by day.
  4. Rain-response types (optional in HANDOFF): k-means on each cell's availability ratios in light, moderate,
     heavy rain and just after rain; k chosen by silhouette; stability by day-bootstrap (adjusted Rand index).

Sample: fit period, main sample. Outputs: outputs/tables/risk_*.csv, figures risk_odds, risk_vulnerability,
risk_types.
Usage: .venv/bin/python -m analysis.05_risk
"""
from __future__ import annotations

import gc
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

from analysis.common import (AQUA, BLUE, BLUE_DARK, FIT, INTERIM, MUTED, NOT_ANALYSED, ORANGE, RAIN_BANDS, SEED,
                             TABLES, VIOLET, load_panel, save, style)
from analysis.fepois_hd import felogit, odds

COLS = ["ts", "cell", "vacant", "baseline", "low", "low40", "low60", "zero", "severity", "rain_band", "mmh",
        "mmh_lag1", "mmh_lag2", "how", "month", "ym", "regime_id", "daytype", "drop_main"]
NAMES = ["light", "moderate", "heavy", "mmh_lag1", "mmh_lag2"]
B_BOOT = 1000
NO_CLEAR, NOT_TESTED = "#c9d6e6", "#ecebe6"


def load():
    p = load_panel(range(2022, 2026), columns=COLS, filters=[("ts", ">=", FIT[0]), ("ts", "<=", FIT[1])])
    p = p[~p.drop_main & (p.rain_band >= 0) & p.mmh_lag1.notna() & p.mmh_lag2.notna() & p.baseline.notna()]
    return p.reset_index(drop=True)


def logits(p):
    q = p[p.baseline >= 4].reset_index(drop=True)
    X = np.column_stack([q.rain_band == 1, q.rain_band == 2, q.rain_band == 3, q.mmh_lag1, q.mmh_lag2]).astype("float32")
    fe = [q.cell.values, q.how.values.astype(np.int32) * 100 + q.month.values,
          q.ym.values.astype(np.int64) * 100 + q.regime_id.values]
    day = q.ts.values.astype("datetime64[D]")
    rows = []
    for outcome in ("low", "zero", "low40", "low60"):
        y = q[outcome].astype(float).values
        r = odds(felogit(y, X, NAMES, fe, day, xt_dtype="float32"))
        r.insert(0, "outcome", outcome)
        r["n"] = r.attrs["n"]
        r["n_dropped_no_variation"] = r.attrs["n_dropped"]
        for b, name in enumerate(RAIN_BANDS):
            r.loc[r.index.isin([name]), "raw_rate"] = q.loc[q.rain_band == b, outcome].mean()
        r["raw_rate_dry"] = q.loc[q.rain_band == 0, outcome].mean()
        print(outcome, r[["or", "or_lo", "or_hi", "raw_rate"]].round(4).to_string(), flush=True)
        rows.append(r.reset_index(names="term"))
        gc.collect()
    t = pd.concat(rows)
    t.to_csv(TABLES / "risk_logit.csv", index=False, float_format="%.6f")
    return t, q


def vulnerability(q, rng):
    q = q[q.rain_band.isin([0, 3])]
    days = np.sort(q.ts.dt.normalize().unique())
    di = np.searchsorted(days, q.ts.dt.normalize().values)
    cc, cl = pd.factorize(q.cell)
    D, C = len(days), len(cl)
    out = {}
    for b in (0, 3):
        m = (q.rain_band == b).values
        L = np.zeros((D, C))
        N = np.zeros((D, C))
        np.add.at(L, (di[m], cc[m]), q.low.values[m].astype(float))
        np.add.at(N, (di[m], cc[m]), 1)
        out[b] = (L, N)
    W = rng.multinomial(D, np.full(D, 1 / D), size=B_BOOT).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        rd = out[3][0].sum(0) / out[3][1].sum(0) - out[0][0].sum(0) / out[0][1].sum(0)
        rdb = (W @ out[3][0]) / (W @ out[3][1]) - (W @ out[0][0]) / (W @ out[0][1])
    v = pd.DataFrame({"cell": cl, "heavy_rows": out[3][1].sum(0).astype(int),
                      "p_low_dry": out[0][0].sum(0) / out[0][1].sum(0),
                      "p_low_heavy": out[3][0].sum(0) / out[3][1].sum(0), "rd_pp": 100 * rd,
                      "rd_lo": 100 * np.nanquantile(rdb, 0.025, axis=0), "rd_hi": 100 * np.nanquantile(rdb, 0.975, axis=0)})
    v.loc[v.heavy_rows < 50, ["rd_pp", "rd_lo", "rd_hi"]] = np.nan
    v["clear_increase"] = v.rd_lo > 0
    v.to_csv(TABLES / "risk_vulnerability.csv", index=False, float_format="%.5f")
    return v


def severity_mnlogit(p, rng, n=1_000_000):
    import statsmodels.api as sm
    q = p[p.baseline >= 4].sample(n=min(n, (p.baseline >= 4).sum()), random_state=SEED)
    cc = pd.read_parquet(INTERIM / "cells.parquet").set_index("cell").city_centre
    lv = pd.read_csv(TABLES / "baseline_regime_levels_30.csv").set_index("regime_id").log_level
    h = q.how.values % 48 // 2
    X = pd.DataFrame({"light": q.rain_band == 1, "moderate": q.rain_band == 2, "heavy": q.rain_band == 3,
                      "mmh_lag1": q.mmh_lag1, "mmh_lag2": q.mmh_lag2, "city_centre": q.cell.map(cc),
                      "am_peak": (h >= 7) & (h < 10), "pm_peak": (h >= 17) & (h < 20), "night": h < 7,
                      "weekend_or_holiday": q.daytype > 0, "regime_log_level": q.regime_id.map(lv),
                      "log_baseline": np.log(q.baseline)}).astype(float)
    X = sm.add_constant(X)
    m = sm.MNLogit(q.severity.astype(int).values, X).fit(disp=0, maxiter=200, cov_type="cluster",
                                                          cov_kwds={"groups": pd.factorize(q.ts.dt.normalize())[0]})
    rows = []
    for k, col in enumerate(m.params.columns):
        for term in ("light", "moderate", "heavy"):
            b, se = m.params.loc[term, col], m.bse.loc[term, col]
            rows.append({"category_vs_normal": ["mild", "low", "severe"][k], "term": term, "rrr": np.exp(b),
                         "rrr_lo": np.exp(b - 1.96 * se), "rrr_hi": np.exp(b + 1.96 * se), "n": len(q)})
    t = pd.DataFrame(rows)
    t.to_csv(TABLES / "risk_severity_mnlogit.csv", index=False, float_format="%.5f")
    print(t.round(3).to_string())
    return t


def response_types(p, rng, n_boot=200):
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    days = np.sort(p.ts.dt.normalize().unique())
    di = np.searchsorted(days, p.ts.dt.normalize().values)
    cc, cl = pd.factorize(p.cell)
    D, C = len(days), len(cl)
    after = (p.mmh.values == 0) & (p.mmh_lag1.values > 2.5)
    groups = {"dry": (p.rain_band.values == 0) & ~after & (p.mmh_lag1.values == 0), "light": p.rain_band.values == 1,
              "moderate": p.rain_band.values == 2, "heavy": p.rain_band.values == 3, "just_after": after}
    S = {}
    for g, m in groups.items():
        V = np.zeros((D, C))
        Bm = np.zeros((D, C))
        np.add.at(V, (di[m], cc[m]), p.vacant.values[m])
        np.add.at(Bm, (di[m], cc[m]), p.baseline.values[m])
        S[g] = (V, Bm)

    def features(w):
        r = {g: (w @ S[g][0]) / (w @ S[g][1]) for g in S}
        return np.column_stack([np.log(r[g] / r["dry"]) for g in ("light", "moderate", "heavy", "just_after")])

    F = features(np.ones(D))
    ok = np.isfinite(F).all(1)
    mu, sd = F[ok].mean(0), F[ok].std(0)
    Z = (F[ok] - mu) / sd
    sil = {k: silhouette_score(Z, KMeans(k, n_init=20, random_state=SEED).fit_predict(Z)) for k in range(2, 6)}
    k = max(sil, key=sil.get)
    km = KMeans(k, n_init=50, random_state=SEED).fit(Z)
    base = km.labels_
    aris = []
    for b in range(n_boot):
        w = rng.multinomial(D, np.full(D, 1 / D)).astype(float)
        Fb = features(w)[ok]
        Zb = (Fb - mu) / sd
        if not np.isfinite(Zb).all():
            Zb = np.nan_to_num(Zb)
        lb = KMeans(k, n_init=10, random_state=b).fit_predict(Zb)
        aris.append(adjusted_rand_score(base, lb))
    # order types by heavy-rain response (most affected first)
    centres = pd.DataFrame(km.cluster_centers_ * sd + mu, columns=["light", "moderate", "heavy", "just_after"])
    order = centres.heavy.argsort().values
    relabel = {old: new for new, old in enumerate(order)}
    t = pd.DataFrame({"cell": cl[ok], "type": [relabel[l] for l in base]})
    for j, c in enumerate(["light", "moderate", "heavy", "just_after"]):
        t[f"pct_{c}"] = 100 * (np.exp(F[ok][:, j]) - 1)
    t.to_csv(TABLES / "risk_types.csv", index=False, float_format="%.4f")
    summ = {"k": int(k), "silhouette": {int(a): round(float(b), 4) for a, b in sil.items()},
            "ari_mean": float(np.mean(aris)), "ari_p05": float(np.quantile(aris, 0.05)),
            "ari_p95": float(np.quantile(aris, 0.95)), "bootstrap_draws": n_boot,
            "type_means_pct": t.groupby("type")[[c for c in t.columns if c.startswith("pct_")]].mean().round(2).to_dict(),
            "type_sizes": t.type.value_counts().sort_index().to_dict()}
    print(summ)
    return t, summ


def charts(lg, v, types):
    d02 = __import__("importlib").import_module("analysis.02_describe")
    allc = pd.read_parquet(INTERIM / "cells.parquet")
    # odds ratios
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for k, (o, lab, col) in enumerate((("low", "Low availability (deficit >= 50%)", BLUE_DARK),
                                       ("zero", "No vacant taxi", ORANGE))):
        t = lg[lg.outcome == o].set_index("term").loc[["light", "moderate", "heavy"]]
        x = np.arange(3) + (k - 0.5) * 0.25
        ax.errorbar(x, t["or"], yerr=[t["or"] - t.or_lo, t.or_hi - t["or"]], fmt="o", ms=7, capsize=3, color=col, label=lab)
        for xi, v_ in zip(x, t["or"]):
            ax.text(xi + 0.05, v_, f"{v_:.2f}", fontsize=7.5, color=MUTED, va="center")
    ax.axhline(1, color=MUTED, lw=0.8)
    ax.set_xticks(range(3), ["Light", "Moderate", "Heavy"])
    ax.set_ylabel("Odds ratio vs dry")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("Rain is associated with higher odds of unusually low availability in a cell", fontsize=10.5)
    fig.tight_layout()
    save(fig, "risk_odds", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025, cells with "
         "expected >= 4 vacant taxis. Logit with cell, how^month, ym^regime FE; 95% CI by day.")
    plt.close(fig)
    # vulnerability map
    fig, ax = plt.subplots(figsize=(8, 4.8))
    d02.draw_base(ax)
    cmap = LinearSegmentedColormap.from_list("o", ["#fbe3d6", ORANGE, "#8a2f10"])
    norm = BoundaryNorm([0, 2.5, 5, 10, 15, 20, 30], cmap.N, extend="max")
    vals = np.where(v.clear_increase, v.rd_pp, np.nan)
    d02.cell_squares(ax, v.cell.values, vals, cmap, norm, allc)
    from pipeline.grid import to_lonlat
    elig = allc[allc.eligible].cell
    tested = set(v[v.rd_pp.notna()].cell)
    for c in elig:
        if c in tested and bool(v.set_index("cell").clear_increase.get(c, False)):
            continue
        x, y = c // 1000, c % 1000
        lon0, lat0 = to_lonlat(x * 1000, y * 1000)
        lon1, lat1 = to_lonlat((x + 1) * 1000, (y + 1) * 1000)
        ax.add_patch(plt.Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0,
                                   facecolor=NO_CLEAR if c in tested else NOT_TESTED, edgecolor="white", lw=0.3, zorder=3))
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, orientation="horizontal", fraction=0.05, pad=0.02,
                 label="Extra chance of low availability in heavy rain (percentage points)")
    ax.legend(handles=[Patch(color=NO_CLEAR, label="Tested, no clear increase"),
                       Patch(color=NOT_TESTED, label="Expected < 4 taxis or < 50 heavy-rain rows"),
                       Patch(color=NOT_ANALYSED, label="Not analysed (mean < 0.5)")], loc="upper left", fontsize=8)
    ax.set_title(f"Where heavy rain most raises the chance of unusually low availability "
                 f"({int(v.clear_increase.sum())} cells with a clear increase)", fontsize=10)
    fig.tight_layout()
    save(fig, "risk_vulnerability", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025; "
         "cells with expected >= 4 vacant taxis; 95% day-bootstrap CI excludes 0.")
    plt.close(fig)
    # types
    fig, ax = plt.subplots(figsize=(8, 4.8))
    d02.draw_base(ax)
    t, summ = types
    k = summ["k"]
    cols = [ORANGE, BLUE, AQUA, VIOLET, BLUE_DARK][:k]
    d02.cell_squares(ax, t.cell.values, t.type.values.astype(float), ListedColormap(cols),
                     BoundaryNorm(np.arange(k + 1) - 0.5, k), allc)
    means = pd.DataFrame(summ["type_means_pct"])
    ax.legend(handles=[Patch(color=cols[i], label=f"Type {i + 1}: heavy {means.loc[i, 'pct_heavy']:+.0f}%, "
                             f"just after {means.loc[i, 'pct_just_after']:+.0f}% (n={summ['type_sizes'][i]})")
                       for i in range(k)] + [Patch(color=NOT_ANALYSED, label="Not analysed")], loc="upper left", fontsize=7.5)
    ax.set_title(f"Rain-response types (k-means, k={k}); bootstrap stability ARI {summ['ari_mean']:.2f}", fontsize=10)
    fig.tight_layout()
    save(fig, "risk_types", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025. Features: "
         "vacant/expected in light, moderate, heavy rain and just after rain, relative to dry.")
    plt.close(fig)


def charts_from_tables():
    lg = pd.read_csv(TABLES / "risk_logit.csv")
    v = pd.read_csv(TABLES / "risk_vulnerability.csv")
    t = pd.read_csv(TABLES / "risk_types.csv")
    summ = json.loads((TABLES / "risk_summary.json").read_text())["types"]
    summ["type_means_pct"] = {k: {int(i): x for i, x in d.items()} for k, d in summ["type_means_pct"].items()}
    summ["type_sizes"] = {int(k): x for k, x in summ["type_sizes"].items()}
    charts(lg, v, (t, summ))


def main():
    import sys
    if "--charts" in sys.argv:
        style()
        return charts_from_tables()
    style()
    rng = np.random.default_rng(SEED)
    p = load()
    lg, q = logits(p)
    v = vulnerability(q, rng)
    del q
    gc.collect()
    sev = severity_mnlogit(p, rng)
    types = response_types(p, rng)
    summary = {"vulnerability_cells_clear_increase": int(v.clear_increase.sum()),
               "vulnerability_cells_tested": int(v.rd_pp.notna().sum()),
               "vulnerability_median_rd_pp": float(v.rd_pp.median()), "types": types[1]}
    (TABLES / "risk_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    charts(lg, v, types)


if __name__ == "__main__":
    main()
