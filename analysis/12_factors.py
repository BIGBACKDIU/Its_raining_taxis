"""Step 12: why some areas lose more vacant taxis in heavy rain (pre-registration: decisions 105-108).

Parts:
  chars    per-cell characteristics for every named cell -> outputs/tables/cell_characteristics.csv
  cell     design (i): weighted regression, VIF, Moran's I, spatial error model, random forest + SHAP (spatial CV),
           type prediction
  panel    design (ii): heavy rain x characteristic interactions in the Poisson FE panel
  charts
Supply associations only: characteristics describe places, they are not shown to cause the rain effect.
Usage: .venv/bin/python -m analysis.12_factors --part chars | cell | panel | charts
"""
from __future__ import annotations

import argparse
import importlib

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from analysis import geo
from analysis.common import BLUE, BLUE_DARK, FIT, INTERIM, MUTED, ORANGE, SEED, TABLES, save, style
from pipeline.grid import cell_ids, coarsen, to_xy

BLOCK_KM = 5


# ============================================================================= characteristics
def in_cell(lon, lat):
    return coarsen(cell_ids(np.asarray(lon), np.asarray(lat), 500))


def cell_count(cells, lon, lat):
    c = pd.Series(in_cell(lon, lat)).value_counts()
    return cells.map(c).fillna(0).values


def within_square(cells_df, plon, plat, buffer_m):
    """Points within buffer_m of each 1 km cell square."""
    px, py = to_xy(np.asarray(plon), np.asarray(plat))
    x0 = cells_df.cell.values // 1000 * 1000.0
    y0 = cells_df.cell.values % 1000 * 1000.0
    out = np.zeros(len(cells_df), int)
    tree = cKDTree(np.c_[px, py])
    for k, (a, b) in enumerate(zip(x0, y0)):
        cand = tree.query_ball_point([a + 500, b + 500], 500 * np.sqrt(2) + buffer_m)
        if not cand:
            continue
        dx = np.maximum(0, np.maximum(a - px[cand], px[cand] - (a + 1000)))
        dy = np.maximum(0, np.maximum(b - py[cand], py[cand] - (b + 1000)))
        out[k] = int((np.hypot(dx, dy) <= buffer_m).sum())
    return out


