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


def features(d):
    d = d.sort_values(["pa", "band", "date"]).copy()
    d["rate"] = d.y / d.exposure
    g = d.groupby(["pa", "band"])
    d["prev1"] = g.rate.shift(1)
    d["prev7"] = g.rate.transform(lambda s: s.shift(1).rolling(7, min_periods=3).mean())
    d["dow"] = d.date.dt.dayofweek
    hol = pd.read_csv("data/static/holidays.csv", parse_dates=["date"])
    ph = set(hol[hol.kind == "public"].date)
    d["daytype"] = np.where(d.date.isin(ph), 2, np.where(d.dow >= 5, 1, 0))
    d["month"] = d.date.dt.month
    fitm = (d.date >= FIT[0]) & (d.date <= FIT[1])
    clim = d[fitm].groupby(["pa", "band", "daytype"]).apply(lambda q: q.y.sum() / q.exposure.sum(), include_groups=False)
    d["clim"] = pd.MultiIndex.from_frame(d[["pa", "band", "daytype"]]).map(clim).values
    lev = pd.read_parquet(INTERIM / "s1_levels.parquet").set_index("ts").lev_7d
    nine = d.date + pd.Timedelta(hours=9)
    d["lev_7d"] = lev.reindex(nine.values, method="ffill").values
    # forecast issued before 09:00
    f = pd.read_csv(geo.P2 / "nea_24h_forecast.csv", parse_dates=["issued", "item_ts", "period_start", "period_end"])
    f = f[f.issued.notna()]
    f["date"] = f.issued.dt.normalize()
    f = f[f.issued.dt.hour < 9].sort_values("issued").groupby(["date", "region", "period_start"]).last().reset_index()
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
    d = d.merge(fw, on=["date", "region"], how="left").merge(gen, left_on="date", right_index=True, how="left")
    return d


def main():
    style()
    d = features(outcomes())
    d = d[d.exposure > 0].reset_index(drop=True)
    d.to_parquet(INTERIM / "morning_panel.parquet", index=False)
    base = ["prev1", "prev7", "clim", "lev_7d", "dow", "daytype", "month", "band_c", "pa_c"]
    fc = ["p12_18", "p18_06", "fc_general", "rh_high", "t_high"]
    d["band_c"] = pd.factorize(d.band)[0]
    d["pa_c"] = pd.factorize(d.pa)[0]
    split = np.select([d.date <= FIT[1], d.date <= CALIB[1]], ["fit", "calib"], "test")
    d["split"] = split
    import lightgbm as lgb
    import statsmodels.api as sm
    rows, preds = [], {}
    for label in ("y", "y_issue"):
        for with_fc in (False, True):
            F = base + (fc if with_fc else [])
            tr, ca, te = (d[d.split == s] for s in ("fit", "calib", "test"))
            ds = lgb.Dataset(tr[F], tr[label], init_score=np.log(tr.exposure), categorical_feature=["pa_c", "band_c"])
            dv = lgb.Dataset(ca[F], ca[label], init_score=np.log(ca.exposure), reference=ds)
            prm = {"objective": "poisson", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 50,
                   "feature_fraction": 0.9, "verbose": -1, "seed": SEED}
            m = lgb.train(prm, ds, 3000, valid_sets=[dv], callbacks=[lgb.early_stopping(100, verbose=False)])
            mu = np.exp(m.predict(te[F], raw_score=True, num_iteration=m.best_iteration) + np.log(te.exposure))
            # Poisson GLM with offset
            Xg = pd.get_dummies(d[F].fillna(d[F].median(numeric_only=True)), columns=["dow", "daytype", "month",
                                                                                       "band_c", "pa_c"], drop_first=True,
                                dtype=float)
            Xg = sm.add_constant(Xg)
            g = sm.GLM(tr[label], Xg.loc[tr.index], family=sm.families.Poisson(), offset=np.log(tr.exposure)).fit()
            mug = g.predict(Xg.loc[te.index], offset=np.log(te.exposure))
            for name, mu_ in (("lgb", mu), ("glm", mug)):
                preds[(label, name, with_fc)] = np.asarray(mu_)
    log_test_scoring("15_morning.py", "morning-forecast models scored on the test year (once)", "step 15")
    te = d[d.split == "test"].reset_index(drop=True)

    def dev(y, mu):
        mu = np.maximum(mu, 1e-9)
        return 2 * (np.where(y > 0, y * np.log(np.maximum(y, 1e-12) / mu), 0) - (y - mu))

    days = te.date.values
    ud = np.sort(np.unique(days))
    di = np.searchsorted(ud, days)
    W = np.random.default_rng(SEED).multinomial(len(ud), np.full(len(ud), 1 / len(ud)), size=1000).astype(float)
    for label in ("y", "y_issue"):
        for name in ("lgb", "glm"):
            y = te[label].values
            d0, d1 = dev(y, preds[(label, name, False)]), dev(y, preds[(label, name, True)])
            D0, D1 = np.bincount(di, d0, len(ud)), np.bincount(di, d1, len(ud))
            imp = 1 - d1.sum() / d0.sum()
            bimp = 1 - (W @ D1) / (W @ D0)
            mae0 = np.mean(np.abs(y - preds[(label, name, False)]))
            mae1 = np.mean(np.abs(y - preds[(label, name, True)]))
            rows.append({"label": "retrospective" if label == "y" else "issue-time", "model": name,
                         "deviance_without": d0.sum(), "deviance_with": d1.sum(), "deviance_improvement_pct": 100 * imp,
                         "lo": 100 * np.quantile(bimp, 0.025), "hi": 100 * np.quantile(bimp, 0.975),
                         "mae_without": mae0, "mae_with": mae1, "test_rows": len(te),
                         "material_rule_met": bool(imp >= 0.02 and np.quantile(bimp, 0.025) > 0)})
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "morning_forecast_value.csv", index=False, float_format="%.5f")
    print(r.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
