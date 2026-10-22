"""Step 1: build the cell x snapshot panel (HANDOFF section 6, step 1).

Unit: 1 km cell x snapshot. The main panel (grid 30) uses :00 and :30 snapshots for all five years; the
fine panel (grid 15, --grid 15) uses every 15-minute snapshot from Oct 2024.

Pass 1  cells: eligibility (mean vacant over fit-period snapshots >= 0.5) and cell traits
Pass 2  per year: vacant counts (500 m -> 1 km, zeros filled for eligible cells), citywide count, flags,
        rain before t (rule 3), forecasts as issued (rule 4), time features
Pass 3  baseline: Poisson vacant ~ 1 | cell + how^month + regime fitted on fit-period rows (main sample),
        solved exactly by iterative proportional fitting on aggregated counts; regimes outside the fit
        period get their own level with the cell and how^month effects held fixed. Then deficit, low,
        zero, severity and lags.

Every row carries the regime and the exclusion flags so every model can run with and without them:
  day_missing, spell, feed_outage, glitch, drop_main (= any of these), drop_robust (robustness set: only
  missing days, spells other than 26 Feb - 1 Mar 2023, and glitches).

Outputs: data/interim/cells.parquet, data/interim/panel{grid}_{year}.parquet (not in git), panel checks in
outputs/tables/panel_checks.csv and panel_handcheck.csv.

Usage: .venv/bin/python -m analysis.01_panel [--grid 30|15]
"""
from __future__ import annotations

import argparse
import json
import re

import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath
from scipy.spatial import cKDTree

from analysis.common import (BASELINE_MIN, CENTRAL_AREA, FIT, INTERIM, LOW_D, RAW, SEED, STATIC, TABLES,
                             rain_band)
from pipeline.grid import cell_centre, coarsen, split_id, to_xy

START = pd.Timestamp("2021-10-01")
BIN = 15                                   # rain bins in minutes; bin k covers (START + 15(k-1), START + 15k]
FC_MAX_AGE_MIN = 180
CELL_SIZE = 1000                           # 500 for the robustness grid (--size 500)
SUFFIX = ""                                # "_500m" for the robustness grid
NEAR_KM, RING_KM = 2.0, 5.0                # neighbouring-rain radii
FC_CODES = {0: "fair or cloudy", 1: "light rain", 2: "showers or moderate rain", 3: "thundery or heavy"}


# ----------------------------------------------------------------------------- helpers
def snapshots(grid: int) -> pd.DataFrame:
    sf = pd.read_csv(INTERIM / "snapshot_flags.csv.gz", parse_dates=["req_ts", "act_ts"])
    sf = sf[(sf.status == "ok") & ~sf.offset_bad]
    if grid == 30:
        sf = sf[sf.req_ts.dt.minute.isin([0, 30])]
    else:
        sf = sf[sf.req_ts >= pd.Timestamp("2024-10-01")]
    return sf[["month", "snap", "req_ts", "n_points", "glitch"]].rename(columns={"req_ts": "ts", "n_points": "citywide"})


def day_flags() -> pd.DataFrame:
    d = pd.read_csv(INTERIM / "day_flags.csv", parse_dates=["date"]).set_index("date")
    return pd.DataFrame({
        "regime_id": d.regime_id.astype("int8"), "regime": d.regime,
        "day_missing": ~d.usable.astype(bool), "spell": d.regime.eq("spell"),
        "feed_outage": d.feed_outage.astype(bool), "exclude_main": d.exclude_main.astype(bool),
        "exclude_robust": d.exclude_robust.astype(bool), "covid": d.covid.astype(bool)})


def month_cells(month: str, keep_snaps) -> pd.DataFrame:
    z = np.load(RAW / "taxi" / f"{month}_cells500.npz")
    cell = coarsen(z["cell"]) if CELL_SIZE == 1000 else z["cell"]
    df = pd.DataFrame({"snap": z["snap"], "cell": cell, "n": z["n"].astype("int32")})
    df = df[df.snap.isin(keep_snaps)]
    return df.groupby(["snap", "cell"], as_index=False).n.sum()