def part_chars():
    names = pd.read_csv(TABLES / "names_cells.csv")
    c = names[["cell", "lon", "lat", "planning_area", "subzone", "eligible", "land"]].copy()
    st, ex = geo.mrt()
    mx = ex[ex.network.str.contains("mrt")]                    # MRT station exits only (LRT stops excluded)
    c["dist_mrt_exit_m"] = geo.dist_to(c.lon, c.lat, mx.lon, mx.lat)
    c["mrt_exits_500m"] = geo.counts_within(c.lon, c.lat, mx.lon, mx.lat, 500)
    sx, sy = to_xy(st.lon.values, st.lat.values)
    x, y = to_xy(c.lon.values, c.lat.values)
    tree = cKDTree(np.c_[sx, sy])
    near = tree.query_ball_point(np.c_[x, y], 800)
    c["mrt_lines_800m"] = [len(frozenset().union(*st.line_set.iloc[idx])) if idx else 0 for idx in near]
    c["interchange_800m"] = [bool(st.interchange.iloc[idx].any()) if idx else False for idx in near]
    c["new_station_800m"] = [bool(st.opened.iloc[idx].notna().any()) if idx else False for idx in near]
    p = geo.pois()
    for cat, col in (("bus stop", "bus_stops"), ("mall", "malls"), ("hospital", "hospitals"), ("hotel", "hotels"),
                     ("office", "offices"), ("nightlife", "nightlife"), ("food", "food_outlets"),
                     ("attraction", "attractions")):
        q = p[p.category == cat]
        c[col] = cell_count(c.cell, q.lon, q.lat)
    q = p[p.category.isin(["school", "university"])]
    c["schools"] = cell_count(c.cell, q.lon, q.lat)
    ts = pd.read_csv("data/static/lta_taxi_stops.csv")
    c["taxi_stands_300m"] = within_square(c, ts.lon, ts.lat, 300)
    q = p[p.category == "taxi point"]
    c["osm_taxi_points_300m"] = within_square(c, q.lon, q.lat, 300)
    # housing
    hdb_f = geo.P2 / "hdb_blocks_geocoded.csv"
    if hdb_f.exists():
        b = pd.read_csv(hdb_f).dropna(subset=["lat", "lon"])
        b["cell"] = in_cell(b.lon, b.lat)
        c["hdb_units"] = c.cell.map(b.groupby("cell").total_dwelling_units.sum()).fillna(0).values
        rs = pd.read_csv(geo.P2 / "hdb_resale.csv")
        rs["psf"] = rs.resale_price / (rs.floor_area_sqm * 10.7639)
        key = (b.blk_no.astype(str).str.strip().str.upper() + "|" + b.street.astype(str).str.strip().str.upper())
        bmap = pd.Series(b.cell.values, index=key)
        bmap = bmap[~bmap.index.duplicated()]
        rkey = rs.block.astype(str).str.strip().str.upper() + "|" + rs.street_name.astype(str).str.strip().str.upper()
        rs["cell"] = rkey.map(bmap)
        c["hdb_resale_psf"] = c.cell.map(rs.groupby("cell").psf.median()).values
        c.attrs["hdb_resale_matched"] = float(rs.cell.notna().mean())
    pr = pd.read_csv(geo.P2 / "private_projects_psf.csv")
    pr["cell"] = in_cell(pr.lon, pr.lat)
    c["private_projects"] = c.cell.map(pr.groupby("cell").size()).fillna(0).values
    c["private_transactions"] = c.cell.map(pr.groupby("cell").transactions.sum()).fillna(0).values
    c["private_psf"] = c.cell.map(pr.groupby("cell").median_psf.median()).values
    hdb = c.get("hdb_units", pd.Series(np.zeros(len(c))))
    c["share_private_tx"] = np.where(c.private_transactions + hdb > 0, c.private_transactions / (c.private_transactions + hdb),
                                     np.nan)
    r = geo.residents_by_cell()
    c = c.merge(r[["cell", "residents", "share_65plus"]], on="cell", how="left").fillna({"residents": 0})
    lu = geo.landuse_shares()
    c = c.merge(lu, on="cell", how="left")
    sz = geo.subzones()
    pts = gpd.GeoDataFrame(c[["cell"]], geometry=gpd.points_from_xy(c.lon, c.lat), crs=4326)
    ca = gpd.sjoin(pts, sz[["central_area", "geometry"]], how="left", predicate="within").drop_duplicates("cell")
    c["central_area"] = c.cell.map(ca.set_index("cell").central_area.eq("Y")).fillna(False).values
    # roads
    nodes = pd.read_parquet(geo.P2 / "osm_drive_nodes.parquet")
    e = pd.read_parquet(geo.P2 / "osm_drive_edges.parquet")
    ll = nodes.set_index("node")
    e = e.join(ll, on="u")
    e["cell"] = in_cell(e.lon.values, e.lat.values)
    cls = e.highway.str.replace("_link", "", regex=False)
    e["cls"] = np.select([cls.eq("motorway"), cls.isin(["trunk", "primary"])], ["expressway", "arterial"], "other")
    L = e.groupby(["cell", "cls"]).length_m.sum().unstack(fill_value=0) / 2000.0        # km, both directions
    for k in ("expressway", "arterial", "other"):
        c[f"road_km_{k}"] = c.cell.map(L.get(k, pd.Series(dtype=float))).fillna(0).values
    c["road_km_total"] = c[["road_km_expressway", "road_km_arterial", "road_km_other"]].sum(1)
    mw = e[e.highway.str.startswith("motorway")]
    c["dist_expressway_m"] = geo.dist_to(c.lon, c.lat, mw.lon, mw.lat)
    c["betweenness"] = c.cell.map(betweenness(nodes, e)).fillna(0).values
    c["dist_city_km"] = geo.dist_to(c.lon, c.lat, [geo.CITY_CENTRE[0]], [geo.CITY_CENTRE[1]]) / 1000
    c["dist_airport_km"] = geo.dist_to(c.lon, c.lat, [geo.AIRPORT[0]], [geo.AIRPORT[1]]) / 1000
    c.to_csv(TABLES / "cell_characteristics.csv", index=False, float_format="%.5f")
    print(c.describe().T.round(2).to_string())
    print("HDB resale matched to geocoded blocks:", c.attrs.get("hdb_resale_matched"))


