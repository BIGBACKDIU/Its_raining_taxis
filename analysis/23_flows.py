"""Step 23: registered anonymous-position flow proxies; no vehicle identities."""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.grid import cell_ids, to_xy
from analysis.s23_fetch import RAW, PILOT, unpack
from analysis.s23_matching import assign, cancel_flicker, conservation, dense_points
from analysis.s23_sample import Gauges, LOCAL, TABLES

RADII = (.5, 1., 2.)
_gauges = None


def settings():
    return json.loads((RAW / "pilot_settings.json").read_text())


def eligible():
    c = pd.read_parquet(ROOT / "data/interim/cells.parquet")
    return np.sort(c.loc[c.eligible, "cell"].to_numpy())


def validate():
    """Known synthetic identities, events and speed; settings are never tuned here."""
    rng = np.random.default_rng(2702)
    rows = []
    interval = settings()["interval_minutes"]
    for day in PILOT:
        source = unpack(RAW / f"{day}_1min.npz")
        for hour in (8, 14, 20):
            r = min(source, key=lambda x: abs((x["req_ts"]-(pd.Timestamp(day)+pd.Timedelta(hours=hour))).total_seconds()))
            a = np.column_stack(to_xy(r["lon"], r["lat"]))
            for speed in (0, 15, 30):
                for event_rate in (.1, .2):
                    n = len(a)
                    removed = rng.choice(n, round(n*event_rate), replace=False)
                    keep = np.ones(n, bool); keep[removed] = False
                    angle = rng.uniform(0, 2*np.pi, n)
                    shift = np.column_stack((np.cos(angle), np.sin(angle)))*speed*1000/60*interval
                    b = a[keep]+shift[keep]
                    # Entrants are sampled from the same occupied geography, with local displacement.
                    added = a[rng.choice(n, len(removed), replace=True)]+rng.normal(0, 150, (len(removed), 2))
                    truth = np.r_[np.flatnonzero(keep), np.full(len(added), -1)]
                    b = np.r_[b, added]
                    perm = rng.permutation(len(b)); b, truth = b[perm], truth[perm]
                    for radius in RADII:
                        ia, ib, dist = assign(a, b, radius*1000*interval)
                        real = truth[ib] == ia
                        got_d = np.setdiff1d(np.arange(n), ia)
                        got_a = np.setdiff1d(np.arange(len(b)), ib)
                        mover = dist > settings()["moving_threshold_m"]
                        observed_speed = np.median(dist[mover])*60/1000/interval if mover.any() else 0.
                        rows.append(dict(day=day, hour=hour, true_speed_kmh=speed, event_rate=event_rate,
                                         radius_km_min=radius, n=n, matched=len(ia), true_links=int(real.sum()),
                                         link_precision=real.mean() if len(real) else np.nan,
                                         link_recall=real.sum()/keep.sum(),
                                         D_recall=np.isin(removed, got_d).mean(),
                                         A_recall=np.isin(np.flatnonzero(truth == -1), got_a).mean(),
                                         estimated_D=len(got_d), true_D=len(removed),
                                         estimated_A=len(got_a), true_A=len(removed),
                                         moving_speed_kmh=observed_speed, speed_error_kmh=observed_speed-speed))
    pd.DataFrame(rows).to_csv(TABLES / "s23_matching_validation.csv", index=False)
    print(pd.DataFrame(rows).groupby(["radius_km_min", "true_speed_kmh"])[
        ["link_precision", "link_recall", "D_recall", "A_recall", "speed_error_kmh"]].mean().to_string(), flush=True)


def counts(cells, eligible_cells):
    idx = np.searchsorted(eligible_cells, cells)
    ok = idx < len(eligible_cells)
    ok[ok] &= eligible_cells[idx[ok]] == cells[ok]
    v = np.bincount(idx[ok], minlength=len(eligible_cells)+1).astype(float)
    v[-1] = len(cells)
    return v


