"""Retry every snapshot that the bulk download did not return as 'ok', once.

HANDOFF 3a lists the big gaps (2-10 Jan 2023, 23-24 Mar 2025, 2-26 Jun 2025). We retry all
non-ok snapshots (a superset, ~2,700 calls) so that smaller gaps are also given a second chance.
Raw files stay untouched; results go to data/raw/taxi_retry/ with the same layout and snap ids,
and the panel builder overlays them.

Usage: .venv/bin/python -m analysis.prep_retry_gaps
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.grid import cell_ids
from pipeline.sources import Client, taxi_snapshot

RAW = Path("data/raw/taxi")
OUT = Path("data/raw/taxi_retry")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    client = Client(tries=3)
    summary = []
    for f in sorted(RAW.glob("*_snapshots.csv.gz")):
        month = f.name[:7]
        sn = pd.read_csv(f, parse_dates=["req_ts", "act_ts"])
        todo = sn[sn.status != "ok"]
        if todo.empty:
            continue
        with ThreadPoolExecutor(4) as ex:
            res = list(ex.map(lambda t: taxi_snapshot(client, t), todo.req_ts))
        rows, sid, cells, counts = [], [], [], []
        for snap, r in zip(todo.snap, res):
            rows.append((snap, r["req_ts"], r["act_ts"], r["taxi_count"], len(r["lon"]), r["status"]))
            if len(r["lon"]):
                ok = np.isfinite(r["lon"]) & np.isfinite(r["lat"])
                c, n = np.unique(cell_ids(r["lon"][ok], r["lat"][ok], 500), return_counts=True)
                sid.append(np.full(len(c), snap, "int32")); cells.append(c); counts.append(n.astype("int16"))
        out = pd.DataFrame(rows, columns=["snap", "req_ts", "act_ts", "taxi_count", "n_points", "status"])
        out.to_csv(OUT / f"{month}_snapshots.csv.gz", index=False)
        cat = (lambda a, dt: np.concatenate(a).astype(dt) if a else np.empty(0, dt))
        np.savez_compressed(OUT / f"{month}_cells500.npz", snap=cat(sid, "int32"),
                            cell=cat(cells, "int32"), n=cat(counts, "int16"))
        rec = {"month": month, "retried": len(out), "recovered": int((out.status == "ok").sum()),
               **{f"still_{k}": int(v) for k, v in out.status.value_counts().drop("ok", errors="ignore").items()}}
        print(rec, flush=True)
        summary.append(rec)
    pd.DataFrame(summary).fillna(0).to_csv(OUT / "retry_summary.csv", index=False)
    print(json.dumps(client.stats))


if __name__ == "__main__":
    main()