def betweenness(nodes, e, k=500):
    import networkx as nx
    sk = e[e.highway.str.replace("_link", "", regex=False).isin(["motorway", "trunk", "primary", "secondary"])]
    G = nx.DiGraph()
    for u, v, l in zip(sk.u.values, sk.v.values, sk.length_m.values):
        G.add_edge(u, v, w=l)
    G = G.subgraph(max(nx.strongly_connected_components(G), key=len)).copy()
    bc = nx.betweenness_centrality(G, k=min(k, G.number_of_nodes()), weight="w", seed=SEED)
    b = pd.Series(bc)
    ll = nodes.set_index("node").reindex(b.index)
    cell = in_cell(ll.lon.values, ll.lat.values)
    return pd.Series(b.values, index=cell).groupby(level=0).max()


# ============================================================================= design (i)
NUM = ["dist_mrt_exit_m", "mrt_exits_500m", "mrt_lines_800m", "bus_stops", "hdb_units", "private_transactions",
       "share_private_tx", "hdb_resale_psf", "private_psf", "residents", "share_65plus", "lu_residential", "lu_commercial",
       "lu_business", "lu_institution", "lu_park", "malls", "hospitals", "hotels", "offices", "schools", "nightlife",
       "food_outlets", "attractions", "taxi_stands_300m", "osm_taxi_points_300m", "road_km_total", "road_km_expressway",
       "road_km_arterial", "dist_expressway_m", "betweenness", "dist_city_km", "dist_airport_km"]
BOOL = ["interchange_800m", "new_station_800m", "central_area"]
LOGS = {"mrt_exits_500m", "bus_stops", "hdb_units", "private_transactions", "residents", "malls", "hospitals", "hotels",
        "offices", "schools", "nightlife", "food_outlets", "attractions", "taxi_stands_300m", "osm_taxi_points_300m",
        "betweenness"}


def fit_scaling(c, cols):
    """Imputation (median) and standardisation (mean, sd) fitted on the given rows, after the log transforms."""
    par = {}
    for k in cols:
        v = c[k].astype(float)
        if k in LOGS:
            v = np.log1p(v)
        med = float(v.median())
        v = v.fillna(med)
        par[k] = (med, float(v.mean()), float(v.std()) if v.std() > 0 else 1.0)
    return par


def design_matrix(c, cols, scaling=None):
    """Standardised characteristics; with `scaling` (from fit_scaling on the training rows) the stored
    imputation and scaling are applied unchanged, so predictions for new cells use the training transform."""
    par = scaling if scaling is not None else fit_scaling(c, cols)
    X = pd.DataFrame(index=c.index)
    for k in cols:
        v = c[k].astype(float)
        if k in LOGS:
            v = np.log1p(v)
        med, mu, sd = par[k]
        X[k] = (v.fillna(med) - mu) / sd
    return X


def vif_prune(X, limit=10.0):
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    cols = list(X.columns)
    dropped = []
    while True:
        A = X[cols].values
        v = np.array([variance_inflation_factor(A, i) for i in range(len(cols))])
        if v.max() <= limit:
            return cols, dropped, pd.Series(v, index=cols)
        j = int(np.argmax(v))
        dropped.append((cols[j], float(v[j])))
        cols.pop(j)


def outcome(e, kind):
    pct, lo, hi = e[f"{kind}_pct"], e[f"{kind}_lo"], e[f"{kind}_hi"]
    y = np.log1p(pct / 100)
    se = (np.log1p(hi / 100) - np.log1p(lo / 100)) / 3.92
    return y, se


def blocks(c):
    x, y = to_xy(c.lon.values, c.lat.values)
    return (np.floor(x / (BLOCK_KM * 1000)) * 1000 + np.floor(y / (BLOCK_KM * 1000))).astype(int)


