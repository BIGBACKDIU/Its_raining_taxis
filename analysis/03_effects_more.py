"""Step 3, second part: approaching rain, regime heterogeneity, interactions, forecast value, robustness.

Same sample and estimator as analysis/03_effects.py (fit period, main sample, Poisson with fixed effects,
day-clustered errors). Parts (run one at a time to stay within memory):

  --part approach   2-5 km ring rain while the cell itself has been dry for 90 minutes ("rain approaching")
  --part hetero     share model with heavy x regime terms, before and after adding heavy x season and
                    heavy x time-band terms; Wald tests of the heavy x regime terms
  --part interact   heavy x rush hour, x city centre, x weekend, x fiscal year (abs and share)
  --part forecast   issued forecast of rain while the cell has been dry for 90 minutes (abs and share),
                    without and with neighbouring-rain controls
  --part robust     3-gauge rain, robustness sample, with COVID months, by fiscal year, 500 m grid (FY2024),
                    15-minute panel (Oct 2024 - Mar 2025), negative binomial on an aggregated table,
                    event-study onset thresholds 0.5 and 2 mm/h
  --part charts     charts from the saved tables

Outputs: outputs/tables/effects_{approach,hetero,interact,forecast,robust}.csv and figures.
Usage: .venv/bin/python -m analysis.03_effects_more --part approach
"""
from __future__ import annotations

import argparse
import gc
import importlib
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2

from analysis.common import (BAND_COLORS, BLUE, BLUE_DARK, FIT, INTERIM, MUTED, ORANGE, TABLES, load_panel, save,
                             style)
from analysis.common import log_test_scoring
from analysis.fepois_hd import fepois, pct

E = importlib.import_module("analysis.03_effects")
BANDS, REGS = E.BANDS, E.REGS
BASE = ["ts", "cell", "vacant", "citywide", "rain_band", "mmh", "mmh_lag1", "mmh_lag2", "how", "month", "ym",
        "regime_id", "regime", "drop_main", "baseline"]


def season(month):
    m = np.asarray(month)
    return np.select([np.isin(m, [12, 1, 2, 3]), np.isin(m, [6, 7, 8, 9])], ["NE monsoon", "SW monsoon"],
                     "Inter-monsoon")


def time_band(hod):
    h = np.asarray(hod) // 2
    return np.select([h < 7, h < 10, h < 17, h < 20], ["Night 00-07", "AM peak 07-10", "Day 10-17", "PM peak 17-20"],
                     "Evening 20-24")


def load(extra=(), years=range(2022, 2026), start=FIT[0], end=FIT[1], drop="drop_main", grid=30, suffix=""):
    cols = list(dict.fromkeys(BASE + list(extra) + ([drop] if drop not in BASE else [])))
    parts = []
    for y in years:
        f = INTERIM / f"panel{grid}{suffix}_{y}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f, columns=cols, filters=[("ts", ">=", start), ("ts", "<=", end)]))
    p = pd.concat(parts, ignore_index=True)
    # association fits do not use the baseline (spell rows have none), so it is not required here
    s = (~p[drop] & (p.rain_band >= 0) & p.mmh_lag1.notna() & p.mmh_lag2.notna()).values
    return p[s].reset_index(drop=True)


def fes(p):
    fe_abs = [p.cell.values, p.how.values.astype(np.int32) * 100 + p.month.values,
              p.ym.values.astype(np.int64) * 100 + p.regime_id.values]
    return fe_abs, [p.cell.values, p.ts.values], p.ts.values.astype("datetime64[D]")


def base_X(p, band_col="rain_band"):
    b = p[band_col].values
    return [b == 1, b == 2, b == 3, p.mmh_lag1.values, p.mmh_lag2.values]


def fit(name, p, cols, names, which=("abs", "share"), xt="float32"):
    X = np.column_stack(cols).astype("float32")
    fe_abs, fe_share, day = fes(p)
    out = []
    for w in which:
        t0 = time.time()
        r = fepois(p.vacant.values, X, names, fe_abs if w == "abs" else fe_share, day, xt_dtype=xt)
        V = r.attrs["vcov"]
        r = pct(r)
        r.insert(0, "model", w)
        r.insert(0, "variant", name)
        r["n"] = r.attrs["n"]
        r.attrs["vcov"] = V
        print(f"{name}/{w}: n={r.attrs['n']:,} {time.time() - t0:.0f}s", flush=True)
        print(r.loc[[c for c in names if not c.startswith("mmh_lag")], ["pct", "pct_lo", "pct_hi"]].round(2).to_string(),
              flush=True)
        out.append(r)
    del X
    gc.collect()
    return out


