"""Resumable, bounded minute-position downloads for the registered step-23 sample."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.sources import Client, taxi_snapshot
from pipeline.grid import to_xy
from scipy.spatial import cKDTree

RAW = ROOT / "data/raw_minute"
TABLES = ROOT / "outputs/tables"
PILOT = ["2023-07-12", "2024-04-17"]
_lock = threading.Lock()
_last = 0.0


def content_hash(xy):
    """Hash a multiset: API coordinate ordering must not imply a new observation."""
    order = np.lexsort((xy[:, 1], xy[:, 0])) if len(xy) else []
    return hashlib.sha256(np.asarray(xy[order], dtype="<f8").tobytes()).hexdigest()


def pack(rows, path):
    arrays = [np.column_stack((r["lon"], r["lat"])) for r in rows]
    ptr = np.r_[0, np.cumsum([len(x) for x in arrays])]
    xy = np.concatenate(arrays) if arrays else np.empty((0, 2))
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, xy=xy, ptr=ptr,
                        req=np.array([r["req_ts"].value for r in rows], dtype="int64"),
                        act=np.array([r["act_ts"].value for r in rows], dtype="int64"),
                        status=np.array([r["status"] for r in rows]),
                        reported=np.array([r["taxi_count"] for r in rows]),
                        digest=np.array([content_hash(x) for x in arrays]))
    tmp.replace(path)


def unpack(path):
    with np.load(path) as z:
        z = {k: z[k] for k in z.files}
        return [dict(req_ts=pd.Timestamp(r), act_ts=pd.Timestamp(a), status=str(s),
                     taxi_count=n, lon=z["xy"][lo:hi, 0].copy(),
                     lat=z["xy"][lo:hi, 1].copy())
                for r, a, s, n, lo, hi in zip(z["req"], z["act"], z["status"],
                                              z["reported"], z["ptr"][:-1], z["ptr"][1:])]


def fetch_one(client, ts):
    # At most four active calls and eight starts/second, including across day chunks.
    global _last
    with _lock:
        time.sleep(max(0, .125 - (time.monotonic() - _last)))
        _last = time.monotonic()
    return taxi_snapshot(client, ts)


def fetch(days, interval=1):
    RAW.mkdir(parents=True, exist_ok=True)
    client = Client(timeout=30, tries=6)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for day in days:
            path = RAW / f"{day}_{interval}min.npz"
            if path.exists():
                print("exists", path.name, flush=True)
                continue
            parts = RAW / f".{day}_{interval}min"
            parts.mkdir(exist_ok=True)
            times = pd.date_range(f"{day} 06:00", pd.Timestamp(day) + pd.Timedelta(days=1),
                                  freq=f"{interval}min")
            rows = []
            for i in range(0, len(times), 60):
                part = parts / f"{i:04d}.npz"
                if not part.exists():
                    pack(list(pool.map(lambda ts: fetch_one(client, ts), times[i:i+60])), part)
                rows.extend(unpack(part))
                print(day, "downloaded", len(rows), "/", len(times), json.dumps(client.stats), flush=True)
            pack(rows, path)
            for part in parts.glob("*.npz"):
                part.unlink()
            parts.rmdir()
            print("saved", path.name, path.stat().st_size, flush=True)


def pilot():
    from scipy.spatial import cKDTree
    audits, jitter = [], []
    for day in PILOT:
        with np.load(RAW / f"{day}_1min.npz") as z:
            z = {k: z[k] for k in z.files}
            valid = (z["status"] == "ok") & (z["act"] <= z["req"]) & (z["req"] - z["act"] <= 600e9)
            idx = np.flatnonzero(valid)
            acts = z["act"][idx]
            distinct = np.r_[True, np.diff(acts) != 0]
            changed = np.r_[True, z["digest"][idx][1:] != z["digest"][idx][:-1]]
            duplicates, counts, j = [], [], []
            previous = None
            for i in idx:
                xy = z["xy"][z["ptr"][i]:z["ptr"][i+1]]
                duplicates.append(len(xy) - len(np.unique(xy, axis=0)))
                counts.append(len(xy))
                metric = np.column_stack(to_xy(xy[:, 0], xy[:, 1]))
                if previous is not None and len(metric) > 1 and len(previous) > 1:
                    ta, tb = cKDTree(previous), cKDTree(metric)
                    dist, dest = tb.query(previous)
                    _, back = ta.query(metric)
                    # Both endpoints isolated by >40 m from other vacant points.
                    isolated_a = ta.query(previous, k=2)[0][:, 1] > 40
                    isolated_b = tb.query(metric, k=2)[0][:, 1] > 40
                    keep = (back[dest] == np.arange(len(previous))) & (dist <= 20) & isolated_a & isolated_b[dest]
                    j.extend(dist[keep].tolist())
                previous = metric
            jitter.extend(j)
            audits.append(dict(day=day, requested=len(valid), valid=int(valid.sum()),
                               distinct_timestamps=int(distinct.sum()), distinct_contents=int(changed.sum()),
                               median_timestamp_seconds=float(np.median(np.diff(acts[distinct])) / 1e9),
                               median_content_seconds=float(np.median(np.diff(acts[changed])) / 1e9),
                               median_offset_seconds=float(np.median((acts-z["req"][idx])/1e9)),
                               median_vacant=float(np.median(counts)), duplicate_points=int(sum(duplicates)),
                               total_points=int(sum(counts)), apparent_jitter_pairs=len(j),
                               apparent_jitter_median_m=float(np.median(j)),
                               apparent_jitter_p95_m=float(np.quantile(j, .95))))
    audit = pd.DataFrame(audits)
    audit.to_csv(TABLES / "s23_pilot.csv", index=False)
    refresh = float(audit.median_content_seconds.median())
    settings = dict(interval_minutes=max(1, int(np.floor(refresh/60+.5))) if refresh > 120 else 1,
                    moving_threshold_m=max(2, float(np.quantile(jitter, .95))),
                    content_refresh_seconds=refresh, pilot_days=PILOT,
                    status="pilot complete; freeze before main-sample data")
    (RAW / "pilot_settings.json").write_text(json.dumps(settings, indent=2))
    print(audit.to_string(index=False), flush=True)
    print(json.dumps(settings, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("part", choices=["pilot-fetch", "pilot", "sample-fetch"])
    args = p.parse_args()
    if args.part == "pilot-fetch":
        fetch(PILOT)
    elif args.part == "pilot":
        pilot()
    else:
        sample = pd.read_csv(TABLES / "s23_sample.csv")
        settings = json.loads((RAW / "pilot_settings.json").read_text())
        fetch(sorted(set(sample.storm_day) | set(sample.dry_day)), settings["interval_minutes"])
