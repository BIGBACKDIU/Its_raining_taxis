"""Download one calendar month of vacant taxis, rainfall and 2-hour forecasts.

Usage:  python -m pipeline.fetch_month --month 2026-09 --out out [--workers 4]

Writes (all readable with numpy/pandas only):
  out/taxi/YYYY-MM_cells500.npz        snap, cell, n   (vacant taxis per 500 m cell per snapshot)
  out/taxi/YYYY-MM_snapshots.csv.gz    snap, req_ts, act_ts, taxi_count, n_points, status
  out/rain/YYYY-MM_readings.csv.gz     ts, station_id, mm   (non-zero 5-minute totals only)
  out/rain/YYYY-MM_completeness.csv.gz date, station_id, n_readings, mm_total
  out/rain/YYYY-MM_stations.csv.gz     date, station_id, name, lat, lon
  out/forecast/YYYY-MM_forecast.csv.gz issued, item_ts, valid_start, valid_end, area, forecast
  out/forecast/YYYY-MM_areas.csv.gz    area, lat, lon
  out/logs/YYYY-MM.json                call statistics and timings
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .grid import cell_ids
from .sources import Client, forecast_day, rain_day, taxi_snapshot

FINE_START = pd.Timestamp("2024-10-01")   # 15-minute snapshots from here, 30-minute before


def month_days(month: str):
    start = pd.Timestamp(month + "-01")
    return pd.date_range(start, start + pd.offsets.MonthEnd(0), freq="D")


def snapshot_times(month: str):
    start = pd.Timestamp(month + "-01")
    end = start + pd.offsets.MonthBegin(1)
    step = "15min" if start >= FINE_START else "30min"
    return pd.date_range(start, end, freq=step, inclusive="left")


def fetch_taxi(client: Client, month: str, out: Path, workers: int, limit: int | None = None):
    times = snapshot_times(month)
    if limit:
        times = times[:limit]
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda t: taxi_snapshot(client, t), times))
    snaps, snap_ids, cells, counts = [], [], [], []
    for i, r in enumerate(res):
        snaps.append((i, r["req_ts"], r["act_ts"], r["taxi_count"], len(r["lon"]), r["status"]))
        if len(r["lon"]):
            ok = np.isfinite(r["lon"]) & np.isfinite(r["lat"])
            c, n = np.unique(cell_ids(r["lon"][ok], r["lat"][ok], 500), return_counts=True)
            snap_ids.append(np.full(len(c), i, dtype="int32")); cells.append(c); counts.append(n.astype("int16"))
    (out / "taxi").mkdir(parents=True, exist_ok=True)
    cat = (lambda a, dt: np.concatenate(a).astype(dt) if a else np.empty(0, dt))
    np.savez_compressed(out / "taxi" / f"{month}_cells500.npz",
                        snap=cat(snap_ids, "int32"), cell=cat(cells, "int32"), n=cat(counts, "int16"))
    sn = pd.DataFrame(snaps, columns=["snap", "req_ts", "act_ts", "taxi_count", "n_points", "status"])
    sn.to_csv(out / "taxi" / f"{month}_snapshots.csv.gz", index=False)
    return sn


ERRORS: list = []


def _safe(fn, empty):
    def run(day):
        try:
            return fn(day)
        except Exception as e:  # keep going; record the problem in the month log
            ERRORS.append(f"{fn.__name__} {day.date()}: {type(e).__name__}: {e}")
            return empty()
    return run


def fetch_weather(client: Client, month: str, out: Path, workers: int):
    days = month_days(month)
    empty_rain = lambda: (pd.DataFrame(columns=["ts", "station_id", "mm"]),
                          pd.DataFrame(columns=["date", "station_id", "name", "lat", "lon"]), "error")
    empty_fc = lambda: (pd.DataFrame(columns=["issued", "item_ts", "valid_start", "valid_end", "area", "forecast"]),
                        pd.DataFrame(columns=["area", "lat", "lon"]))
    rain_fn = _safe(lambda d: rain_day(client, d), empty_rain); rain_fn.__name__ = "rain_day"
    fc_fn = _safe(lambda d: forecast_day(client, d), empty_fc); fc_fn.__name__ = "forecast_day"
    with ThreadPoolExecutor(min(workers, 4)) as ex:
        rain = list(ex.map(rain_fn, days))
        fcs = list(ex.map(fc_fn, days))
    (out / "rain").mkdir(parents=True, exist_ok=True)
    (out / "forecast").mkdir(parents=True, exist_ok=True)
    nonempty = [r[0] for r in rain if len(r[0])]
    rd = pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame(columns=["ts", "station_id", "mm"])
    st_parts = [r[1] for r in rain if len(r[1])]
    st = pd.concat(st_parts, ignore_index=True) if st_parts else pd.DataFrame(columns=["date", "station_id", "name", "lat", "lon"])
    sources = [r[2] for r in rain]
    if len(rd):
        rd["date"] = rd.ts.dt.normalize()
        comp = rd.groupby(["date", "station_id"]).agg(n_readings=("mm", "size"), mm_total=("mm", "sum")).reset_index()
        rd[rd.mm > 0][["ts", "station_id", "mm"]].to_csv(out / "rain" / f"{month}_readings.csv.gz", index=False)
    else:
        comp = pd.DataFrame(columns=["date", "station_id", "n_readings", "mm_total"])
        rd.to_csv(out / "rain" / f"{month}_readings.csv.gz", index=False)
    comp.to_csv(out / "rain" / f"{month}_completeness.csv.gz", index=False)
    st.to_csv(out / "rain" / f"{month}_stations.csv.gz", index=False)
    fc_parts, ar_parts = [f[0] for f in fcs if len(f[0])], [f[1] for f in fcs if len(f[1])]
    fc = (pd.concat(fc_parts, ignore_index=True).drop_duplicates() if fc_parts else empty_fc()[0])
    ar = (pd.concat(ar_parts, ignore_index=True).drop_duplicates("area") if ar_parts else empty_fc()[1])
    fc.to_csv(out / "forecast" / f"{month}_forecast.csv.gz", index=False)
    ar.to_csv(out / "forecast" / f"{month}_areas.csv.gz", index=False)
    return {"rain_days_v1": sources.count("v1"), "rain_days_v2": sources.count("v2"), "rain_days_error": sources.count("error"),
            "rain_readings_total": int(len(rd)), "rain_stations_max": int(st.groupby("date").size().max() if len(st) else 0),
            "forecast_rows": int(len(fc)), "forecast_issues": int(fc.issued.nunique() if len(fc) else 0)}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True)
    p.add_argument("--out", default="out")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=None, help="only the first N snapshots (testing)")
    p.add_argument("--skip-weather", action="store_true")
    a = p.parse_args(argv)
    out = Path(a.out)
    client = Client()
    t0 = time.time()
    sn = fetch_taxi(client, a.month, out, a.workers, a.limit)
    t_taxi = time.time() - t0
    try:
        weather = {} if a.skip_weather else fetch_weather(client, a.month, out, a.workers)
    except Exception as e:
        weather = {"weather_error": f"{type(e).__name__}: {e}"}
    log = {"month": a.month, "snapshots": int(len(sn)), "snapshots_ok": int((sn.status == "ok").sum()),
           "median_taxis": float(sn.n_points[sn.status == "ok"].median()) if (sn.status == "ok").any() else None,
           "median_offset_min": float(((pd.to_datetime(sn.act_ts) - pd.to_datetime(sn.req_ts)).dt.total_seconds() / 60).median())
           if (sn.status == "ok").any() else None,
           "taxi_seconds": round(t_taxi, 1), "total_seconds": round(time.time() - t0, 1),
           "calls_per_second": round(client.stats["calls"] / max(1e-9, time.time() - t0), 2),
           "workers": a.workers, "client": client.stats, **weather, "errors": ERRORS[:50]}
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "logs" / f"{a.month}.json").write_text(json.dumps(log, indent=2, default=str))
    print(json.dumps(log, indent=2, default=str))


if __name__ == "__main__":
    main()