def combo(r, terms, label):
    """Sum of coefficients (e.g. heavy + heavy x group) with delta-method SE, as % change."""
    V = r.attrs["vcov"]
    b = r.coef[terms].sum()
    se = np.sqrt(V.loc[terms, terms].values.sum())
    return {"group": label, "coef": b, "se": se, "pct": 100 * (np.exp(b) - 1),
            "pct_lo": 100 * (np.exp(b - 1.96 * se) - 1), "pct_hi": 100 * (np.exp(b + 1.96 * se) - 1)}


# ----------------------------------------------------------------------------- parts
def part_approach():
    p = load(extra=["rain_ring", "rain_2km", "wet5_min"])
    own_dry = (p.mmh.values == 0) & (p.mmh_lag1.values == 0) & (p.mmh_lag2.values == 0)
    ring = p.rain_ring.fillna(0).values
    near = p.rain_2km.fillna(0).values
    cols = base_X(p) + [own_dry & (ring > 0) & (ring <= 2.5), own_dry & (ring > 2.5),
                        own_dry & (near > 0) & (near <= 2.5), own_dry & (near > 2.5)]
    names = REGS + ["ring_light_owndry", "ring_heavier_owndry", "near_light_owndry", "near_heavier_owndry"]
    print("rows with ring rain while own cell dry 90 min:", int((own_dry & (ring > 0)).sum()))
    res = fit("approach", p, cols, names)
    for r in res:
        r.attrs = {}
    t = pd.concat(res)
    t.index.name = "term"
    t.to_csv(TABLES / "effects_approach.csv", float_format="%.6f")


def wald(r, terms):
    b = r.coef[terms].values
    V = r.attrs["vcov"].loc[terms, terms].values
    w = float(b @ np.linalg.solve(V, b))
    return w, len(terms), chi2.sf(w, len(terms))


def part_hetero():
    p = load()
    p["regime"] = p.regime.astype(str)
    regs = sorted(r for r in p.regime.unique() if r != "spell" and (p.regime == r).sum() >= 200_000)
    ref = "R09"
    heavy = p.rain_band.values == 3
    reg_cols = [heavy & (p.regime.values == r) for r in regs if r != ref]
    reg_names = [f"heavy_x_{r}" for r in regs if r != ref]
    se_ = season(p.month.values)
    tb = time_band(p.how.values % 48)
    s_levels = ["NE monsoon", "SW monsoon"]                              # ref: inter-monsoon
    t_levels = ["Night 00-07", "AM peak 07-10", "PM peak 17-20", "Evening 20-24"]   # ref: day 10-17
    s_cols = [heavy & (se_ == s) for s in s_levels]
    t_cols = [heavy & (tb == t) for t in t_levels]
    s_names = [f"heavy_x_{s}" for s in s_levels]
    t_names = [f"heavy_x_{t}" for t in t_levels]
    share_heavy = pd.crosstab(p.regime[heavy], se_[heavy], normalize="index").round(3)
    share_heavy.to_csv(TABLES / "effects_hetero_season_mix.csv")
    print(share_heavy.to_string())
    rows, tests = [], []
    for name, cols, names in (("regime only", base_X(p) + reg_cols, REGS + reg_names),
                              ("regime + season + time band", base_X(p) + reg_cols + s_cols + t_cols,
                               REGS + reg_names + s_names + t_names),
                              ("season + time band only", base_X(p) + s_cols + t_cols, REGS + s_names + t_names)):
        r = fit(name, p, cols, names, which=("share",))[0]
        if reg_names[0] in r.index:
            w, df, pv = wald(r, reg_names)
            tests.append({"model": name, "test": "heavy x regime = 0", "wald": w, "df": df, "p": pv})
        if s_names[0] in r.index:
            for lab, nm in (("heavy x season = 0", s_names), ("heavy x time band = 0", t_names)):
                w, df, pv = wald(r, nm)
                tests.append({"model": name, "test": lab, "wald": w, "df": df, "p": pv})
        r = r.reset_index(names="term")
        r.attrs = {}
        rows.append(r)
    t = pd.concat(rows)
    t.to_csv(TABLES / "effects_hetero.csv", index=False, float_format="%.6f")
    tests = pd.DataFrame(tests)
    tests.to_csv(TABLES / "effects_hetero_tests.csv", index=False, float_format="%.6f")
    print(tests.to_string())


