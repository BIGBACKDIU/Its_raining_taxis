"""Step 11: road network, drive-time matrices and rider-centric availability (pre-registration: decisions 102-104).

Parts:
  graph      build the weighted drive graph and the 500 m land-cell drive-time matrices (dry, rain)
  minutes    per fit-period snapshot: drive minutes from each eligible 1 km cell centre to the nearest vacant taxi
  effects    Poisson FE rain effects on minutes; per-cell named heavy-rain effects; charts
Outputs: data/interim/drive_* (not in git), outputs/tables/minutes_*.csv, figures minutes_*.
Usage: .venv/bin/python -m analysis.11_roads --part graph | minutes | effects
"""
from __future__ import annotations

import argparse
import importlib
import time

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import dijkstra

from analysis import geo
from analysis.common import FIT, INTERIM, RAW, SEED, TABLES, save, style
from pipeline.grid import cell_ids, coarsen, to_xy

SPEEDS = {"motorway": 80, "trunk": 70, "primary": 60, "secondary": 50, "tertiary": 40, "unclassified": 30,
          "residential": 30, "service": 20, "living_street": 20}
DRY_FACTOR, RAIN_FACTOR = 1.25, 1.25
FLOOR_MIN = 0.5


def edge_speed(hw, maxspeed):
    try:
        ms = maxspeed[0] if isinstance(maxspeed, list) else maxspeed
        v = float(str(ms).split()[0])
        if 5 <= v <= 120:
            return v
    except (TypeError, ValueError):
        pass
    h = hw[0] if isinstance(hw, list) else hw
    h = str(h)
    if h.endswith("_link"):
        return 40
    return SPEEDS.get(h, 30)


def build_graph():
    """Weighted drive graph from the parsed Geofabrik extract (analysis/prep_osm.py), largest strongly connected
    component. Edge weight = minutes at the class / maxspeed speed x DRY_FACTOR."""
    from scipy.sparse.csgraph import connected_components
    nodes = pd.read_parquet(geo.P2 / "osm_drive_nodes.parquet")
    e = pd.read_parquet(geo.P2 / "osm_drive_edges.parquet")
    idx = pd.Series(np.arange(len(nodes)), index=nodes.node.values)
    r, c = idx.reindex(e.u.values).values, idx.reindex(e.v.values).values
    sp = np.array([edge_speed(h, m) for h, m in zip(e.highway.values, e.maxspeed.values)], float)
    tt = e.length_m.values / (sp * 1000 / 60) * DRY_FACTOR
    df = pd.DataFrame({"r": r, "c": c, "t": tt}).groupby(["r", "c"]).t.min().reset_index()
    n = len(nodes)
    A = sparse.csr_matrix((df.t.values, (df.r.values, df.c.values)), shape=(n, n))
    ncomp, lab = connected_components(A, directed=True, connection="strong")
    keep = lab == np.bincount(lab).argmax()
    kidx = np.flatnonzero(keep)
    A = A[kidx][:, kidx]
    edges = e.assign(minutes=tt, speed_kmh=sp)
    return A, nodes.lon.values[kidx], nodes.lat.values[kidx], edges