def process(task):
    global _gauges
    pair, day, storm_day, role, radius, onset = task
    path = LOCAL / f"{day}_{radius:g}.parquet"
    if path.exists():
        return str(path)
    if _gauges is None:
        _gauges = Gauges()
    cfg = settings(); ec = eligible(); nc = len(ec)+1
    start = pd.Timestamp(day)+pd.Timedelta(hours=6, minutes=pd.Timestamp(onset).minute % 15)
    raw = unpack(RAW / f"{day}_{cfg['interval_minutes']}min.npz")
    valid = [r for r in raw if r["status"] == "ok" and
             0 <= (r["req_ts"]-r["act_ts"]).total_seconds() <= 600]
    valid.sort(key=lambda r: r["act_ts"])
    # Duplicate actual timestamps do not create observations, even if API ordering changes.
    valid = list({r["act_ts"]: r for r in valid}.values())
    M = {k: np.zeros((2, 72, nc)) for k in ("D_raw", "A_raw", "D", "A", "V", "outflow")}
    coverage = np.zeros(72)
    speeds = [[[] for _ in range(nc)] for _ in range(144)]
    events, bridge_rows = [], []
    pair_count, max_balance = 0, 0.

    def add_event(kind, xy, cells, dense, ts, bin_id):
        for point, cell, den in zip(xy, cells, dense):
            events.append(dict(kind=kind, xy=point, cell=cell, dense=bool(den),
                               time=(ts-start).total_seconds(), bin=bin_id, removed=False))

    for left, right in zip(valid[:-1], valid[1:]):
        dt = (right["act_ts"]-left["act_ts"]).total_seconds()
        if not 0 < dt <= cfg["interval_minutes"]*120:
            continue
        a = np.column_stack(to_xy(left["lon"], left["lat"]))
        b = np.column_stack(to_xy(right["lon"], right["lat"]))
        ca = cell_ids(left["lon"], left["lat"], 1000)
        cb = cell_ids(right["lon"], right["lat"], 1000)
        da, db = dense_points(a), dense_points(b)
        ia, ib, distance = assign(a, b, radius*1000*dt/60)
        D, A = conservation(len(a), len(b), ia, ib)
        missing_a = np.setdiff1d(np.arange(len(a)), ia, assume_unique=True)
        missing_b = np.setdiff1d(np.arange(len(b)), ib, assume_unique=True)
        balance = counts(cb, ec)-counts(ca, ec)-counts(cb[missing_b], ec)+counts(ca[missing_a], ec)
        balance -= counts(cb[ib], ec)-counts(ca[ia], ec)
        max_balance = max(max_balance, np.max(np.abs(balance)))
        assert max_balance == 0
        pair_count += 1
        k = int((right["act_ts"]-start).total_seconds()//900)
        # Duration-weighted stock and observed exposure, splitting bin boundaries exactly.
        lo = max(0., (left["act_ts"]-start).total_seconds())
        hi = min(18*3600., (right["act_ts"]-start).total_seconds())
        while lo < hi:
            j = int(lo//900); end = min(hi, (j+1)*900); duration = end-lo
            coverage[j] += duration
            M["V"][0, j] += counts(ca, ec)*duration
            M["V"][1, j] += counts(ca[~da], ec)*duration
            lo = end
        if not 0 <= k < 72:
            continue
        add_event("D", a[missing_a], ca[missing_a], da[missing_a], right["act_ts"], k)
        add_event("A", b[missing_b], cb[missing_b], db[missing_b], right["act_ts"], k)
        for dense_mode in (0, 1):
            ma = ~da[missing_a] if dense_mode else np.ones(D, bool)
            mb = ~db[missing_b] if dense_mode else np.ones(A, bool)
            M["D_raw"][dense_mode, k] += counts(ca[missing_a][ma], ec)
            M["A_raw"][dense_mode, k] += counts(cb[missing_b][mb], ec)
        union = np.unique(np.r_[ca[ia], cb[ib]])
        rain_ts = pd.Timestamp(storm_day)+(left["act_ts"]-pd.Timestamp(day))
        wet, rain_valid = _gauges.wet_cells(rain_ts, union)
        wa = wet[np.searchsorted(union, ca[ia])]
        wb = wet[np.searchsorted(union, cb[ib])]
        net = wa.astype(int)-wb.astype(int)
        for dense_mode in (0, 1):
            keep = ~(da[ia] | db[ib]) if dense_mode else np.ones(len(ia), bool)
            leaving, entering = keep & (net == 1), keep & (net == -1)
            if rain_valid:
                M["outflow"][dense_mode, k] += counts(ca[ia[leaving]], ec)-counts(cb[ib[entering]], ec)
            else:
                M["outflow"][dense_mode, k] = np.nan
            moving = keep & (distance > cfg["moving_threshold_m"])
            speed = distance[moving]/dt*3.6
            c = ca[ia[moving]]
            speeds[dense_mode*72+k][-1].extend(speed.tolist())
            idx = np.searchsorted(ec, c)
            for ci in np.unique(idx[idx < len(ec)]):
                mask = (idx == ci) & (c == ec[ci])
                speeds[dense_mode*72+k][ci].extend(speed[mask].tolist())
    bridges = cancel_flicker(events)
    for event in events:
        if event["removed"]:
            continue
        for dense_mode in (0, 1):
            if dense_mode and event["dense"]:
                continue
            M[event["kind"]][dense_mode, event["bin"]] += counts(np.array([event["cell"]]), ec)
    out = []
    for dense_mode in (0, 1):
        for k in range(72):
            covered = coverage[k]/900
            good = covered >= .8
            for ci, cell in enumerate(np.r_[ec, -1]):
                row = dict(pair=pair, day=day, storm_day=storm_day, role=role, radius=radius,
                           dense_excluded=bool(dense_mode), ts=start+pd.Timedelta(minutes=15*k),
                           cell=int(cell), coverage=covered, valid=good)
                for name in M:
                    if name == "V":
                        row[name] = M[name][dense_mode, k, ci]/coverage[k] if good else np.nan
                    else:
                        row[name] = M[name][dense_mode, k, ci]/covered if good else np.nan
                values = speeds[dense_mode*72+k][ci]
                row["speed"] = np.median(values) if good and values else np.nan
                row["moving_links"] = len(values) if good else np.nan
                out.append(row)
    d = pd.DataFrame(out)
    d.to_parquet(path, index=False)
    pd.DataFrame([dict(day=day, radius=radius, requested=len(raw), valid=len(valid),
                       analysed_pairs=pair_count, max_cell_balance_error=max_balance,
                       raw_D=sum(e["kind"] == "D" for e in events), raw_A=sum(e["kind"] == "A" for e in events),
                       flicker_bridges=len(bridges), coverage_mean=coverage.mean()/900,
                       missing_bins=int((coverage < .8*900).sum()))]).to_csv(
        LOCAL / f"{day}_{radius:g}_audit.csv", index=False)
    print("processed", day, radius, "pairs", pair_count, "flickers", len(bridges), flush=True)
    return str(path)


def run():
    LOCAL.mkdir(parents=True, exist_ok=True)
    sample = pd.read_csv(TABLES / "s23_sample.csv")
    tasks = []
    for s in sample.itertuples():
        for role, day in (("storm", s.storm_day), ("dry", s.dry_day)):
            for radius in RADII:
                tasks.append((s.pair, day, s.storm_day, role, radius, s.onset))
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(process, tasks))
    pd.concat([pd.read_csv(p) for p in LOCAL.glob("*_audit.csv")]).to_csv(TABLES / "s23_flow_audit.csv", index=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("part", choices=["validate", "flows"])
    args = p.parse_args()
    validate() if args.part == "validate" else run()