def part_interact():
    p = load(extra=["daytype", "hod"])
    cc = pd.read_parquet(INTERIM / "cells.parquet").set_index("cell").city_centre
    heavy = p.rain_band.values == 3
    h = p.hod.values // 2
    rush = (p.daytype.values == 0) & (((h >= 7) & (h < 10)) | ((h >= 17) & (h < 20)))
    centre = p.cell.map(cc).values.astype(bool)
    weekend = p.daytype.values > 0
    fy = np.where(p.ts.values < np.datetime64("2023-04-01"), 0, np.where(p.ts.values < np.datetime64("2024-04-01"), 1, 2))
    specs = [("rush hour (weekday 07-10, 17-20)", [rush], ["heavy_x_rush"], {"other times": [], "rush hour": ["heavy_x_rush"]}),
             ("city centre", [centre], ["heavy_x_centre"], {"outside centre": [], "city centre": ["heavy_x_centre"]}),
             ("weekend or holiday", [weekend], ["heavy_x_weekend"], {"weekday": [], "weekend or holiday": ["heavy_x_weekend"]}),
             ("fiscal year", [fy == 1, fy == 2], ["heavy_x_FY2023", "heavy_x_FY2024"],
              {"FY2022 (Apr 22-Mar 23)": [], "FY2023": ["heavy_x_FY2023"], "FY2024": ["heavy_x_FY2024"]})]
    rows = []
    for name, groups, names, combos in specs:
        res = fit(f"heavy x {name}", p, base_X(p) + [heavy & g for g in groups], REGS + names)
        for r in res:
            for label, terms in combos.items():
                c = combo(r, ["heavy"] + terms, label)
                c.update(interaction=name, model=r.model.iloc[0])
                if terms:
                    c["p_difference"] = float(r.loc[terms[0], "p"]) if len(terms) == 1 else wald(r, terms)[2]
                rows.append(c)
    t = pd.DataFrame(rows)
    t.to_csv(TABLES / "effects_interact.csv", index=False, float_format="%.6f")
    print(t[["interaction", "model", "group", "pct", "pct_lo", "pct_hi", "p_difference"]].round(3).to_string())


def part_forecast():
    p = load(extra=["fc_code", "fc_age_min", "rain_ring", "rain_2km", "gauges_wet_share"])
    own_dry = (p.mmh.values == 0) & (p.mmh_lag1.values == 0) & (p.mmh_lag2.values == 0) & (p.fc_code.values >= 0)
    p = p[own_dry].reset_index(drop=True)
    fc = p.fc_code.values
    names = ["fc_light", "fc_showers", "fc_thundery"]
    cols = [fc == 1, fc == 2, fc == 3]
    print("dry-cell rows with a forecast:", len(p), pd.Series(fc).value_counts().sort_index().to_dict())
    ring = p.rain_ring.fillna(0).values
    near = p.rain_2km.fillna(0).values
    ctrl = [(near > 0) & (near <= 2.5), near > 2.5, (ring > 0) & (ring <= 2.5), ring > 2.5]
    ctrl_n = ["near_light", "near_heavier", "ring_light", "ring_heavier"]
    res = fit("forecast only", p, cols, names) + fit("forecast + neighbouring rain", p, cols + ctrl, names + ctrl_n)
    for r in res:
        r.attrs = {}
    t = pd.concat(res)
    t.index.name = "term"
    t.to_csv(TABLES / "effects_forecast.csv", float_format="%.6f")