def part_graph():
    t0 = time.time()
    A, lon, lat, edges = build_graph()
    nx_, ny_ = to_xy(lon, lat)
    from scipy.spatial import cKDTree
    tree = cKDTree(np.c_[nx_, ny_])
    lc5 = geo.land_cells(500)[["cell", "lon", "lat"]].reset_index(drop=True)
    x, y = to_xy(lc5.lon.values, lc5.lat.values)
    snap_d, node = tree.query(np.c_[x, y])
    lc5["node"], lc5["snap_m"] = node, snap_d
    lc1 = pd.read_parquet(INTERIM / "cells.parquet")
    lc1 = lc1[lc1.eligible].sort_values("cell").reset_index(drop=True)
    x1, y1 = to_xy(lc1.lon.values, lc1.lat.values)
    d1, n1 = tree.query(np.c_[x1, y1])
    lc1["node"], lc1["snap_m"] = n1, d1
    # snapping distance at 25 km/h on foot-to-road is added as access time (both ends)
    acc5 = lc5.snap_m.values / (25000 / 60)
    acc1 = lc1.snap_m.values / (25000 / 60)
    print("graph nodes", A.shape[0], "500 m land cells", len(lc5), f"{time.time() - t0:.0f}s", flush=True)
    def dist(src, dst, chunk=150):
        out = np.empty((len(src), len(dst)), "float32")
        for a in range(0, len(src), chunk):
            out[a:a + chunk] = dijkstra(A, directed=True, indices=src[a:a + chunk])[:, dst]
        return out

    D55 = dist(lc5.node.values, lc5.node.values) + acc5[:, None] + acc5[None, :]
    D15 = dist(lc1.node.values, lc5.node.values) + acc1[:, None] + acc5[None, :]
    np.save(INTERIM / "drive_500x500_dry.npy", D55.astype("float32"))
    np.save(INTERIM / "drive_500x500_rain.npy", (D55 * RAIN_FACTOR).astype("float32"))
    np.save(INTERIM / "drive_1kmelig_to_500_dry.npy", D15.astype("float32"))
    lc5.to_csv(INTERIM / "drive_cells500.csv", index=False)
    lc1[["cell", "node", "snap_m"]].to_csv(INTERIM / "drive_cells1km_eligible.csv", index=False)
    edges.to_parquet(INTERIM / "drive_edges.parquet", index=False)
    finite = np.isfinite(D55)
    s = {"nodes": A.shape[0], "edges": A.nnz, "cells500": len(lc5), "unreachable_share": float(1 - finite.mean()),
         "median_snap_m": float(np.median(lc5.snap_m)), "median_minutes_500x500": float(np.median(D55[finite])),
         "seconds": round(time.time() - t0)}
    pd.Series(s).to_csv(TABLES / "roads_graph_summary.csv")
    print(s, flush=True)


def part_minutes():
    lc5 = pd.read_csv(INTERIM / "drive_cells500.csv")
    lc1 = pd.read_csv(INTERIM / "drive_cells1km_eligible.csv")
    D = np.load(INTERIM / "drive_1kmelig_to_500_dry.npy")
    pos5 = {c: i for i, c in enumerate(lc5.cell)}
    from scipy.spatial import cKDTree
    from pipeline.grid import cell_centre
    x5, y5 = to_xy(lc5.lon.values, lc5.lat.values)
    tree5 = cKDTree(np.c_[x5, y5])
    sf = pd.read_csv(INTERIM / "snapshot_flags.csv.gz", parse_dates=["req_ts"])
    sf = sf[(sf.status == "ok") & ~sf.offset_bad & sf.req_ts.dt.minute.isin([0, 30])
            & (sf.req_ts >= FIT[0]) & (sf.req_ts <= FIT[1])]
    remap = {}
    rows_ts, rows_min = [], []
    for month, g in sf.groupby("month"):
        z = np.load(RAW / "taxi" / f"{month}_cells500.npz")
        keep = np.isin(z["snap"], g.snap.values)
        snaps, cells, n = z["snap"][keep], z["cell"][keep], z["n"][keep]
        for c in np.unique(cells):
            if c not in remap:
                if c in pos5:
                    remap[c] = pos5[c]
                else:
                    lon, lat = cell_centre(np.array([c]), 500)
                    xx, yy = to_xy(lon, lat)
                    remap[c] = int(tree5.query(np.c_[xx, yy])[1][0])
        col = np.array([remap[c] for c in cells])
        ts = g.set_index("snap").req_ts
        order = np.argsort(snaps, kind="stable")
        snaps, col, n = snaps[order], col[order], n[order]
        bounds = np.searchsorted(snaps, g.snap.values), np.searchsorted(snaps, g.snap.values, side="right")
        for sp, a, b in zip(g.snap.values, *bounds):
            occ = np.unique(col[a:b][n[a:b] > 0])
            if len(occ) == 0:
                continue
            rows_ts.append(ts[sp])
            rows_min.append(np.maximum(D[:, occ].min(1), FLOOR_MIN))
        print(month, flush=True)
    M = np.vstack(rows_min).astype("float32")
    out = [pd.DataFrame({"ts": np.repeat(np.array(rows_ts, dtype="datetime64[ns]"), len(lc1)),
                         "cell": np.tile(lc1.cell.values, len(rows_ts)), "minutes": M.ravel()})]
    res = pd.concat(out, ignore_index=True)
    res.to_parquet(INTERIM / "minutes_to_taxi_fit.parquet", index=False)
    print("rows", len(res), "median minutes", float(res.minutes.median()), flush=True)