def part_cell():
    import statsmodels.api as sm
    from libpysal.weights import KNN
    from esda.moran import Moran
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import r2_score, roc_auc_score
    from sklearn.model_selection import GroupKFold
    c = pd.read_csv(TABLES / "cell_characteristics.csv")
    e = pd.read_csv(TABLES / "cell_rain_effects.csv")
    d = c.merge(e[["cell", "abs_pct", "abs_lo", "abs_hi", "share_pct", "share_lo", "share_hi", "tested"]], on="cell")
    d = d[d.tested].reset_index(drop=True)
    scaling = fit_scaling(d, NUM)
    X = design_matrix(d, NUM, scaling)
    for b in BOOL:
        X[b] = d[b].astype(float).values
    keep, dropped, vif = vif_prune(X)
    print("VIF kept", len(keep), "dropped", dropped, flush=True)
    out, coef_rows, rf_rows = {}, [], []
    W = KNN.from_array(np.c_[to_xy(d.lon.values, d.lat.values)], k=8)
    W.transform = "r"
    grp = blocks(d)
    for kind in ("abs", "share"):
        y, se = outcome(d, kind)
        ok = np.isfinite(y) & np.isfinite(se)
        Xk = sm.add_constant(X.loc[ok, keep])
        ols = sm.WLS(y[ok], Xk, weights=1 / se[ok] ** 2).fit()
        r = ols.resid
        Q = float(np.sum(r ** 2 / se[ok] ** 2))
        tau2 = max(0.0, (Q - (ok.sum() - Xk.shape[1])) / np.sum(1 / se[ok] ** 2))
        m = sm.WLS(y[ok], Xk, weights=1 / (se[ok] ** 2 + tau2)).fit(cov_type="HC1")
        Wk = KNN.from_array(np.c_[to_xy(d.lon.values[ok], d.lat.values[ok])], k=8)
        Wk.transform = "r"
        mi = Moran(m.resid, Wk, permutations=999)
        row = {"outcome": kind, "cells": int(ok.sum()), "tau2": tau2, "r2": m.rsquared, "moran_I": mi.I, "moran_p": mi.p_sim}
        sem_params = None
        if mi.p_sim < 0.05:
            from spreg import ML_Error
            sem = ML_Error(y[ok].values.reshape(-1, 1), X.loc[ok, keep].values, w=Wk, name_x=keep, name_y=kind)
            sem_params = pd.Series(np.asarray(sem.betas).ravel()[1:len(keep) + 1], index=keep)
            sem_se = pd.Series(np.asarray(sem.std_err).ravel()[1:len(keep) + 1], index=keep)
            row["sem_lambda"] = float(np.asarray(sem.lam).ravel()[0])
            mi2 = Moran(np.asarray(sem.e_filtered).ravel(), Wk, permutations=999)
            row["moran_I_after_sem"], row["moran_p_after_sem"] = mi2.I, mi2.p_sim
        out[kind] = row
        for k in keep:
            cr = {"outcome": kind, "characteristic": k, "coef_log_per_sd": m.params[k], "se": m.bse[k], "p": m.pvalues[k],
                  "pct_per_sd": 100 * (np.exp(m.params[k]) - 1), "pct_lo": 100 * (np.exp(m.params[k] - 1.96 * m.bse[k]) - 1),
                  "pct_hi": 100 * (np.exp(m.params[k] + 1.96 * m.bse[k]) - 1), "vif": vif[k]}
            if sem_params is not None:
                cr["sem_pct_per_sd"] = 100 * (np.exp(sem_params[k]) - 1)
                cr["sem_lo"] = 100 * (np.exp(sem_params[k] - 1.96 * sem_se[k]) - 1)
                cr["sem_hi"] = 100 * (np.exp(sem_params[k] + 1.96 * sem_se[k]) - 1)
            coef_rows.append(cr)
        # random forest with spatial block CV and SHAP
        Xa = X.loc[ok]
        pred = np.zeros(ok.sum())
        for tr, te in GroupKFold(5).split(Xa, y[ok], grp[ok]):
            rf = RandomForestRegressor(500, min_samples_leaf=5, random_state=SEED, n_jobs=-1)
            rf.fit(Xa.iloc[tr], y[ok].iloc[tr], sample_weight=1 / (se[ok].iloc[tr] ** 2 + tau2))
            pred[te] = rf.predict(Xa.iloc[te])
        row["rf_spatial_cv_r2"] = float(r2_score(y[ok], pred, sample_weight=1 / (se[ok] ** 2 + tau2)))
        rf = RandomForestRegressor(500, min_samples_leaf=5, random_state=SEED, n_jobs=-1)
        rf.fit(Xa, y[ok], sample_weight=1 / (se[ok] ** 2 + tau2))
        import shap
        sv = shap.TreeExplainer(rf).shap_values(Xa)
        imp = pd.DataFrame({"outcome": kind, "characteristic": Xa.columns, "mean_abs_shap": np.abs(sv).mean(0),
                            "direction_corr": [np.corrcoef(Xa[k], sv[:, i])[0, 1] if Xa[k].std() > 0 else np.nan
                                               for i, k in enumerate(Xa.columns)]})
        rf_rows.append(imp.sort_values("mean_abs_shap", ascending=False))
        import joblib
        joblib.dump({"model": rf, "columns": list(Xa.columns), "tau2": tau2, "scaling": scaling, "bool": BOOL,
                     "keep_wls": keep}, INTERIM / f"rf_rain_{kind}.joblib")
    pd.DataFrame(coef_rows).to_csv(TABLES / "factors_cell_wls.csv", index=False, float_format="%.5f")
    pd.concat(rf_rows).to_csv(TABLES / "factors_cell_rf_shap.csv", index=False, float_format="%.6f")
    pd.DataFrame({"dropped_for_vif": [a for a, _ in dropped], "vif": [b for _, b in dropped]}).to_csv(
        TABLES / "factors_vif_dropped.csv", index=False)
    # type prediction
    ty = pd.read_csv(TABLES / "risk_types.csv").set_index("cell").type
    yt = (d.cell.map(ty) == 0).astype(int)
    okt = d.cell.map(ty).notna().values
    aucs = {}
    for name, mk in (("logistic", lambda: LogisticRegression(max_iter=2000, C=1.0)),
                     ("random forest", lambda: RandomForestClassifier(500, min_samples_leaf=5, random_state=SEED, n_jobs=-1))):
        pr = np.zeros(okt.sum())
        Xt, yy, gg = X.loc[okt, keep], yt[okt], grp[okt]
        for tr, te in GroupKFold(5).split(Xt, yy, gg):
            mdl = mk().fit(Xt.iloc[tr], yy.iloc[tr])
            pr[te] = mdl.predict_proba(Xt.iloc[te])[:, 1]
        aucs[name] = float(roc_auc_score(yy, pr))
    summ = pd.DataFrame(out).T
    summ["type0_spatial_cv_auc_logistic"] = aucs["logistic"]
    summ["type0_spatial_cv_auc_rf"] = aucs["random forest"]
    summ.to_csv(TABLES / "factors_cell_summary.csv", float_format="%.5f")
    print(summ.round(4).to_string())
    print(pd.DataFrame(coef_rows).query("p < 0.05")[["outcome", "characteristic", "pct_per_sd", "pct_lo", "pct_hi"]]
          .round(2).to_string(index=False))
    print(pd.concat(rf_rows).groupby("outcome").head(8).round(4).to_string(index=False))


