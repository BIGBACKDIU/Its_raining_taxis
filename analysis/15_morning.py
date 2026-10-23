"""Step 15: planning value of the morning 24-hour forecast (pre-registration: decision 113).

Unit: planning area x time band x day. Outcome: number of low-availability cell-half-hours (retrospective deficit
label; issue-time label as a check). Models with and without the NEA 24-hour forecast issued before 09:00;
fit Apr 2022 - Mar 2025, early stopping on Apr - Sep 2025, test year scored once (logged).
Usage: .venv/bin/python -m analysis.15_morning
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis import geo
from analysis.common import CALIB, FIT, INTERIM, SEED, TABLES, TEST, load_panel, log_test_scoring, save, style

BANDS = [("10-17", 10, 17), ("17-20", 17, 20), ("20-24", 20, 24)]
ANCHORS = {"north": (103.82, 1.43), "south": (103.82, 1.28), "east": (103.94, 1.35), "west": (103.70, 1.35),
           "central": (103.82, 1.35)}


def fc_code(s):
    t = s.fillna("").str.lower()
    return np.select([t.str.contains("thunder|heavy"), t.str.contains("shower|rain|drizzle"),
                      t.str.contains("cloudy|overcast|mist")], [3, 2, 1], 0)


def outcomes():
    names = pd.read_csv(TABLES / "names_cells.csv").set_index("cell")
    pat = pd.read_parquet(INTERIM / "forecast_pattern.parquet")
    lev = pd.read_parquet(INTERIM / "s1_levels.parquet").set_index("ts").lev_7d
    parts = []
    for y in range(2022, 2027):
        p = load_panel([y], columns=["ts", "cell", "vacant", "low", "drop_main", "how", "month"])
        p = p[~p.drop_main & (p.ts >= FIT[0])]
        p = p.merge(pat, on=["cell", "how", "month"], how="left")
        base_f = p.pattern.values * p.ts.map(lev).values
        p["low_issue"] = np.where(base_f >= 4, ((base_f - p.vacant) / np.maximum(1, base_f) >= 0.5).astype(float), np.nan)
        h = p.ts.dt.hour
        p["band"] = np.select([(h >= a) & (h < b) for _, a, b in BANDS], [n for n, _, _ in BANDS], None)
        p = p[p.band.notna()]
        p["pa"] = p.cell.map(names.planning_area)
        p["date"] = p.ts.dt.normalize()
        p["lowf"] = p.low.astype(float)
        g = p.groupby(["pa", "band", "date"]).agg(y=("lowf", "sum"), y_issue=("low_issue", "sum"),
                                                  exposure=("cell", "size")).reset_index()
        parts.append(g)
        print(y, flush=True)
    return pd.concat(parts, ignore_index=True)


HALF_HOURS = {"10-17": 14, "17-20": 6, "20-24": 8}


def features(d, label):
    """Features knowable at 09:00 (decision 131): history of the issue-time label only, scheduled exposure
    (eligible cells in the area x half-hours in the band), climatology of the modelled label on fit-period days,
    and the latest single NEA 24-hour forecast issued before 09:00."""
    d = d.sort_values(["pa", "band", "date"]).copy()
    names = pd.read_csv(TABLES / "names_cells.csv")
    ncell = names[names.eligible].groupby("planning_area").size()
    d["exposure_sched"] = d.pa.map(ncell).fillna(1).values * d.band.map(HALF_HOURS).values
    d["rate_issue"] = d.y_issue / d.exposure_sched
    g = d.groupby(["pa", "band"])
    d["prev1"] = g.rate_issue.shift(1)
    d["prev7"] = g.rate_issue.transform(lambda s: s.shift(1).rolling(7, min_periods=3).mean())
    d["dow"] = d.date.dt.dayofweek
    hol = pd.read_csv("data/static/holidays.csv", parse_dates=["date"])
    ph = set(hol[hol.kind == "public"].date)
    d["daytype"] = np.where(d.date.isin(ph), 2, np.where(d.dow >= 5, 1, 0))
    d["month"] = d.date.dt.month
    fitm = (d.date >= FIT[0]) & (d.date <= FIT[1])
    clim = d[fitm].groupby(["pa", "band", "daytype"]).apply(lambda q: q[label].sum() / q.exposure_sched.sum(),
                                                             include_groups=False)
    d["clim"] = pd.MultiIndex.from_frame(d[["pa", "band", "daytype"]]).map(clim).values
    lev = pd.read_parquet(INTERIM / "s1_levels.parquet").set_index("ts").lev_7d
    nine = d.date + pd.Timedelta(hours=9)
    d["lev_7d"] = lev.reindex(nine.values, method="ffill").values
    # the single latest forecast issued before 09:00 that day
    f = pd.read_csv(geo.P2 / "nea_24h_forecast.csv", parse_dates=["issued", "item_ts", "period_start", "period_end"])
    f = f[f.issued.notna()]
    f["date"] = f.issued.dt.normalize()
    f = f[f.issued.dt.hour < 9]
    last = f.groupby("date").issued.transform("max")
    f = f[f.issued == last].copy()
    f["code"] = fc_code(f.forecast)
    f["gcode"] = fc_code(f.general)
    f["slot"] = np.select([f.period_start.dt.hour.between(12, 17) & (f.period_start.dt.normalize() == f.date),
                           (f.period_start.dt.hour >= 18) & (f.period_start.dt.normalize() == f.date)], ["p12_18", "p18_06"],
                          "other")
    fw = f[f.slot != "other"].pivot_table(index=["date", "region"], columns="slot", values="code", aggfunc="max").reset_index()
    gen = f.groupby("date").agg(fc_general=("gcode", "max"), rh_high=("rh_high", "max"), t_high=("t_high", "max"))
    pa_reg = {}
    sz = geo.subzones().to_crs(geo.CRS)
    cent = sz.dissolve("planning_area").geometry.centroid.to_crs(4326)
    for pa, pt in cent.items():
        pa_reg[pa] = min(ANCHORS, key=lambda k: (pt.x - ANCHORS[k][0]) ** 2 + (pt.y - ANCHORS[k][1]) ** 2)
    d["region"] = d.pa.map(pa_reg)
    d = d.drop(columns=[c for c in ("p12_18", "p18_06", "fc_general", "rh_high", "t_high") if c in d])
    d = d.merge(fw, on=["date", "region"], how="left").merge(gen, left_on="date", right_index=True, how="left")
    return d


def main():
    import sys
    style()
    f = INTERIM / "morning_panel.parquet"
    if "--reuse" in sys.argv and f.exists():         # outcomes (labels) do not change between runs
        d0 = pd.read_parquet(f)[["pa", "band", "date", "y", "y_issue", "exposure"]]
    else:
        d0 = outcomes()
        d0.to_parquet(f, index=False)
    d0 = d0[d0.exposure > 0].reset_index(drop=True)
    import lightgbm as lgb
    import statsmodels.api as sm
    base = ["prev1", "prev7", "clim", "lev_7d", "dow", "daytype", "month", "band_c", "pa_c"]
    fc = ["p12_18", "p18_06", "fc_general", "rh_high", "t_high"]
    rows, preds, tests = [], {}, {}
    for label in ("y", "y_issue"):
        d = features(d0, label).reset_index(drop=True)
        d["band_c"] = pd.factorize(d.band)[0]
        d["pa_c"] = pd.factorize(d.pa)[0]
        d["split"] = np.select([d.date <= FIT[1], d.date <= CALIB[1]], ["fit", "calib"], "test")
        tr, ca, te = (d[d.split == s_] for s_ in ("fit", "calib", "test"))
        off = {k: np.log(v.exposure_sched.values) for k, v in (("tr", tr), ("ca", ca), ("te", te))}
        tests[label] = te.reset_index(drop=True)
        for with_fc in (False, True):
            F = base + (fc if with_fc else [])
            ds = lgb.Dataset(tr[F], tr[label], init_score=off["tr"], categorical_feature=["pa_c", "band_c"])
            dv = lgb.Dataset(ca[F], ca[label], init_score=off["ca"], reference=ds)
            prm = {"objective": "poisson", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 50,
                   "feature_fraction": 0.9, "verbose": -1, "seed": SEED}
            m = lgb.train(prm, ds, 3000, valid_sets=[dv], callbacks=[lgb.early_stopping(100, verbose=False)])
            preds[(label, "lgb", with_fc)] = np.exp(m.predict(te[F], raw_score=True, num_iteration=m.best_iteration)
                                                    + off["te"])
            med = tr[F].median(numeric_only=True)                 # imputation fitted on training rows only
            Xg = pd.get_dummies(d[F].fillna(med), columns=["dow", "daytype", "month", "band_c", "pa_c"], drop_first=True,
                                dtype=float)
            Xg = sm.add_constant(Xg)
            g = sm.GLM(tr[label], Xg.loc[tr.index], family=sm.families.Poisson(), offset=off["tr"]).fit()
            preds[(label, "glm", with_fc)] = np.asarray(g.predict(Xg.loc[te.index], offset=off["te"]))
    log_test_scoring("15_morning.py", "morning-forecast models re-scored on the test year after the timing fixes "
                     "(issue-time history, scheduled exposure, train-only imputation, one forecast issue)", "step 15 fix")

    def dev(y, mu):
        mu = np.maximum(mu, 1e-9)
        return 2 * (np.where(y > 0, y * np.log(np.maximum(y, 1e-12) / mu), 0) - (y - mu))

    for label in ("y", "y_issue"):
        te = tests[label]
        days = te.date.values
        ud = np.sort(np.unique(days))
        di = np.searchsorted(ud, days)
        W = np.random.default_rng(SEED).multinomial(len(ud), np.full(len(ud), 1 / len(ud)), size=1000).astype(float)
        for name in ("lgb", "glm"):
            y = te[label].values
            d0_, d1_ = dev(y, preds[(label, name, False)]), dev(y, preds[(label, name, True)])
            D0, D1 = np.bincount(di, d0_, len(ud)), np.bincount(di, d1_, len(ud))
            imp = 1 - d1_.sum() / d0_.sum()
            bimp = 1 - (W @ D1) / (W @ D0)
            rows.append({"label": "retrospective" if label == "y" else "issue-time", "model": name,
                         "deviance_without": d0_.sum(), "deviance_with": d1_.sum(), "deviance_improvement_pct": 100 * imp,
                         "lo": 100 * np.quantile(bimp, 0.025), "hi": 100 * np.quantile(bimp, 0.975),
                         "mae_without": np.mean(np.abs(y - preds[(label, name, False)])),
                         "mae_with": np.mean(np.abs(y - preds[(label, name, True)])), "test_rows": len(te),
                         "material_rule_met": bool(imp >= 0.02 and np.quantile(bimp, 0.025) > 0)})
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "morning_forecast_value.csv", index=False, float_format="%.5f")
    print(r.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