def part_robust():
    rows = []

    def keep(res, variant):
        for r in res:
            r = r.loc[r.index.intersection(BANDS)].reset_index(names="term")
            r.attrs = {}
            r["variant"] = variant
            rows.append(r)
        pd.concat(rows).to_csv(TABLES / "effects_robust.csv", index=False, float_format="%.6f")

    from analysis.common import rain_band
    # 1. 3-gauge rain
    p = load(extra=["mmh_3g"])
    p["band3"] = rain_band(p.mmh_3g.values)
    p = p[p.band3 >= 0].reset_index(drop=True)
    keep(fit("3-gauge rain", p, base_X(p, "band3"), REGS), "3-gauge mean rain")
    # 2. by fiscal year
    for a, b, lab in (("2022-04-01", "2023-03-31 23:59", "FY2022 only"), ("2023-04-01", "2024-03-31 23:59", "FY2023 only"),
                      ("2024-04-01", "2025-03-31 23:59", "FY2024 only")):
        q = p[(p.ts >= a) & (p.ts <= b)].reset_index(drop=True)
        keep(fit(lab, q, base_X(q), REGS), lab)
        del q
    del p
    gc.collect()
    # 3. robustness sample (feed-outage days and the ambiguous Feb-Mar 2023 spell back in)
    p = load(drop="drop_robust")
    keep(fit("robust sample", p, base_X(p), REGS), "robustness sample (outage days back in)")
    del p
    gc.collect()
    # 4. with COVID months (Oct 2021 - Mar 2025)
    p = load(years=range(2021, 2026), start=pd.Timestamp("2021-10-01"))
    keep(fit("with COVID", p, base_X(p), REGS), "with COVID months (from Oct 2021)")
    del p
    gc.collect()
    # 5. 15-minute panel, Oct 2024 - Mar 2025
    p = load(years=[2024, 2025], start=pd.Timestamp("2024-10-01"), grid=15)
    keep(fit("15-minute panel", p, base_X(p), REGS), "15-minute snapshots (Oct 24-Mar 25)")
    q = load(years=[2024, 2025], start=pd.Timestamp("2024-10-01"))
    keep(fit("30-minute same months", q, base_X(q), REGS), "30-minute snapshots (Oct 24-Mar 25)")
    del p, q
    gc.collect()
    # 6. 500 m grid, FY2024
    if (INTERIM / "panel30_500m_2024.parquet").exists():
        p = load(years=[2024, 2025], start=pd.Timestamp("2024-04-01"), suffix="_500m")
        keep(fit("500 m grid", p, base_X(p), REGS), "500 m cells (FY2024)")
        del p
        q = load(years=[2024, 2025], start=pd.Timestamp("2024-04-01"))
        keep(fit("1 km same period", q, base_X(q), REGS), "1 km cells (FY2024)")
        del q
        gc.collect()
    # 7. event-study onset thresholds
    p = E.load_fit()
    for thr in (0.5, 2.0):
        ev, info = E.onsets(p, thr=thr)
        s = E.sample(p)
        q, evq = p[s].reset_index(drop=True), ev[s]
        evt = np.where(np.isnan(evq), -999, evq).astype(int)
        _, fe_abs, fe_share, day = E.design(q)
        for m, f in (("abs", fe_abs), ("share", fe_share)):
            es = E.event_study(f"event_{m}_thr{thr}", q.vacant.values, evt, f, day)
            es["threshold"] = thr
            es.to_csv(TABLES / f"effects_event_study_thr{thr}_{m}.csv", index=False, float_format="%.6f")
        del q, evq, evt
        gc.collect()
    del p
    gc.collect()
    # 8. negative binomial on an aggregated table
    nb = negbin_aggregated()
    nb.to_csv(TABLES / "effects_robust_negbin.csv", float_format="%.6f")