# ============================================================================= design (ii)
def part_panel():
    from analysis.fepois_hd import fepois, pct
    E = importlib.import_module("analysis.03_effects")
    c = pd.read_csv(TABLES / "cell_characteristics.csv").set_index("cell")
    p = E.load_fit()
    p = p[E.sample(p)].reset_index(drop=True)
    X, fe_abs, fe_share, day = E.design(p)
    heavy = (p.rain_band.values == 3)
    dm = p.cell.map(c.dist_mrt_exit_m).values
    z = lambda s: (s - s.mean()) / s.std()
    cc = c.loc[c.eligible]
    terms = {"heavy_x_mrt_lt300m": heavy & (dm < 300), "heavy_x_mrt_300_1000m": heavy & (dm >= 300) & (dm < 1000),
             "heavy_x_central_area": heavy & p.cell.map(c.central_area).values.astype(bool),
             "heavy_x_taxi_stand_300m": heavy & (p.cell.map(c.taxi_stands_300m).values > 0),
             "heavy_x_mall": heavy & (p.cell.map(c.malls).values > 0),
             "heavy_x_hdb_units_sd": heavy * p.cell.map(z(np.log1p(cc.hdb_units))).fillna(0).values,
             "heavy_x_dist_city_sd": heavy * p.cell.map(z(cc.dist_city_km)).fillna(0).values}
    names = E.REGS + list(terms)
    XX = np.column_stack([X] + [np.asarray(v, "float32") for v in terms.values()]).astype("float32")
    rows = []
    for kind, fes in (("abs", fe_abs), ("share", fe_share)):
        r = fepois(p.vacant.values, XX, names, fes, day, xt_dtype="float32")
        V = r.attrs["vcov"]
        rr = pct(r)
        rr.insert(0, "model", kind)
        rr.attrs = {}
        rows.append(rr.reset_index(names="term"))
        # contrasts: heavy effect for a cell with an MRT exit < 300 m vs >= 1 km (others at reference / mean)
        for lab, terms_c in (("heavy, MRT < 300 m (vs >= 1 km reference)", ["heavy", "heavy_x_mrt_lt300m"]),
                             ("heavy, MRT 300-1000 m", ["heavy", "heavy_x_mrt_300_1000m"]),
                             ("heavy, MRT >= 1 km (reference)", ["heavy"]),
                             ("heavy, Central Area", ["heavy", "heavy_x_central_area"]),
                             ("heavy, taxi stand within 300 m", ["heavy", "heavy_x_taxi_stand_300m"]),
                             ("heavy, mall in cell", ["heavy", "heavy_x_mall"])):
            b = r.coef[terms_c].sum()
            se = np.sqrt(V.loc[terms_c, terms_c].values.sum())
            rows.append(pd.DataFrame([{"model": kind, "term": "CONTRAST: " + lab, "coef": b, "se": se,
                                       "pct": 100 * (np.exp(b) - 1), "pct_lo": 100 * (np.exp(b - 1.96 * se) - 1),
                                       "pct_hi": 100 * (np.exp(b + 1.96 * se) - 1)}]))
        print(kind, rr[["pct", "pct_lo", "pct_hi"]].round(2).to_string(), flush=True)
    t = pd.concat(rows)
    t.to_csv(TABLES / "factors_panel_interactions.csv", index=False, float_format="%.5f")
    print(t[t.term.str.startswith("CONTRAST")][["model", "term", "pct", "pct_lo", "pct_hi"]].round(2).to_string(index=False))