def part_effects():
    from analysis.fepois_hd import fepois, pct
    from analysis.common import load_panel
    style()
    E = importlib.import_module("analysis.03_effects")
    mins = pd.read_parquet(INTERIM / "minutes_to_taxi_fit.parquet")
    p = E.load_fit(columns=E.COLS)
    s = E.sample(p)
    p = p[s].reset_index(drop=True)
    p = p.merge(mins, on=["ts", "cell"], how="inner")
    X, fe_abs, _, day = E.design(p)
    rows = []
    for name, off in (("minutes, main", None), ("minutes, with log(citywide) as regressor", "cw")):
        if off is None:
            r = fepois(p.minutes.values, X, E.REGS, fe_abs, day)
        else:
            X2 = np.column_stack([X, np.log(p.citywide.values.astype(float))]).astype("float32")
            r = fepois(p.minutes.values, X2, E.REGS + ["log_citywide"], fe_abs, day)
        r = pct(r)
        r.insert(0, "model", name)
        r["n"] = r.attrs["n"]
        r.attrs = {}
        rows.append(r)
        print(name, r[["pct", "pct_lo", "pct_hi"]].round(2).to_string(), flush=True)
    t = pd.concat(rows)
    t.index.name = "term"
    t.to_csv(TABLES / "minutes_effects.csv", float_format="%.5f")
    # per-cell named effects: ratio of minutes in heavy rain to the no-rain model for minutes
    inf = importlib.import_module("analysis.04_inference")
    hm = p.how.values.astype(np.int32) * 100 + p.month.values
    ymr = p.ym.values.astype(np.int64) * 100 + p.regime_id.values
    dry = (p.mmh.values == 0) & (p.mmh_lag1.values == 0) & (p.mmh_lag2.values == 0)
    groups = [p.cell.values, hm, ymr]
    codes, eff = inf.ipf_poisson(p.minutes.values[dry].astype(float), [g[dry] for g in groups])
    pred = np.zeros(len(p))
    for g, c, e in zip(groups, codes, eff):
        lev = pd.Series(np.arange(c.max() + 1), index=pd.unique(g[dry]))
        ix = pd.Series(g).map(lev).values
        pred += np.where(np.isnan(ix), np.nan, e[np.nan_to_num(ix).astype(int)])
    p["m0"] = np.exp(pred)
    h = p[(p.rain_band == 3) & np.isfinite(p.m0)]
    days = np.sort(h.ts.dt.normalize().unique())
    di = np.searchsorted(days, h.ts.dt.normalize().values)
    cc, cl = pd.factorize(h.cell)
    Mo, Me = np.zeros((len(days), len(cl))), np.zeros((len(days), len(cl)))
    np.add.at(Mo, (di, cc), h.minutes.values)
    np.add.at(Me, (di, cc), h.m0.values)
    W = np.random.default_rng(SEED).multinomial(len(days), np.full(len(days), 1 / len(days)), size=1000).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        b = (W @ Mo) / (W @ Me) - 1
    names = pd.read_csv(TABLES / "names_cells.csv")
    c = pd.DataFrame({"cell": cl, "heavy_rows": np.bincount(cc, minlength=len(cl)),
                      "minutes_heavy": Mo.sum(0) / np.bincount(cc, minlength=len(cl)),
                      "minutes_expected": Me.sum(0) / np.bincount(cc, minlength=len(cl)),
                      "pct": 100 * (Mo.sum(0) / Me.sum(0) - 1), "lo": 100 * np.nanquantile(b, 0.025, 0),
                      "hi": 100 * np.nanquantile(b, 0.975, 0)})
    c["extra_minutes"] = c.minutes_heavy - c.minutes_expected
    c = c.merge(names[["cell", "planning_area", "subzone", "nearest_mrt", "landmarks", "place", "lon", "lat"]], on="cell")
    c = c[c.heavy_rows >= 100].sort_values("extra_minutes", ascending=False)
    c.insert(0, "rank", np.arange(1, len(c) + 1))
    c.to_csv(TABLES / "minutes_cells_named.csv", index=False, float_format="%.3f")
    print(c.head(15)[["rank", "planning_area", "subzone", "landmarks", "minutes_expected", "minutes_heavy",
                      "extra_minutes", "pct", "lo", "hi"]].round(2).to_string(index=False))
    charts(c, p)