def negbin_aggregated():
    """NB2 GLM on counts aggregated to planning area x 3-hour block of week x ym^regime x rain band,
    exposure = number of cell-snapshots; fixed effects as dummies; HC1 errors. Checks the Poisson
    variance assumption on a table small enough for statsmodels."""
    import statsmodels.api as sm
    p = load(extra=["hod", "dow"])
    pa = pd.read_parquet(INTERIM / "cells.parquet").set_index("cell").planning_area
    p["pa"] = p.cell.map(pa)
    p["blk"] = p.dow.astype(int) * 8 + (p.hod.astype(int) // 6)
    p["ymr"] = p.ym.astype(int) * 100 + p.regime_id.astype(int)
    a = p.groupby(["pa", "blk", "ymr", "rain_band"], observed=True).vacant.agg(y="sum", n="size").reset_index()
    del p
    X = pd.get_dummies(a[["pa", "blk", "ymr"]].astype(str), drop_first=True, dtype=float)
    for k, b in enumerate(BANDS, start=1):
        X[b] = (a.rain_band == k).astype(float)
    X = sm.add_constant(X)
    res = {}
    for fam, lab in ((sm.families.Poisson(), "poisson_aggregated"), (sm.families.NegativeBinomial(alpha=1.0), "negbin_aggregated")):
        if lab == "negbin_aggregated":
            # NB2 dispersion by the method of moments from the Poisson fit, then the GLM with that alpha
            mu = res["poisson_aggregated"].mu
            alpha = max(1e-6, float(np.mean(((a.y - mu) ** 2 - mu) / mu ** 2)))
            fam = sm.families.NegativeBinomial(alpha=alpha)
        r = sm.GLM(a.y, X, family=fam, exposure=a.n).fit(cov_type="HC1")
        res[lab] = r
    rows = []
    for lab, r in res.items():
        for b in BANDS:
            c, se = r.params[b], r.bse[b]
            rows.append({"model": lab, "term": b, "coef": c, "se": se, "pct": 100 * (np.exp(c) - 1),
                         "pct_lo": 100 * (np.exp(c - 1.96 * se) - 1), "pct_hi": 100 * (np.exp(c + 1.96 * se) - 1),
                         "n_cells_in_table": len(a)})
    out = pd.DataFrame(rows).set_index(["model", "term"])
    out.attrs["alpha"] = res["negbin_aggregated"].family.alpha
    print(out.round(3).to_string(), "alpha", out.attrs["alpha"])
    return out


def part_testregimes():
    """Share model per regime in the test year. Run only after the test year has been scored in step 6
    (agreed at the step-3 checkpoint): it checks the rain association in the high-coverage regime."""
    stamp = INTERIM / "test_year_first_scored.txt"
    assert stamp.exists(), "score the test year in step 6 first"
    log_test_scoring("03_effects_more.py --part testregimes", "rain association models on test-year rows", "association")
    p = load(years=[2025, 2026], start=pd.Timestamp("2025-10-01"), end=pd.Timestamp("2026-09-30 23:59"))
    p["regime"] = p.regime.astype(str)
    reg = pd.read_csv(INTERIM / "feed_regimes.csv").drop_duplicates("regime").set_index("regime").level_ratio
    rows = []
    for r in sorted(p.regime.unique()):
        q = p[p.regime == r].reset_index(drop=True)
        if r == "spell" or len(q) < 200_000:
            continue
        for t in fit(f"test-year {r}", q, base_X(q), REGS, which=("share", "abs")):
            t = t.loc[BANDS].reset_index(names="term")
            t.attrs = {}
            t["regime"], t["level_ratio"] = r, reg.get(r)
            rows.append(t)
    out = pd.concat(rows)
    out.to_csv(TABLES / "effects_test_year_by_regime.csv", index=False, float_format="%.6f")
    print(out[["regime", "level_ratio", "model", "term", "pct", "pct_lo", "pct_hi", "n"]].round(3).to_string())


def part_robustfix():
    """Re-fit the robustness-sample variant after removing the baseline requirement (review of aac26fe): the
    26 Feb - 1 Mar 2023 spell has no baseline and was silently dropped before. Replaces that variant in
    effects_robust.csv and reports how many rows the spell adds."""
    p = load(drop="drop_robust")
    spell = (p.ts >= "2023-02-26") & (p.ts < "2023-03-02")
    print("robust-sample rows:", len(p), "of which 26 Feb - 1 Mar 2023:", int(spell.sum()))
    res = fit("robust sample", p, base_X(p), REGS)
    rb = pd.read_csv(TABLES / "effects_robust.csv")
    lab = "robustness sample (outage days back in)"
    rb = rb[rb.variant != lab]
    new = []
    for r in res:
        r = r.loc[r.index.intersection(BANDS)].reset_index(names="term")
        r.attrs = {}
        r["variant"] = lab
        r["rows_26feb_1mar_2023"] = int(spell.sum())
        new.append(r)
    pd.concat([rb] + new).to_csv(TABLES / "effects_robust.csv", index=False, float_format="%.6f")


def part_rainlag():
    """Sensitivity: rain window lagged by one 15-minute bin, (t-45, t-15] instead of (t-30, t] (snapshots are
    taken ~19 s before the requested time, so the last bin can include a few seconds after the snapshot). Lags
    shift by the same bin. Computed from the gauge bins exactly as in the panel builder."""
    import importlib
    P1 = importlib.import_module("analysis.01_panel")
    from analysis.common import rain_band
    from pipeline.grid import to_xy
    rain = P1.Rain()
    cells = pd.read_parquet(INTERIM / "cells.parquet")
    cells = cells[cells.eligible].sort_values("cell").reset_index(drop=True)
    cx, cy = to_xy(cells.lon.values, cells.lat.values)
    p = load()
    parts = []
    for y in range(2022, 2026):
        ts = np.sort(p.ts[p.ts.dt.year == y].unique())
        if not len(ts):
            continue
        tsi = pd.DatetimeIndex(ts)
        k = ((tsi - P1.START).total_seconds().values / 60 / P1.BIN).astype(int)
        day = (tsi.normalize() - P1.START).days.values
        ud, inv = np.unique(day, return_inverse=True)
        g = rain.nearest(cx, cy, ud, k=1)[inv][:, :, 0]

        def window(k_end):
            kk = np.broadcast_to(k_end[:, None], g.shape)
            v = (rain.B[g.clip(0), kk] + rain.B[g.clip(0), kk - 1]) * 2
            v[g < 0] = np.nan
            return v

        df = pd.DataFrame({"ts": np.repeat(tsi.values, len(cells)), "cell": np.tile(cells.cell.values, len(tsi)),
                           "mmh_l15": window(k - 1).ravel(), "lag1_l15": window(k - 3).ravel(),
                           "lag2_l15": window(k - 5).ravel()})
        parts.append(df)
    lag = pd.concat(parts)
    p = p.merge(lag, on=["ts", "cell"], how="left")
    p = p[p.mmh_l15.notna() & p.lag1_l15.notna() & p.lag2_l15.notna()].reset_index(drop=True)
    b = rain_band(p.mmh_l15.values)
    cols = [b == 1, b == 2, b == 3, p.lag1_l15.values, p.lag2_l15.values]
    res = fit("rain lagged 15 min", p, cols, REGS)
    rb = pd.read_csv(TABLES / "effects_robust.csv")
    lab = "rain window lagged 15 min, (t-45, t-15]"
    rb = rb[rb.variant != lab]
    new = []
    for r in res:
        r = r.loc[r.index.intersection(BANDS)].reset_index(names="term")
        r.attrs = {}
        r["variant"] = lab
        new.append(r)
    pd.concat([rb] + new).to_csv(TABLES / "effects_robust.csv", index=False, float_format="%.6f")


# ----------------------------------------------------------------------------- charts
def charts():
    style()
    main = pd.read_csv(TABLES / "effects_main.csv", index_col=0)
    # robustness forest plot (heavy rain)
    rb = pd.read_csv(TABLES / "effects_robust.csv")
    nb = pd.read_csv(TABLES / "effects_robust_negbin.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    for ax, m in zip(axes, ["abs", "share"]):
        mm = main[(main.model == m)].loc["heavy"]
        t = rb[(rb.model == m) & (rb.term == "heavy")][["variant", "pct", "pct_lo", "pct_hi"]]
        t = pd.concat([pd.DataFrame([{"variant": "MAIN (fit period, 1 km, 30 min)", "pct": mm.pct, "pct_lo": mm.pct_lo,
                                      "pct_hi": mm.pct_hi}]), t])
        n = nb[(nb.term == "heavy")]
        extra = pd.DataFrame({"variant": ["Poisson, aggregated table (abs only)", "Negative binomial, aggregated table (abs only)"],
                              "pct": n.pct.values, "pct_lo": n.pct_lo.values, "pct_hi": n.pct_hi.values})
        if m == "share":
            extra[["pct", "pct_lo", "pct_hi"]] = np.nan          # keeps the rows aligned with the left panel
        t = pd.concat([t, extra])
        y = np.arange(len(t))[::-1]
        ax.errorbar(t.pct, y, xerr=[t.pct - t.pct_lo, t.pct_hi - t.pct], fmt="o", color=BLUE_DARK if m == "abs" else BLUE,
                    capsize=2, ms=5)
        ax.axvline(mm.pct, color=MUTED, lw=0.8, ls="--")
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.set_yticks(y, t.variant, fontsize=7.5)
        ax.set_title("Absolute count model" if m == "abs" else "Share model", fontsize=9.5)
        ax.set_xlabel("Heavy rain vs dry, % change in vacant taxis")
    fig.suptitle("The heavy-rain association holds across rain measures, samples, grids and time resolutions",
                 x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "effects_robustness", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. 95% CI clustered by day "
         "(aggregated tables: HC1).")
    plt.close(fig)
    # interactions
    it = pd.read_csv(TABLES / "effects_interact.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, m in zip(axes, ["abs", "share"]):
        t = it[it.model == m]
        labels = [f"{g}" for g in t.group]
        y = np.arange(len(t))[::-1]
        ax.errorbar(t.pct, y, xerr=[t.pct - t.pct_lo, t.pct_hi - t.pct], fmt="o", capsize=2, ms=5,
                    color=BLUE_DARK if m == "abs" else BLUE)
        ax.set_yticks(y, labels, fontsize=7.5)
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.set_title("Absolute count model" if m == "abs" else "Share model", fontsize=9.5)
        ax.set_xlabel("Heavy rain vs dry, % change in vacant taxis")
    fig.suptitle("Heavy-rain association by time of day, place, day type and year", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "effects_interactions")
    plt.close(fig)
    # forecast value and approaching rain
    fc = pd.read_csv(TABLES / "effects_forecast.csv")
    ap = pd.read_csv(TABLES / "effects_approach.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    terms = ["ring_light_owndry", "ring_heavier_owndry", "near_light_owndry", "near_heavier_owndry"]
    labs = ["Rain 2-5 km away, light", "Rain 2-5 km away, heavier", "Rain within 2 km, light", "Rain within 2 km, heavier"]
    for k, (m, col) in enumerate((("abs", BLUE_DARK), ("share", BLUE))):
        t = ap[(ap.model == m)].set_index("term").loc[terms]
        y = np.arange(4)[::-1] + (0.15 if k == 0 else -0.15)
        ax.errorbar(t.pct, y, xerr=[t.pct - t.pct_lo, t.pct_hi - t.pct], fmt="o", capsize=2, ms=5, color=col,
                    label="Absolute" if m == "abs" else "Share")
    ax.set_yticks(np.arange(4)[::-1], labs, fontsize=8)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.legend(fontsize=8)
    ax.set_title("Cell still dry (90 min): rain nearby", fontsize=9.5)
    ax.set_xlabel("% change in vacant taxis vs no rain nearby")
    ax = axes[1]
    for k, (v, col) in enumerate((("forecast only", BLUE_DARK), ("forecast + neighbouring rain", ORANGE))):
        t = fc[(fc.variant == v) & (fc.model == "abs")].set_index("term").loc[["fc_light", "fc_showers", "fc_thundery"]]
        y = np.arange(3)[::-1] + (0.12 if k == 0 else -0.12)
        ax.errorbar(t.pct, y, xerr=[t.pct - t.pct_lo, t.pct_hi - t.pct], fmt="o", capsize=2, ms=5, color=col, label=v)
    ax.set_yticks(np.arange(3)[::-1], ["Forecast: light rain", "Forecast: showers", "Forecast: thundery/heavy"], fontsize=8)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.legend(fontsize=8)
    ax.set_title("Cell still dry (90 min): NEA 2-hour forecast as issued (absolute model)", fontsize=9.5)
    ax.set_xlabel("% change in vacant taxis vs fair/cloudy forecast")
    fig.suptitle("Vacant taxis start to thin before rain reaches the cell", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "effects_approach_forecast")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True,
                    choices=["approach", "hetero", "interact", "forecast", "robust", "testregimes", "robustfix", "rainlag",
                             "charts"])
    a = ap.parse_args()
    {"approach": part_approach, "hetero": part_hetero, "interact": part_interact, "forecast": part_forecast,
     "robust": part_robust, "testregimes": part_testregimes, "robustfix": part_robustfix, "rainlag": part_rainlag,
     "charts": charts}[a.part]()


if __name__ == "__main__":
    main()
