"""Step 21 inputs: verified Zenodo archive, inspection, clock check, and spatial/temporal aggregation.

Run from the repository root with ``python -m analysis.prep_radar --part download|inspect|aggregate``.
Only step-21 local inputs and radar_* outputs are written. Daily NetCDF files are read from the ZIP in memory.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import time
import zipfile

import netCDF4
import numpy as np
import pandas as pd
import requests
from scipy import sparse
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import Polygon

from analysis import geo
from pipeline.grid import cell_centre, cell_ids, to_xy

ROOT = Path('data/static/phase3/radar')
ARCHIVE = ROOT / '5min_SG.zip'
MD5 = '5d97d0700c23d028fa6e6977485359f7'
SIZE = 10087581305
URL = 'https://zenodo.org/records/19642566/files/5min_SG.zip'
START, END = pd.Timestamp('2022-04-01'), pd.Timestamp('2024-12-31 23:59:59')
TABLES = Path('outputs/tables')


def digest(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(16 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def download(workers=16):
    """Resume bounded HTTP ranges, then concatenate and verify the entire archive before accepting it."""
    ROOT.mkdir(parents=True, exist_ok=True)
    if ARCHIVE.exists() and ARCHIVE.stat().st_size == SIZE and digest(ARCHIVE) == MD5:
        print('Archive already complete; MD5 verified', flush=True)
        return
    parts = ROOT / 'download_parts'
    parts.mkdir(exist_ok=True)
    block = 32 * 1024 * 1024
    n = (SIZE + block - 1) // block
    # Keep complete chunks from an interrupted sequential download.
    if ARCHIVE.exists() and ARCHIVE.stat().st_size < SIZE:
        with open(ARCHIVE, 'rb') as f:
            for i in range(ARCHIVE.stat().st_size // block):
                dest = parts / f'{i:04d}'
                b = f.read(block)
                if not dest.exists():
                    dest.write_bytes(b)

    def fetch(i):
        a, b = i * block, min(SIZE, (i + 1) * block)
        dest = parts / f'{i:04d}'
        if dest.exists() and dest.stat().st_size == b - a:
            return i
        for attempt in range(8):
            try:
                with requests.get(URL, params={'download': 1, 'part': i},
                                  headers={'Range': f'bytes={a}-{b - 1}'}, stream=True, timeout=(30, 180)) as r:
                    r.raise_for_status()
                    assert r.status_code == 206 and r.headers.get('Content-Range') == f'bytes {a}-{b - 1}/{SIZE}'
                    tmp = dest.with_suffix('.part')
                    with open(tmp, 'wb') as f:
                        for data in r.iter_content(1024 * 1024):
                            f.write(data)
                    assert tmp.stat().st_size == b - a
                    tmp.replace(dest)
                return i
            except Exception:
                if attempt == 7:
                    raise
                time.sleep(min(60, 2 ** attempt))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, _ in enumerate(as_completed([pool.submit(fetch, i) for i in range(n)]), 1):
            _.result()
            if done % 8 == 0 or done == n:
                print(f'Download chunks {done}/{n}; elapsed {(time.time() - t0) / 60:.1f} min', flush=True)
    h = hashlib.md5()
    tmp = ROOT / '5min_SG.verified-part'
    with open(tmp, 'wb') as f:
        for i in range(n):
            with open(parts / f'{i:04d}', 'rb') as src:
                for data in iter(lambda: src.read(8 * 1024 * 1024), b''):
                    h.update(data)
                    f.write(data)
    if h.hexdigest() != MD5:
        raise ValueError(f'Archive checksum mismatch: {h.hexdigest()}')
    tmp.replace(ARCHIVE)
    (ROOT / 'verified_md5.txt').write_text(f'{MD5}  5min_SG.zip\n')
    print('Full archive MD5 verified:', MD5, flush=True)


def read_day(z, name):
    with netCDF4.Dataset('radar.nc', memory=z.read(name)) as d:
        rain = np.asarray(d['rainfall'][:].filled(np.nan), dtype='float32')
        ts = pd.DatetimeIndex(netCDF4.num2date(d['time'][:], d['time'].units,
                                             only_use_cftime_datetimes=False, only_use_python_datetimes=True))
        return ts, rain


def members(z):
    return {pd.Timestamp(Path(n).stem.rsplit('_', 1)[1]): n for n in z.namelist() if n.endswith('.nc')}


def spatial_weights(lon, lat, domain=None):
    """Pixel-centre membership; equal weight per nominal 100 m land pixel, never sea pixels."""
    xx, yy = np.meshgrid(lon, lat)
    rings = json.loads(Path('data/static/sg_map.json').read_text())['land']
    coast = shapely.union_all([shapely.make_valid(Polygon(r)) for r in rings])
    land = shapely.contains_xy(coast, xx.ravel(), yy.ravel())
    if domain is not None:
        land &= np.asarray(domain).ravel()
    ids = np.flatnonzero(land)
    plon, plat = xx.ravel()[land], yy.ravel()[land]
    x, y = to_xy(plon, plat)
    cells = pd.read_parquet('data/interim/cells.parquet').query('eligible').sort_values('cell').cell.to_numpy()
    c500 = np.sort(np.unique(np.concatenate([((cells // 1000 * 2 + dx) * 1000 + cells % 1000 * 2 + dy)
                                            for dx in (0, 1) for dy in (0, 1)])))
    p1, p5 = cell_ids(plon, plat, 1000), cell_ids(plon, plat, 500)

    def membership(order, pids):
        lookup = {int(c): j for j, c in enumerate(order)}
        row = np.array([lookup.get(int(v), -1) for v in pids])
        good = row >= 0
        return sparse.csr_matrix((np.ones(good.sum(), 'float32'), (row[good], np.flatnonzero(good))),
                                 shape=(len(order), len(ids)))
    tree = cKDTree(np.c_[x, y])
    cx, cy = to_xy(*cell_centre(cells, 1000))
    ring_rows, ring_cols, near_rows, near_cols = [], [], [], []
    for j, (a, b) in enumerate(zip(cx, cy)):
        idx = np.array(tree.query_ball_point([a, b], 5000), dtype=int)
        dist = np.hypot(x[idx] - a, y[idx] - b)
        rr = idx[(dist > 2000) & (dist <= 5000)]
        # Match the step-3 near-control concept: neighbouring land, excluding the own 1 km cell.
        nn = idx[(dist <= 2000) & (p1[idx] != cells[j])]
        ring_rows.extend([j] * len(rr)); ring_cols.extend(rr)
        near_rows.extend([j] * len(nn)); near_cols.extend(nn)
    shape = (len(cells), len(ids))
    ring = sparse.csr_matrix((np.ones(len(ring_rows), 'float32'), (ring_rows, ring_cols)), shape=shape)
    near = sparse.csr_matrix((np.ones(len(near_rows), 'float32'), (near_rows, near_cols)), shape=shape)
    return ids, cells, c500, {'cell': membership(cells, p1), '500m': membership(c500, p5),
                            'ring': ring, 'near': near}


def mean_pixels(values, W):
    valid = np.isfinite(values)
    count = W @ valid.T.astype('float32')
    total = W @ np.where(valid, values, 0).T
    expected = np.asarray(W.sum(1)).ravel()[:, None]
    # Do not treat missing land pixels as zero or change spatial support across a storm.
    good = (expected > 0) & (count == expected)
    return np.divide(total, count, out=np.full_like(total, np.nan), where=good).T


def snapshot_windows(frame):
    """Five-minute interval END labels; require all six bins in each (t-30, t] window."""
    frame = frame.sort_index()
    grid = pd.date_range(frame.index.min(), frame.index.max(), freq='5min')
    q = frame.reindex(grid)
    now = q.rolling(6, min_periods=6).sum() * 2
    snap = now.index.minute.isin([0, 30])
    return now[snap], now.shift(6)[snap], now.shift(12)[snap]


class Agreement:
    """Streaming paired measurement diagnostics, in mm/h; not an independent validation of a merged product."""

    def __init__(self):
        self.n = 0
        self.s = np.zeros(7, dtype='float64')
        self.conf = {t: np.zeros(4, dtype='int64') for t in (0.0, 0.1, 10.0)}

    def add(self, radar, gauge):
        good = np.isfinite(radar) & np.isfinite(gauge)
        x, y = np.asarray(radar[good], 'float64'), np.asarray(gauge[good], 'float64')
        self.n += len(x)
        self.s += [x.sum(), y.sum(), x @ x, y @ y, x @ y, np.abs(x - y).sum(), (x - y) @ (x - y)]
        for t in self.conf:
            a, b = x > t, y > t
            self.conf[t] += np.bincount((2 * a + b).astype(int), minlength=4)

    def rows(self, scale):
        n = self.n
        if not n:
            return []
        sx, sy, xx, yy, xy, ae, sq = self.s
        cor = (xy - sx * sy / n) / np.sqrt((xx - sx ** 2 / n) * (yy - sy ** 2 / n))
        rows = []
        for t, (tn, fn, fp, tp) in self.conf.items():
            rows.append({'scale': scale, 'n': n, 'correlation': cor, 'mean_radar_mmh': sx / n,
                         'mean_gauge_mmh': sy / n, 'bias_mmh': (sx - sy) / n, 'radar_to_gauge_total_ratio': sx / sy,
                         'mae_mmh': ae / n, 'rmse_mmh': np.sqrt(sq / n), 'threshold_mmh': t,
                         'agreement': (tn + tp) / n, 'gauge_event_sensitivity': tp / max(1, tp + fn),
                         'radar_event_precision': tp / max(1, tp + fp),
                         'both_dry': int(tn), 'gauge_only_wet': int(fn), 'radar_only_wet': int(fp), 'both_wet': int(tp)})
        return rows


class Gauges:
    def __init__(self):
        f = pd.read_csv('data/interim/gauge_day_flags.csv.gz', parse_dates=['date'])
        self.flags = f
        self.month = None

    def day(self, day, index):
        mon = day.strftime('%Y-%m')
        if mon != self.month:
            self.st = pd.read_csv(f'data/raw/rain/{mon}_stations.csv.gz', parse_dates=['date'])
            self.rd = pd.read_csv(f'data/raw/rain/{mon}_readings.csv.gz', parse_dates=['ts'])
            self.month = mon
        f = self.flags[(self.flags.date == day) & self.flags.working & (self.flags.n_readings >= 287)]
        st = self.st[(self.st.date == day) & self.st.station_id.isin(f.station_id)].drop_duplicates('station_id')
        r = self.rd[self.rd.ts.dt.normalize() == day]
        g = r.pivot_table(index='ts', columns='station_id', values='mm', aggfunc='sum')
        g = g.reindex(index=index, columns=st.station_id).fillna(0).astype('float32')
        # Most source days have 287 readings: midnight is not in that day's API archive. Never invent it as dry.
        g.loc[g.index == day] = np.nan
        return st, g


def gauge_pixels(rain, lon, lat, st):
    i = np.abs(np.asarray(lat)[:, None] - st.lat.values).argmin(0)
    j = np.abs(np.asarray(lon)[:, None] - st.lon.values).argmin(0)
    return rain[:, i, j]


def clock_check(read, lon, lat):
    days = ['2022-12-11', '2023-07-20', '2023-12-25', '2024-05-14', '2024-12-29']
    gauges, rows = Gauges(), []
    for day in map(pd.Timestamp, days):
        ts, rain = read(day)
        st, g = gauges.day(day, ts)
        R = pd.DataFrame(gauge_pixels(rain, lon, lat, st), index=ts, columns=g.columns)
        for shift in (-10, -5, 0, 5, 10):
            shifted = R.copy()
            shifted.index += pd.Timedelta(minutes=shift)
            x, y = shifted.reindex(ts).values, g.values
            good = np.isfinite(x) & np.isfinite(y)
            x, y = x[good], y[good]
            rows.append({'date': str(day.date()), 'radar_timestamp_shift_min': shift, 'paired_observations': len(x),
                         'correlation': np.corrcoef(x, y)[0, 1], 'bias_mm_5min': float(np.mean(x - y)),
                         'radar_to_gauge_total_ratio': float(x.sum() / y.sum())})
    out = pd.DataFrame(rows)
    best = out.loc[out.groupby('date').correlation.idxmax()]
    if not (best.radar_timestamp_shift_min == 0).all():
        raise ValueError('Clock checks do not consistently support interval-end labels; do not aggregate yet')
    return out


def inspect_archive():
    if digest(ARCHIVE) != MD5:
        raise ValueError('Full archive MD5 must match before production inspection/aggregation')
    with zipfile.ZipFile(ARCHIVE) as z:
        names = members(z)
        first = names[min(names)]
        with netCDF4.Dataset('metadata', memory=z.read(first)) as d:
            lon, lat = np.asarray(d['lon'][:]), np.asarray(d['lat'][:])
            metadata = {'md5': MD5, 'archive_size_bytes': ARCHIVE.stat().st_size, 'daily_files': len(names),
                        'first_date': str(min(names).date()), 'last_date': str(max(names).date()),
                        'variables': {k: {'dimensions': list(v.dimensions), 'shape': list(v.shape),
                                          'dtype': str(v.dtype), 'attributes': {a: str(v.getncattr(a)) for a in v.ncattrs()}}
                                      for k, v in d.variables.items()},
                        'global_attributes': d.__dict__, 'time_zone': 'UTC+8 (Zenodo metadata)',
                        'rainfall_units': 'mm per five-minute interval (Zenodo metadata; no variable units attribute)',
                        'crs': 'Geographic longitude/latitude axes; no CRS variable or datum/EPSG metadata supplied',
                        'latitude_step_degrees': float(np.diff(lat).mean()),
                        'longitude_step_degrees': float(np.diff(lon).mean()),
                        'bounds_centres': [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]}
        missing = pd.date_range(min(names), max(names)).difference(pd.DatetimeIndex(names))
        metadata['missing_archive_days'] = [str(t.date()) for t in missing]
        clock = clock_check(lambda day: read_day(z, names[day]), lon, lat)
        metadata['timestamp_convention'] = 'Interval end; zero-shift cross-correlation wins on all five fixed storm days'
        clock.to_csv(TABLES / 'radar_clock_check.csv', index=False)
        (ROOT / 'metadata.json').write_text(json.dumps(metadata, indent=2))
        pd.DataFrame([{'field': k, 'value': json.dumps(v)} for k, v in metadata.items()]).to_csv(
            TABLES / 'radar_metadata.csv', index=False)
        print(json.dumps(metadata, indent=2), flush=True)


def aggregate():
    meta = json.loads((ROOT / 'metadata.json').read_text())
    if meta['md5'] != MD5 or ARCHIVE.stat().st_size != SIZE:
        raise ValueError('Run verified inspection first')
    outdir = Path('data/interim/radar_5min')
    outdir.mkdir(exist_ok=True)
    gauges = Gauges()
    agree = {'5min': Agreement(), '30min': Agreement()}
    audit, blocks = [], {}
    t0 = time.time()
    with zipfile.ZipFile(ARCHIVE) as z:
        files = members(z)
        # A fixed product footprint, distinguished from day-specific missing values. Land also requires coastline support.
        _, first = read_day(z, files[pd.Timestamp('2020-01-01')])
        domain = np.isfinite(first).any(0)
        with netCDF4.Dataset('grid', memory=z.read(files[pd.Timestamp('2020-01-01')])) as d:
            lon, lat = np.asarray(d['lon'][:]), np.asarray(d['lat'][:])
        ids, cells, c500, W = spatial_weights(lon, lat, domain)
        coverage = []
        for kind, mat in W.items():
            order = c500 if kind == '500m' else cells
            coverage.extend({'kind': kind, 'cell': int(c), 'land_pixels': int(n)} for c, n in
                            zip(order, np.asarray(mat.sum(1)).ravel()))
        pd.DataFrame(coverage).to_csv(TABLES / 'radar_land_pixel_coverage.csv', index=False)
        dates = pd.date_range(START - pd.Timedelta(days=1), END.normalize())
        current_month = None

        def flush(month):
            for kind, values in blocks.items():
                pd.concat(values).sort_index().to_parquet(outdir / f'{kind}_{month}.parquet')
            blocks.clear()

        for k, day in enumerate(dates):
            mon = day.strftime('%Y-%m')
            if current_month is not None and mon != current_month:
                flush(current_month)
                print(f'Aggregated {current_month}; elapsed {(time.time() - t0) / 60:.1f} min', flush=True)
            current_month = mon
            index = pd.date_range(day, periods=288, freq='5min')
            if day in files:
                ts, rain = read_day(z, files[day])
                assert ts.equals(index), f'Unexpected timestamps: {day}'
                assert rain.shape == (288, len(lat), len(lon)), f'Unexpected grid: {day}'
                if np.any(rain < 0):
                    raise ValueError(f'Negative rainfall: {day}')
                values = rain.reshape(288, -1)[:, ids]
                if (np.isfinite(rain).any(0) & ~domain).any():
                    raise ValueError(f'Product footprint changed on {day}; inspect before proceeding')
                all_missing = np.isnan(values).all(1)
            else:
                values = np.full((288, len(ids)), np.nan, 'float32')
                all_missing = np.ones(288, bool)
                rain = None
            audit.append({'date': str(day.date()), 'archive_present': day in files,
                          'all_missing_steps': int(all_missing.sum()), 'missing_land_values': int(np.isnan(values).sum()),
                          'zero_fraction_among_valid': float((values == 0).sum() / max(1, np.isfinite(values).sum()))})
            for kind, mat in W.items():
                order = c500 if kind == '500m' else cells
                blocks.setdefault(kind, []).append(pd.DataFrame(mean_pixels(values, mat), index=index, columns=order))
            if day >= START and rain is not None:
                st, g = gauges.day(day, index)
                rp = gauge_pixels(rain, lon, lat, st)
                agree['5min'].add(rp * 12, g.values * 12)
                # Gauge midnight is unknown; requiring all six bins excludes incomplete 30-minute windows.
                gr = g.rolling(6, min_periods=6).sum() * 2
                rr = pd.DataFrame(rp, index=index).rolling(6, min_periods=6).sum() * 2
                keep = index.minute.isin([0, 30])
                agree['30min'].add(rr.values[keep], gr.values[keep])
        flush(current_month)
    pd.DataFrame(audit).to_csv(TABLES / 'radar_daily_coverage.csv', index=False)
    pd.DataFrame([r for scale, acc in agree.items() for r in acc.rows(scale)]).to_csv(
        TABLES / 'radar_gauge_agreement.csv', index=False, float_format='%.8f')
    for kind in W:
        import pyarrow as pa
        import pyarrow.parquet as pq
        paths = sorted(outdir.glob(f'{kind}_*.parquet'))
        writers, tail = {}, None
        try:
            for path in paths:
                data = pd.read_parquet(path)
                start = data.index.min()
                if tail is not None:
                    data = pd.concat([tail, data])
                tail = data.iloc[-18:].copy()
                a, b, c = snapshot_windows(data)
                take = (a.index >= max(start, START - pd.Timedelta(days=1))) & (a.index <= END)
                if not take.any():
                    continue
                t, order = a.index[take], a.columns
                year = t[0].year
                df = pd.DataFrame({'ts': np.repeat(t.values, len(order)), 'cell': np.tile(order, len(t)).astype('int32'),
                                   'mmh': a.values[take].ravel().astype('float32'),
                                   'mmh_lag1': b.values[take].ravel().astype('float32'),
                                   'mmh_lag2': c.values[take].ravel().astype('float32')})
                tab = pa.Table.from_pandas(df, preserve_index=False)
                if year not in writers:
                    writers[year] = pq.ParquetWriter(f'data/interim/radar_{kind}_{year}.parquet', tab.schema)
                writers[year].write_table(tab)
        finally:
            for writer in writers.values():
                writer.close()
    print('Radar aggregation and paired gauge diagnostics complete', flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--part', choices=['download', 'inspect', 'aggregate'], required=True)
    p.add_argument('--workers', type=int, default=16)
    args = p.parse_args()
    if args.part == 'download':
        download(args.workers)
    elif args.part == 'inspect':
        inspect_archive()
    else:
        aggregate()


if __name__ == '__main__':
    main()