def charts(c, p):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    from analysis.common import BLUE_DARK, ORANGE
    N = importlib.import_module("analysis.10_names")
    d02 = importlib.import_module("analysis.02_describe")
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.2))
    blues = LinearSegmentedColormap.from_list("b", ["#0d2f5c", "#2a78d6", "#a9c9ef", "#fbe3d6", ORANGE, "#8a2f10"])
    from matplotlib.colors import BoundaryNorm
    dry = p[(p.mmh == 0) & (p.mmh_lag1 == 0) & (p.mmh_lag2 == 0)].groupby("cell").minutes.median()
    names = pd.read_csv(TABLES / "names_cells.csv").set_index("cell")
    norm = BoundaryNorm([0, 1, 2, 3, 4, 6, 8, 12], blues.N, extend="max")
    d02.draw_base(axes[0])
    N.draw_cells(axes[0], dry.index.values, dry.values, blues, norm)
    lab = names.loc[dry.sort_values(ascending=False).index[:10]].assign(short=lambda d: d.place)
    N.label(axes[0], lab.reset_index(), "short", 10)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=blues), ax=axes[0], orientation="horizontal", fraction=0.05,
                 pad=0.02, label="Median drive minutes to the nearest vacant taxi (dry, modelled road times)")
    axes[0].set_title("Dry weather: how far the nearest vacant taxi is", fontsize=9.5)
    div = LinearSegmentedColormap.from_list("d", [BLUE_DARK, "#7fb0e8", "#f2f1ed", ORANGE, "#8a2f10"])
    norm2 = TwoSlopeNorm(vcenter=0, vmin=-20, vmax=60)
    d02.draw_base(axes[1])
    N.draw_cells(axes[1], c.cell.values, c.pct.clip(-20, 60).values, div, norm2)
    cl = c[c.presentable] if "presentable" in c else c
    N.label(axes[1], cl.assign(short=cl.place), "short", 10)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm2, cmap=div), ax=axes[1], orientation="horizontal", fraction=0.05,
                 pad=0.02, label="% longer drive to the nearest vacant taxi in heavy rain (vs no-rain model)")
    axes[1].set_title("Heavy rain: where the nearest vacant taxi is furthest away (labels: 10 most extra minutes, "
                      ">= 4 expected taxis, FDR q < 0.10)",
                      fontsize=9.5)
    fig.tight_layout()
    save(fig, "minutes_to_taxi_maps", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, OpenStreetMap roads "
         "(modelled speeds). Apr 2022 - Mar 2025. Association, not cause.")
    plt.close(fig)


def part_names():
    """Re-attach the current step-10 names to the per-cell table and redraw the maps (no re-estimation)."""
    style()
    E = importlib.import_module("analysis.03_effects")
    c = pd.read_csv(TABLES / "minutes_cells_named.csv")
    names = pd.read_csv(TABLES / "names_cells.csv")
    keep = ["cell", "planning_area", "subzone", "nearest_mrt", "landmarks", "place", "lon", "lat"]
    c = c.drop(columns=[k for k in keep[1:] + ["expected_vacant_heavy", "p", "q", "presentable"] if k in c])
    c = c.merge(names[keep], on="cell").sort_values("rank")
    # presentation filter (decision 133): >= 4 expected vacant taxis in heavy rain and BH q < 0.10; p from the
    # day-bootstrap CI on the log scale (normal approximation)
    from scipy.stats import norm
    N10 = importlib.import_module("analysis.10_names")
    se = (np.log1p(c.hi / 100) - np.log1p(c.lo / 100)) / 3.92
    c["p"] = 2 * norm.sf(np.abs(np.log1p(c.pct / 100) / se))
    c["q"] = N10.bh(c.p.values)
    ev = pd.read_csv(TABLES / "cell_rain_effects.csv").set_index("cell").expected_vacant_heavy
    c["expected_vacant_heavy"] = c.cell.map(ev)
    c["presentable"] = (c.expected_vacant_heavy >= 4) & (c.q < 0.10)
    c.to_csv(TABLES / "minutes_cells_named.csv", index=False, float_format="%.3f")
    mins = pd.read_parquet(INTERIM / "minutes_to_taxi_fit.parquet")
    p = E.load_fit(columns=["ts", "cell", "mmh", "mmh_lag1", "mmh_lag2", "drop_main", "rain_band"])
    p = p[E.sample(p)].merge(mins, on=["ts", "cell"], how="inner")
    charts(c, p)
    print(c[c.presentable].head(10)[["rank", "planning_area", "subzone", "extra_minutes", "pct", "lo", "hi"]]
          .to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["graph", "minutes", "effects", "names"])
    a = ap.parse_args()
    {"graph": part_graph, "minutes": part_minutes, "effects": part_effects, "names": part_names}[a.part]()


if __name__ == "__main__":
    main()
