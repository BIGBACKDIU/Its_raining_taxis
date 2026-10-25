"""Gauge-only sample selection and right-closed gauge rain for step 23."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.grid import to_xy

TABLES = ROOT / "outputs/tables"
LOCAL = ROOT / "data/interim/s23"
START, END = pd.Timestamp("2022-04-01"), pd.Timestamp("2025-03-31")


class Gauges:
    def __init__(self):
        months = pd.period_range("2022-03", "2025-04", freq="M").astype(str)
        gd = pd.read_csv(ROOT / "data/interim/gauge_day_flags.csv.gz", parse_dates=["date"])
        gd = gd[gd.date.between(START-pd.Timedelta(days=1), END+pd.Timedelta(days=1))]
        stations = pd.concat([pd.read_csv(ROOT / f"data/raw/rain/{m}_stations.csv.gz") for m in months])
        self.loc = stations.groupby("station_id")[["lon", "lat"]].median()
        self.ids = pd.Index(sorted(set(gd.station_id) & set(self.loc.index)))
        self.loc = self.loc.reindex(self.ids)
        self.times = pd.date_range(START-pd.Timedelta(days=1), END+pd.Timedelta(days=1), freq="5min")
        self.work = gd.pivot(index="date", columns="station_id", values="working").reindex(columns=self.ids).fillna(False)
        health = self.work.reindex((self.times-pd.Timedelta(nanoseconds=1)).normalize()).fillna(False).to_numpy(bool)
        B = np.zeros(health.shape, dtype="float32")
        for m in months:
            r = pd.read_csv(ROOT / f"data/raw/rain/{m}_readings.csv.gz", parse_dates=["ts"])
            ti, gi = self.times.get_indexer(r.ts), self.ids.get_indexer(r.station_id)
            use = (ti >= 0) & (gi >= 0)
            # Raw files have one depth per timestamp and gauge.
            B[ti[use], gi[use]] = r.mm.to_numpy(dtype="float32")[use]
        B[~health] = np.nan
        self.B = B
        self.R = pd.DataFrame(B).rolling(6, min_periods=6).sum().to_numpy(dtype="float32")*2
        self.tree_cache = {}

    def wet_cells(self, ts, cell_ids):
        """Rain at nearest working gauge; no end-labelled interval after ts is used."""
        from pipeline.grid import cell_centre
        k = self.times.searchsorted(pd.Timestamp(ts), side="right")-1
        if k < 0 or k >= len(self.times):
            raise ValueError("Rain time outside registered fit sample")
        rain = self.R[k]
        good = np.flatnonzero(np.isfinite(rain))
        if len(good) < 20:
            return np.full(len(cell_ids), False), False
        key = good.tobytes()
        if key not in self.tree_cache:
            xy = np.column_stack(to_xy(self.loc.lon.to_numpy()[good], self.loc.lat.to_numpy()[good]))
            self.tree_cache[key] = cKDTree(xy)
        lon, lat = cell_centre(cell_ids, size=1000)
        _, near = self.tree_cache[key].query(np.column_stack(to_xy(lon, lat)))
        return rain[good[near]] > 0, True


def select():
    g = Gauges()
    # Three dry hours immediately before the first (possibly wet) 30-minute window.
    prior = pd.DataFrame(g.B).rolling(36, min_periods=36).max().shift(6).to_numpy(dtype="float32")
    common = np.isfinite(prior) & np.isfinite(g.R)
    n = common.sum(axis=1)
    changed = common & (prior == 0) & (g.R >= 1)
    share = changed.sum(axis=1)/np.maximum(n, 1)
    alldry = np.all((prior == 0) | ~common, axis=1)
    flags = pd.read_csv(ROOT / "data/interim/day_flags.csv", parse_dates=["date"]).set_index("date")
    regimes = pd.read_csv(ROOT / "data/interim/feed_regimes.csv")
    print("regime columns", regimes.columns.tolist(), flush=True)
    ratio = regimes.set_index("regime_id").level_ratio
    flags["normal"] = flags.regime_id.map(ratio).between(.8, 1.25)
    holidays = pd.read_csv(ROOT / "data/static/holidays.csv", parse_dates=["date"])
    public = set(holidays.loc[holidays.kind == "public", "date"])
    pilot = {pd.Timestamp("2023-07-12"), pd.Timestamp("2024-04-17")}
    days = pd.date_range(START, END)
    candidates, dry = [], []
    audit = []
    for day in days:
        f = flags.loc[day]
        usable = bool(f.normal and not f.exclude_main and day not in public and day not in pilot)
        selecttime = (g.times >= day+pd.Timedelta(hours=12)) & (g.times <= day+pd.Timedelta(hours=20))
        qualifying = selecttime & (n >= 20) & (share >= .25) & alldry
        ii = np.flatnonzero(qualifying)
        during = (g.times > day+pd.Timedelta(hours=6)) & (g.times <= day+pd.Timedelta(days=1))
        dry_ok = bool(np.nanmax(g.B[during]) == 0 and np.all(np.isfinite(g.B[during]).sum(axis=1) >= 20))
        onset = g.times[ii[0]] if len(ii) else pd.NaT
        audit.append(dict(day=day.date(), usable=usable, regime=f.regime, normal=f.normal,
                          exclude_main=f.exclude_main, public=day in public, pilot=day in pilot,
                          gauge_dry=dry_ok, qualifying_onset=onset))
        if usable and len(ii):
            candidates.append(dict(day=day, onset=onset, regime=f.regime,
                                   onset_share=share[ii[0]], gauges=n[ii[0]]))
        if usable and dry_ok:
            dry.append(dict(day=day, regime=f.regime))
    storms, dry = pd.DataFrame(candidates), pd.DataFrame(dry)
    pd.DataFrame(audit).to_csv(TABLES / "s23_sample_audit.csv", index=False)
    if storms.empty or dry.empty:
        raise RuntimeError(f"No matched sample: {len(storms)} storms, {len(dry)} dry days")
    rng = np.random.default_rng(2702)
    cost = np.full((len(storms), len(dry)+len(storms)), 1e9)
    for i, s in storms.iterrows():
        for j, d in dry.iterrows():
            monthdiff = abs(s.day.month-d.day.month)
            if s.regime == d.regime and s.day.weekday() == d.day.weekday() and min(monthdiff, 12-monthdiff) <= 1:
                cost[i, j] = abs((s.day-d.day).days)+rng.uniform(0, .001)
        cost[i, len(dry)+i] = 1e6
    ii, jj = linear_sum_assignment(cost)
    pairs = [(i, j) for i, j in zip(ii, jj) if j < len(dry) and cost[i, j] < 1e6]
    if len(pairs) > 60:
        pairs = [pairs[k] for k in sorted(rng.choice(len(pairs), 60, replace=False))]
    rows = []
    for pair, (i, j) in enumerate(pairs):
        s, d = storms.iloc[i], dry.iloc[j]
        rows.append(dict(pair=pair, storm_day=str(s.day.date()), dry_day=str(d.day.date()),
                         onset=str(s.onset), regime=s.regime, onset_share=s.onset_share, gauges=s.gauges))
    pd.DataFrame(audit).to_csv(TABLES / "s23_sample_audit.csv", index=False)
    storms.to_csv(TABLES / "s23_storm_candidates.csv", index=False)
    pd.DataFrame(rows).to_csv(TABLES / "s23_sample.csv", index=False)
    print("eligible storm days", len(storms), "dry days", len(dry), "matched pairs", len(rows), flush=True)


if __name__ == "__main__":
    select()