def in_polygon_name(lon, lat, polys: dict) -> np.ndarray:
    out = np.full(len(lon), "", dtype=object)
    pts = np.c_[lon, lat]
    for name, geom in polys.items():
        # geom: list of polygons, each a list of rings (first = outer)
        for poly in geom:
            rings = poly if isinstance(poly[0][0], list) else [poly]
            inside = MplPath(np.asarray(rings[0])).contains_points(pts)
            for hole in rings[1:]:
                inside &= ~MplPath(np.asarray(hole)).contains_points(pts)
            out[inside & (out == "")] = name
    return out


# ----------------------------------------------------------------------------- pass 1: cells
def build_cells(sn: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    fit = sn[(sn.ts >= FIT[0]) & (sn.ts <= FIT[1])].copy()
    fit = fit[~fit.glitch & ~fit.ts.dt.normalize().map(flags.exclude_main).astype(bool)]
    tot, n_snap = {}, 0
    for month, g in fit.groupby("month"):
        mc = month_cells(month, set(g.snap))
        for c, v in mc.groupby("cell").n.sum().items():
            tot[c] = tot.get(c, 0) + v
        n_snap += len(g)
    c = pd.DataFrame({"cell": list(tot), "vacant_sum": list(tot.values())})
    c["mean_fit"] = c.vacant_sum / n_snap
    c["eligible"] = c.mean_fit >= 0.5
    c["lon"], c["lat"] = cell_centre(c.cell, CELL_SIZE)
    c["cx"], c["cy"] = split_id(c.cell)
    x, y = to_xy(c.lon, c.lat)
    # MRT/LRT exits (stations as fallback for stations without exits)
    mrt = json.load(open(STATIC / "sg_mrt.json"))
    ex = np.array([[e[3], e[2]] for e in mrt["exits"]] + [[s[4], s[3]] for s in mrt["stations"]])
    ex_x, ex_y = to_xy(ex[:, 0], ex[:, 1])
    c["dist_mrt_m"] = cKDTree(np.c_[ex_x, ex_y]).query(np.c_[x, y])[0].round(0)
    c["mrt_exits_in_cell"] = 0
    ec = _cell500(ex[:, 0], ex[:, 1])
    exc = pd.Series(coarsen(ec) if CELL_SIZE == 1000 else ec).value_counts()
    c["mrt_exits_in_cell"] = c.cell.map(exc).fillna(0).astype(int)
    # taxi stops/stands within 300 m of the cell square
    ts = pd.read_csv(STATIC / "lta_taxi_stops.csv")
    sx, sy = to_xy(ts.lon, ts.lat)
    x0, y0 = c.cx.values * CELL_SIZE, c.cy.values * CELL_SIZE
    dx = np.maximum(0, np.maximum(x0[:, None] - sx[None, :], sx[None, :] - (x0[:, None] + CELL_SIZE)))
    dy = np.maximum(0, np.maximum(y0[:, None] - sy[None, :], sy[None, :] - (y0[:, None] + CELL_SIZE)))
    c["taxi_stands_300m"] = (np.hypot(dx, dy) <= 300).sum(1)
    pa = json.load(open(STATIC / "sg_map.json"))["planning_areas"]
    c["planning_area"] = in_polygon_name(c.lon.values, c.lat.values, pa)
    miss = c.planning_area == ""
    if miss.any():                         # cell centre at sea or on a boundary: nearest area by vertex
        verts = [(n, p) for n, g in pa.items() for poly in g for p in (poly[0] if isinstance(poly[0][0], list) else poly)]
        vx, vy = to_xy([p[0] for _, p in verts], [p[1] for _, p in verts])
        _, idx = cKDTree(np.c_[vx, vy]).query(np.c_[x[miss], y[miss]])
        c.loc[miss, "planning_area"] = [verts[i][0] for i in idx]
    c["city_centre"] = c.planning_area.isin(CENTRAL_AREA)
    return c.sort_values("cell").reset_index(drop=True)


def _cell500(lon, lat):
    from pipeline.grid import cell_ids
    return cell_ids(lon, lat, 500)


# ----------------------------------------------------------------------------- rain
class Rain:
    """15-minute rain bins per gauge, with working-gauge masks per day."""

    def __init__(self):
        gd = pd.read_csv(INTERIM / "gauge_day_flags.csv.gz", parse_dates=["date"])
        st = pd.concat([pd.read_csv(f) for f in sorted((RAW / "rain").glob("*_stations.csv.gz"))])
        loc = st.groupby("station_id")[["lat", "lon"]].median()
        self.gauges = sorted(set(gd.station_id) & set(loc.index))
        self.gi = {g: i for i, g in enumerate(self.gauges)}
        self.gx, self.gy = to_xy(loc.loc[self.gauges].lon.values, loc.loc[self.gauges].lat.values)
        self.days = pd.date_range(START, "2026-09-30")
        self.n_bins = len(self.days) * 96 + 1
        work = gd[gd.working & gd.station_id.isin(self.gi)]
        self.working = np.zeros((len(self.days), len(self.gauges)), bool)
        self.working[(work.date - START).dt.days.values, work.station_id.map(self.gi).values] = True
        B = np.zeros((len(self.gauges), self.n_bins), "float32")
        for f in sorted((RAW / "rain").glob("*_readings.csv.gz")):
            r = pd.read_csv(f, parse_dates=["ts"])
            r = r[r.station_id.isin(self.gi) & (r.ts > START)]
            k = np.ceil((r.ts - START).dt.total_seconds().values / 60 / BIN).astype(int)
            np.add.at(B, (r.station_id.map(self.gi).values, k), r.mm.values.astype("float32"))
        # bins of a gauge-day that is not working are missing
        day_of_bin = (np.arange(self.n_bins) - 1).clip(0) // 96
        B[~self.working[day_of_bin].T] = np.nan
        self.B = B
        # run lengths: wet duration and minutes since last rain, per gauge, in bins
        wet = np.nan_to_num(B) > 0
        self.wet_run = _run_length(wet)
        self.dry_run = _run_length(~wet)

    def nearest(self, x, y, day_idx, k=1):
        """Indices of the k nearest working gauges for each point on each day: (days, points, k)."""
        out = np.full((len(day_idx), len(x), k), -1, "int32")
        for i, d in enumerate(day_idx):
            w = np.flatnonzero(self.working[d])
            if len(w) >= k:
                _, j = cKDTree(np.c_[self.gx[w], self.gy[w]]).query(np.c_[x, y], k=k)
                out[i] = w[j.reshape(len(x), k)]
        return out


def _run_length(mask: np.ndarray) -> np.ndarray:
    """Length of the run of True ending at each position, along axis 1 (int16, capped)."""
    out = np.zeros(mask.shape, "int16")
    run = np.zeros(mask.shape[0], "int32")
    for k in range(mask.shape[1]):
        run = np.where(mask[:, k], np.minimum(run + 1, 32000), 0)
        out[:, k] = run
    return out


def spatial_rain(rain: "Rain", k: np.ndarray, cells: pd.DataFrame, allc: pd.DataFrame):
    """Neighbouring rain for each (snapshot, eligible cell), using only rain up to t.

    Every 1 km cell seen in the feed (eligible or not) gets the rain at its nearest working gauge; then for each
    eligible cell: mean mm/h over (t-30, t] in cells within 2 km (centre distance, cell itself excluded) and in
    the 2-5 km ring; wet5_min = minutes since rain first appeared within 5 km in the current spell (0 if no rain
    within 5 km now); dry5_min = minutes since rain was last seen within 5 km (capped at 1440); island-wide
    share of working gauges with rain.
    """
    ax, ay = to_xy(allc.lon.values, allc.lat.values)
    ex, ey = to_xy(cells.lon.values, cells.lat.values)
    d = np.hypot(ex[:, None] - ax[None, :], ey[:, None] - ay[None, :])
    W2 = ((d > 0) & (d <= NEAR_KM * 1000)).astype("float32")
    WR = ((d > NEAR_KM * 1000) & (d <= RING_KM * 1000)).astype("float32")
    A5 = (d <= RING_KM * 1000).astype("float32")
    k0, k1 = max(1, int(k.min()) - 97), int(k.max())
    bins = np.arange(k0, k1 + 1)
    bday = ((bins - 1).clip(0) // 96)
    udays = np.unique(bday)
    near = rain.nearest(ax, ay, udays, k=1)[:, :, 0]                       # (days, all cells)
    g = near[np.searchsorted(udays, bday)]                                  # (bins, all cells)
    CB = rain.B[g.clip(0), bins[:, None]]
    CB[g < 0] = np.nan
    wet = np.nan_to_num(CB) > 0
    any5 = (wet.astype("float32") @ A5.T) > 0                              # (bins, eligible)
    wet5 = _run_length(any5.T)                                              # (eligible, bins)
    dry5 = _run_length(~any5.T)
    kk = k - k0
    mm = 2 * (CB[kk] + CB[kk - 1])                                          # (snaps, all cells) mm/h
    ok = ~np.isnan(mm)
    m0 = np.nan_to_num(mm)

    def wmean(W):
        num, den = m0 @ W.T, ok.astype("float32") @ W.T
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den > 0, num / den, np.nan).astype("float32")

    Bk = rain.B[:, k] + rain.B[:, k - 1]
    with np.errstate(invalid="ignore"):
        share = (np.nansum(Bk > 0, axis=0) / np.sum(~np.isnan(Bk), axis=0)).astype("float32")
    return {"rain_2km": wmean(W2), "rain_ring": wmean(WR),
            "wet5_min": (wet5[:, kk].T.astype("int32") * BIN).astype("int16"),
            "dry5_min": np.minimum(dry5[:, kk].T.astype("int32") * BIN, 1440).astype("int16"),
            "gauges_wet_share": share}


# ----------------------------------------------------------------------------- forecasts
def fc_code(text: pd.Series) -> np.ndarray:
    t = text.fillna("").str.lower()
    return np.select([t.str.contains("thunder|heavy"), t.str.contains("light|passing|drizzle"),
                      t.str.contains("showers|moderate rain|^rain")], [3, 1, 2], 0).astype("int8")


class Forecasts:
    def __init__(self, cells_lonlat):
        fc = pd.concat([pd.read_csv(f, usecols=["issued", "area", "forecast"], parse_dates=["issued"])
                        for f in sorted((RAW / "forecast").glob("*_forecast.csv.gz"))])
        fc = fc.dropna(subset=["issued", "area"]).drop_duplicates(["issued", "area"], keep="last")
        ar = pd.concat([pd.read_csv(f) for f in sorted((RAW / "forecast").glob("*_areas.csv.gz"))])
        ar = ar.dropna().groupby("area")[["lat", "lon"]].median()
        ar = ar[ar.index.isin(fc.area.unique())]
        self.areas = list(ar.index)
        ax, ay = to_xy(ar.lon.values, ar.lat.values)
        cx, cy = to_xy(*cells_lonlat)
        self.cell_area = cKDTree(np.c_[ax, ay]).query(np.c_[cx, cy])[1]
        fc["code"] = fc_code(fc.forecast)
        self.by_area = {a: (g.issued.values, g.code.values) for a, g in fc.sort_values("issued").groupby("area")}
        self.texts = fc.forecast.value_counts()

    def as_issued(self, ts: np.ndarray):
        """Latest forecast issued strictly before each time: code (areas x times) and age in minutes."""
        code = np.full((len(self.areas), len(ts)), -1, "int8")
        age = np.full((len(self.areas), len(ts)), np.nan, "float32")
        for i, a in enumerate(self.areas):
            iss, cod = self.by_area.get(a, (np.array([], "datetime64[ns]"), np.array([], "int8")))
            j = np.searchsorted(iss, ts, "left") - 1
            ok = j >= 0
            ag = np.where(ok, (ts - iss[j.clip(0)]).astype("timedelta64[s]").astype(float) / 60, np.nan)
            ok &= ag <= FC_MAX_AGE_MIN
            code[i, ok] = cod[j[ok]]
            age[i, ok] = ag[ok]
        return code, age


# ----------------------------------------------------------------------------- pass 2: year panels
def build_year(year, sn, flags, cells, rain: Rain, fcs: Forecasts, hol, grid, allc=None):
    s = sn[sn.ts.dt.year == year].sort_values("ts").reset_index(drop=True)
    if s.empty:
        return None
    E = cells.cell.values
    nE = len(E)
    cell_pos = {c: i for i, c in enumerate(E)}
    V = np.zeros((len(s), nE), "int16")
    s_index = {(m, sp): i for i, (m, sp) in enumerate(zip(s.month, s.snap))}
    for month, g in s.groupby("month"):
        mc = month_cells(month, set(g.snap))
        mc = mc[mc.cell.isin(cell_pos)]
        rows = np.array([s_index[(month, sp)] for sp in mc.snap])
        V[rows, mc.cell.map(cell_pos).values] = mc.n.values
    ts = s.ts.values
    date = s.ts.dt.normalize()
    day_idx = (date - START).dt.days.values
    k = ((s.ts - START).dt.total_seconds().values / 60 / BIN).astype(int)      # bin ending at t
    # rain at nearest and 3 nearest working gauges, per day
    cx, cy = to_xy(cells.lon.values, cells.lat.values)
    udays, inv = np.unique(day_idx, return_inverse=True)
    near3 = rain.nearest(cx, cy, udays, k=3)[inv]                                # (snaps, cells, 3)

    def window(gauge_idx, k_end, nbins=2):
        """mm/h over the nbins bins ending at k_end (2 bins = 30 min), for gauge indices (snaps, cells)."""
        tot = np.zeros(gauge_idx.shape, "float32")
        for b in range(nbins):
            kk = np.broadcast_to((k_end - b)[:, None], gauge_idx.shape)
            v = rain.B[gauge_idx.clip(0), kk]
            tot += v
        tot[gauge_idx < 0] = np.nan
        return tot * (60 / (BIN * nbins))

    g1 = near3[:, :, 0]
    mmh = window(g1, k)
    lag1 = window(g1, k - 2)
    lag2 = window(g1, k - 4)
    mmh3 = np.nanmean(np.stack([window(near3[:, :, j], k) for j in range(3)]), axis=0)
    wet_min = rain.wet_run[g1.clip(0), np.broadcast_to(k[:, None], g1.shape)].astype("int32") * BIN
    dry_min = np.minimum(rain.dry_run[g1.clip(0), np.broadcast_to(k[:, None], g1.shape)].astype("int32") * BIN, 1440)
    # island mean over all working gauges
    Bk = rain.B[:, k] + rain.B[:, k - 1]
    island = np.nanmean(Bk, axis=0) * 2
    # forecasts as issued
    code, age = fcs.as_issued(ts)
    fca = fcs.cell_area
    f = flags.reindex(date).reset_index(drop=True)
    how = (s.ts.dt.day_of_week * 48 + s.ts.dt.hour * 2 + s.ts.dt.minute // 30).values
    hd = hol.reindex(date)
    public = hd.public.fillna(False).values.astype(bool)
    school = hd.school.fillna(False).values.astype(bool)
    wkend = s.ts.dt.day_of_week.values >= 5
    T = len(s)

    def rep(a):        # snapshot-level -> rows (snapshot-major order)
        return np.repeat(np.asarray(a), nE)

    out = pd.DataFrame({
        "ts": rep(ts), "cell": np.tile(E, T).astype("int32"), "vacant": V.ravel(),
        "citywide": rep(s.citywide.values).astype("int16"),
        "regime_id": rep(f.regime_id.values).astype("int8"),
        "regime": pd.Categorical(rep(f.regime.values)),
        "day_missing": rep(f.day_missing.values), "spell": rep(f.spell.values),
        "feed_outage": rep(f.feed_outage.values), "glitch": rep(s.glitch.values),
        "covid": rep(f.covid.values),
    })
    out["drop_main"] = rep((f.exclude_main | s.glitch).values)
    out["drop_robust"] = rep((f.exclude_robust | s.glitch).values)
    out["mmh"] = mmh.ravel()
    out["rain_band"] = rain_band(out.mmh)
    out["mmh_lag1"] = lag1.ravel()
    out["mmh_lag2"] = lag2.ravel()
    out["mmh_3g"] = mmh3.ravel().astype("float32")
    out["wet_min"] = wet_min.ravel().astype("int16")
    out["dry_min"] = dry_min.ravel().astype("int16")
    out["mmh_island"] = rep(island).astype("float32")
    if allc is not None:
        sp = spatial_rain(rain, k, cells, allc)
        for c in ("rain_2km", "rain_ring", "wet5_min", "dry5_min"):
            out[c] = sp[c].ravel()
        out["gauges_wet_share"] = rep(sp["gauges_wet_share"])
    out["fc_code"] = code[fca][:, :].T.ravel()
    out["fc_age_min"] = age[fca].T.ravel()
    out["how"] = rep(how).astype("int16")
    out["hod"] = (out.how % 48).astype("int8")
    out["dow"] = (out.how // 48).astype("int8")
    out["month"] = rep(s.ts.dt.month.values).astype("int8")
    out["ym"] = rep((s.ts.dt.year * 100 + s.ts.dt.month).values).astype("int32")
    out["public_holiday"] = rep(public)
    out["school_holiday"] = rep(school)
    out["daytype"] = rep(np.where(public, 2, np.where(wkend, 1, 0))).astype("int8")   # 0 weekday 1 weekend 2 holiday
    out["date"] = rep(date.values)
    return out


# ----------------------------------------------------------------------------- pass 3: baseline
def fit_baseline(years, grid, n_iter=200, tol=1e-10):
    agg = []
    for y in years:
        p = pd.read_parquet(INTERIM / f"panel{grid}{SUFFIX}_{y}.parquet",
                            columns=["ts", "cell", "vacant", "how", "month", "regime_id", "drop_main"])
        p = p[~p.drop_main].assign(infit=lambda d: (d.ts >= FIT[0]) & (d.ts <= FIT[1]))
        agg.append(p.groupby(["cell", "how", "month", "regime_id", "infit"], observed=True)
                   .vacant.agg(y="sum", n="size").reset_index())
    a = pd.concat(agg).groupby(["cell", "how", "month", "regime_id", "infit"], as_index=False).sum()
    a["hm"] = a.how.astype(int) * 100 + a.month.astype(int)
    fit = a[a.infit].copy()                     # only fit-period rows enter the estimation
    a = a.groupby(["cell", "hm", "regime_id"], as_index=False)[["y", "n"]].sum()
    # Poisson MLE with three sets of main effects by iterative proportional fitting
    ci, cu = pd.factorize(fit.cell)
    hi, hu = pd.factorize(fit.hm)
    ri, ru = pd.factorize(fit.regime_id)
    yv, nv = fit.y.values, fit.n.values
    A, H, R = np.zeros(len(cu)), np.zeros(len(hu)), np.zeros(len(ru))
    for it in range(n_iter):
        old = np.r_[A, H, R].copy()
        for idx, eff in ((ci, A), (hi, H), (ri, R)):
            mu = nv * np.exp(A[ci] + H[hi] + R[ri])
            num = np.bincount(idx, yv, len(eff))
            den = np.bincount(idx, mu, len(eff))
            with np.errstate(divide="ignore"):
                eff += np.log(np.maximum(num, 1e-12) / den)
        R -= R[0]
        if np.max(np.abs(np.r_[A, H, R] - old)) < tol:
            break
    A, H = pd.Series(A, cu), pd.Series(H, hu)
    R = pd.Series(R, ru)
    # regimes without fit-period data: level from all their (main-sample) rows, cell and how^month fixed
    oth = a[~a.regime_id.isin(R.index)]
    if len(oth):
        oth = oth.assign(m0=oth.n * np.exp(oth.cell.map(A).fillna(-np.inf) + oth.hm.map(H).fillna(-np.inf)))
        for r, g in oth.groupby("regime_id"):
            R[r] = np.log(g.y.sum() / g.m0.sum())
    return A, H, R, it


def add_baseline(year, grid, A, H, R):
    f = INTERIM / f"panel{grid}{SUFFIX}_{year}.parquet"
    p = pd.read_parquet(f)
    hm = p.how.astype(int) * 100 + p.month.astype(int)
    eta = p.cell.map(A).values + hm.map(H).values + p.regime_id.map(R).values
    p["baseline"] = np.exp(eta).astype("float32")
    p.loc[p.spell, "baseline"] = np.nan              # spells have no regime level
    p["deficit"] = ((p.baseline - p.vacant) / np.maximum(1, p.baseline)).astype("float32")
    big = p.baseline >= BASELINE_MIN
    p["low"] = pd.array(np.where(big, p.deficit >= LOW_D, pd.NA), dtype="boolean")
    p["low40"] = pd.array(np.where(big, p.deficit >= 0.4, pd.NA), dtype="boolean")
    p["low60"] = pd.array(np.where(big, p.deficit >= 0.6, pd.NA), dtype="boolean")
    p["zero"] = pd.array(np.where(big, p.vacant == 0, pd.NA), dtype="boolean")
    sev = np.select([p.deficit < 0.25, p.deficit < 0.5, p.deficit < 0.75], [0, 1, 2], 3)
    p["severity"] = pd.array(np.where(big, sev, pd.NA), dtype="Int8")
    # lags of vacant within cell (previous slots), using the end of the previous year where needed
    step = pd.Timedelta(minutes=grid)
    prev = INTERIM / f"panel{grid}{SUFFIX}_{year - 1}.parquet"
    if prev.exists():
        tail = pd.read_parquet(prev, columns=["ts", "cell", "vacant"],
                               filters=[("ts", ">=", pd.Timestamp(f"{year}-01-01") - pd.Timedelta(hours=3))])
    else:
        tail = pd.DataFrame(columns=["ts", "cell", "vacant"])
    look = pd.concat([tail, p[["ts", "cell", "vacant"]]]).set_index(["cell", "ts"]).vacant
    for L in (1, 2):
        key = pd.MultiIndex.from_arrays([p.cell, p.ts - L * step])
        p[f"vacant_lag{L}"] = look.reindex(key).values.astype("float32")
    p.to_parquet(f, index=False, compression="zstd")
    return p


# ----------------------------------------------------------------------------- checks
def check_year(p, sn_year, nE):
    n_snap = sn_year.ts.nunique()
    usable = int((~sn_year.glitch).sum())
    return {"rows": len(p), "eligible_cells": nE, "panel_snapshots": n_snap, "usable_snapshots": usable,
            "rows_equal_cells_x_snapshots": len(p) == nE * n_snap,
            "duplicate_keys": int(p.duplicated(["cell", "ts"]).sum()),
            "rows_main_sample": int((~p.drop_main).sum()), "rows_robust_sample": int((~p.drop_robust).sum()),
            "rain_missing_share": round(float(p.mmh.isna().mean()), 5),
            "fc_missing_share": round(float((p.fc_code < 0).mean()), 5)}


def hand_check(grid, cells, n=5, n_wet=3):
    """Recompute vacant, citywide and rain for 5 random rows straight from the raw files, plus 3 extra rows
    drawn from rainy snapshots (random rows are almost always dry, which would not test the rain alignment)."""
    rng = np.random.default_rng(SEED)
    rows = []
    years = [y for y in range(2021, 2027) if (INTERIM / f"panel{grid}{SUFFIX}_{y}.parquet").exists()]
    for i in range(n + n_wet):
        y = int(rng.choice(years))
        p = pd.read_parquet(INTERIM / f"panel{grid}{SUFFIX}_{y}.parquet", columns=["ts", "cell", "vacant", "citywide", "mmh"])
        if i >= n:
            p = p[p.mmh > 0]
        r = p.iloc[int(rng.integers(len(p)))]
        month = r.ts.strftime("%Y-%m")
        sn = pd.read_csv(RAW / "taxi" / f"{month}_snapshots.csv.gz", parse_dates=["req_ts"])
        srow = sn[sn.req_ts == r.ts].iloc[0]
        z = np.load(RAW / "taxi" / f"{month}_cells500.npz")
        zc = coarsen(z["cell"]) if CELL_SIZE == 1000 else z["cell"]
        sel = (z["snap"] == srow.snap) & (zc == r.cell)
        raw_vacant = int(z["n"][sel].sum())
        # rain: nearest working gauge by hand from the raw readings and completeness files
        comp = pd.read_csv(RAW / "rain" / f"{month}_completeness.csv.gz", parse_dates=["date"])
        gd = pd.read_csv(INTERIM / "gauge_day_flags.csv.gz", parse_dates=["date"])
        work = gd[(gd.date == r.ts.normalize()) & gd.working].station_id
        st = pd.read_csv(RAW / "rain" / f"{month}_stations.csv.gz").groupby("station_id")[["lat", "lon"]].median()
        st = st[st.index.isin(work)]
        clon, clat = cell_centre(np.array([r.cell]), CELL_SIZE)
        gx, gy = to_xy(st.lon.values, st.lat.values)
        x0, y0 = to_xy(clon, clat)
        g = st.index[np.argmin(np.hypot(gx - x0, gy - y0))]
        rd = pd.read_csv(RAW / "rain" / f"{month}_readings.csv.gz", parse_dates=["ts"])
        prev_month = (r.ts - pd.Timedelta(minutes=30)).strftime("%Y-%m")
        if prev_month != month:
            rd = pd.concat([rd, pd.read_csv(RAW / "rain" / f"{prev_month}_readings.csv.gz", parse_dates=["ts"])])
        mm = rd[(rd.station_id == g) & (rd.ts > r.ts - pd.Timedelta(minutes=30)) & (rd.ts <= r.ts)].mm.sum()
        rows.append({"draw": "random" if i < n else "rainy", "year": y, "ts": r.ts, "cell": r.cell, "panel_vacant": int(r.vacant), "raw_vacant": raw_vacant,
                     "panel_citywide": int(r.citywide), "raw_citywide": int(srow.n_points), "gauge": g,
                     "panel_mmh": float(r.mmh), "raw_mmh": float(mm * 2),
                     "match": raw_vacant == r.vacant and srow.n_points == r.citywide and abs(mm * 2 - r.mmh) < 1e-4})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", type=int, default=30, choices=[30, 15])
    ap.add_argument("--size", type=int, default=1000, choices=[1000, 500])
    ap.add_argument("--years", type=int, nargs="*", default=None)
    a = ap.parse_args()
    grid = a.grid
    global CELL_SIZE, SUFFIX
    CELL_SIZE, SUFFIX = a.size, ("" if a.size == 1000 else "_500m")
    sn = snapshots(grid)
    flags = day_flags()
    if (grid == 30 and not a.years) or not (INTERIM / f"cells{SUFFIX}.parquet").exists():
        allc = build_cells(sn, flags)
        allc.to_parquet(INTERIM / f"cells{SUFFIX}.parquet", index=False)
    allc = pd.read_parquet(INTERIM / f"cells{SUFFIX}.parquet")
    cells = allc[allc.eligible].reset_index(drop=True)
    print(f"cells seen in fit period: {len(allc)}, eligible: {len(cells)}, excluded: {(~allc.eligible).sum()}")
    h = pd.read_csv(STATIC / "holidays.csv", parse_dates=["date"])
    hol = pd.DataFrame({"public": h[h.kind == "public"].groupby("date").size() > 0,
                        "school": h[h.kind == "school"].groupby("date").size() > 0}).fillna(False)
    rain = Rain()
    fcs = Forecasts((cells.lon.values, cells.lat.values))
    print("forecast texts -> codes:", {t: int(fc_code(pd.Series([t]))[0]) for t in fcs.texts.index})
    years = sorted(sn.ts.dt.year.unique()) if not a.years else a.years
    checks = {}
    for y in years:
        p = build_year(y, sn, flags, cells, rain, fcs, hol, grid, allc)
        p.to_parquet(INTERIM / f"panel{grid}{SUFFIX}_{y}.parquet", index=False, compression="zstd")
        print(y, len(p), "rows", flush=True)
        del p
    A, H, R, it = fit_baseline(years, grid)
    print("baseline IPF iterations:", it, "regime levels:", np.exp(R).round(3).to_dict())
    pd.DataFrame({"regime_id": R.index, "log_level": R.values}).to_csv(TABLES / f"baseline_regime_levels_{grid}{SUFFIX}.csv",
                                                                       index=False, float_format="%.4f")
    for y in years:
        p = add_baseline(y, grid, A, H, R)
        checks[y] = check_year(p, sn[sn.ts.dt.year == y], len(cells))
        checks[y].update({"baseline_ge4_share": round(float((p.baseline >= BASELINE_MIN).mean()), 4),
                          "low_share_main": round(float(p.loc[~p.drop_main, "low"].mean()), 4),
                          "zero_share_main": round(float(p.loc[~p.drop_main, "zero"].mean()), 4)})
        print(y, checks[y], flush=True)
        del p
    ck = pd.DataFrame(checks).T
    ck.index.name = "year"
    ck.to_csv(TABLES / f"panel_checks_{grid}{SUFFIX}.csv")
    hc = hand_check(grid, cells)
    hc.to_csv(TABLES / f"panel_handcheck_{grid}{SUFFIX}.csv", index=False)
    print(ck.to_string())
    print(hc.to_string())


if __name__ == "__main__":
    main()