def charts():
    style()
    s = pd.read_csv(TABLES / "factors_cell_rf_shap.csv")
    w = pd.read_csv(TABLES / "factors_cell_wls.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    labels = {"dist_city_km": "Distance to Raffles Place", "central_area": "URA Central Area", "hotels": "Hotels",
              "offices": "Offices", "malls": "Malls", "attractions": "Attractions", "nightlife": "Bars / nightlife",
              "food_outlets": "Food outlets", "hdb_units": "HDB dwelling units", "residents": "Residents",
              "dist_mrt_exit_m": "Distance to MRT exit", "mrt_exits_500m": "MRT exits within 500 m", "lu_commercial": "Commercial land",
              "lu_residential": "Residential land", "taxi_stands_300m": "Taxi stops / stands", "betweenness": "Road betweenness",
              "dist_airport_km": "Distance to airport", "road_km_total": "Road length", "bus_stops": "Bus stops",
              "hdb_resale_psf": "HDB resale price (psf)", "private_psf": "Private housing price (psf)",
              "lu_park": "Park land", "lu_business": "Business / industrial land", "lu_institution": "Institutional land",
              "share_65plus": "Share of residents 65+", "road_km_arterial": "Arterial road length",
              "road_km_expressway": "Expressway length", "dist_expressway_m": "Distance to expressway",
              "hospitals": "Hospitals", "schools": "Schools", "private_transactions": "Private housing transactions",
              "share_private_tx": "Share private housing", "mrt_lines_800m": "MRT lines within 800 m",
              "osm_taxi_points_300m": "OSM taxi points"}
    summ = pd.read_csv(TABLES / "factors_cell_summary.csv").set_index("outcome")
    for ax, kind in zip(axes, ("abs", "share")):
        t = s[s.outcome == kind].head(12)[::-1]
        cols = [ORANGE if d < 0 else BLUE for d in t.direction_corr]
        ax.barh([labels.get(k, k.replace("_", " ")) for k in t.characteristic], t.mean_abs_shap, color=cols)
        ax.set_title(f"{'Absolute' if kind == 'abs' else 'Share of citywide'} (spatial-CV R2 = "
                     f"{summ.loc[kind, 'rf_spatial_cv_r2']:.2f}: weak out-of-area prediction)", fontsize=9.5)
        ax.set_xlabel("Mean |SHAP| (log ratio of heavy-rain effect)")
    fig.suptitle("What distinguishes cells that lose more vacant taxis in heavy rain (orange: higher value goes with a bigger "
                 "loss; blue: with a smaller loss)",
                 x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "factors_shap", "Sources: data.gov.sg taxi availability, NEA rainfall, URA MP2019, HDB, Census 2020, OSM, "
         "LTA. Random forest on 374 cells, spatial block CV; associations between places and rain effects.")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["chars", "cell", "panel", "charts"])
    a = ap.parse_args()
    {"chars": part_chars, "cell": part_cell, "panel": part_panel, "charts": charts}[a.part]()


if __name__ == "__main__":
    main()
