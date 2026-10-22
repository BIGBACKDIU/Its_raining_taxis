"""Fetch the small static data listed in HANDOFF section 3c.

- LTA taxi stops/stands (data.gov.sg d_fa1896e73ded89dd513788d501d45033, GeoJSON)
- Public holidays 2021-2026 (data.gov.sg consolidated d_8ef23381f9417e4d4254ee8b4dcdb176)
  plus MOE school holidays (hand-entered from MOE calendars; see SCHOOL_HOLIDAYS)
- LTA monthly taxi fleet by company and P2P trips (LTA "P2P_info_YYYY.pdf"), for CDG's fleet share
- Raw vacant-taxi GPS positions around ~30 storm peaks (20 in the fit period, 10 in the test year),
  for the simulation's start states (data/raw/storm_positions/)

Usage: .venv/bin/python -m analysis.prep_static [--skip-storms]
"""
from __future__ import annotations

import argparse
import io
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from pipeline.sources import Client, taxi_snapshot

STATIC = Path("data/static")
SRC = STATIC / "sources"
STORM_DIR = Path("data/raw/storm_positions")
UA = {"User-Agent": "its-raining-taxis/1.0 (NUS DAO2702 student project)"}
POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{}/poll-download"
LTA_P2P = "https://www.lta.gov.sg/content/dam/ltagov/who_we_are/statistics_and_publications/statistics/pdf/P2P_info_{}.pdf"
SEED = 2702

# MOE school holidays (primary and secondary), inclusive dates. Sources: MOE press releases
# "School terms and holidays for YYYY"; 2025-2026 checked against moe.gov.sg (30 Jul 2025 release).
SCHOOL_HOLIDAYS = [
    ("2021-11-20", "2021-12-31", "year-end"),
    ("2022-03-12", "2022-03-20", "march"), ("2022-05-28", "2022-06-26", "mid-year"),
    ("2022-09-03", "2022-09-11", "september"), ("2022-11-19", "2022-12-31", "year-end"),
    ("2023-03-11", "2023-03-19", "march"), ("2023-05-27", "2023-06-25", "mid-year"),
    ("2023-09-02", "2023-09-10", "september"), ("2023-11-18", "2023-12-31", "year-end"),
    ("2024-03-09", "2024-03-17", "march"), ("2024-05-25", "2024-06-23", "mid-year"),
    ("2024-08-31", "2024-09-08", "september"), ("2024-11-16", "2024-12-31", "year-end"),
    ("2025-03-15", "2025-03-23", "march"), ("2025-05-31", "2025-06-29", "mid-year"),
    ("2025-09-06", "2025-09-14", "september"), ("2025-11-22", "2025-12-31", "year-end"),
    ("2026-03-14", "2026-03-22", "march"), ("2026-05-30", "2026-06-28", "mid-year"),
    ("2026-09-05", "2026-09-13", "september"), ("2026-11-21", "2026-12-31", "year-end"),
]


def datagov_download(dataset_id: str) -> bytes:
    j = requests.get(POLL.format(dataset_id), headers=UA, timeout=60).json()
    return requests.get(j["data"]["url"], headers=UA, timeout=120).content


def taxi_stands():
    raw = datagov_download("d_fa1896e73ded89dd513788d501d45033")
    (STATIC / "lta_taxi_stops.geojson").write_bytes(raw)
    gj = pd.read_json(io.BytesIO(raw), typ="series")
    rows = []
    for f in gj["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        props = f.get("properties") or {}
        rows.append({"lon": lon, "lat": lat, **{k: v for k, v in props.items() if k != "Description"}})
    df = pd.DataFrame(rows)
    df.to_csv(STATIC / "lta_taxi_stops.csv", index=False)
    print("taxi stops:", len(df), list(df.columns)[:8])


def holidays():
    ph = pd.read_csv(io.BytesIO(datagov_download("d_8ef23381f9417e4d4254ee8b4dcdb176")))
    ph.columns = [c.lower() for c in ph.columns]
    ph["date"] = pd.to_datetime(ph["date"])
    ph = ph[(ph.date >= "2021-01-01") & (ph.date <= "2026-12-31")]
    out = [pd.DataFrame({"date": ph.date, "kind": "public", "name": ph["holiday"]})]
    for a, b, name in SCHOOL_HOLIDAYS:
        out.append(pd.DataFrame({"date": pd.date_range(a, b), "kind": "school", "name": name}))
    h = pd.concat(out).sort_values(["date", "kind"])
    h.to_csv(STATIC / "holidays.csv", index=False, date_format="%Y-%m-%d")
    print("public holidays:", int((h.kind == "public").sum()), "school-holiday days:", int((h.kind == "school").sum()))


def fleet():
    from pypdf import PdfReader
    SRC.mkdir(parents=True, exist_ok=True)
    rows, trips = [], []
    for y in range(2021, 2027):
        pdf = SRC / f"LTA_P2P_info_{y}.pdf"
        if not pdf.exists():
            r = requests.get(LTA_P2P.format(y), headers=UA, timeout=60)
            r.raise_for_status()
            pdf.write_bytes(r.content)
        text = PdfReader(pdf).pages[0].extract_text()
        months = re.findall(r"([A-Z][a-z]{2})-(\d{2})", text.split("\n")[0])
        idx = [pd.Timestamp(f"1 {m} 20{yy}") for m, yy in months]
        section = None
        for line in text.split("\n"):
            if line.startswith("Taxi Fleet"):
                section = "fleet"
                continue
            if line.startswith("Taxi Driver"):
                section = None
            m = re.match(r"(.+?)\s+((?:[\d,]+\s*)+)$", line)
            if not m:
                continue
            vals = [int(v.replace(",", "")) for v in m.group(2).split()]
            if len(vals) != len(idx):
                continue
            name = m.group(1).strip()
            if section == "fleet":
                rows += [(t, name, v) for t, v in zip(idx, vals)]
            elif "street-hail" in name or "ride-hail" in name:
                trips += [(t, "street_hail" if "street" in name else "ride_hail", v * 1000) for t, v in zip(idx, vals)]
    f = pd.DataFrame(rows, columns=["month", "company", "taxis"])
    f.to_csv(STATIC / "lta_taxi_fleet_monthly.csv", index=False, date_format="%Y-%m")
    w = f.pivot_table(index="month", columns="company", values="taxis", aggfunc="sum")
    share = pd.DataFrame({"total_taxis": w["Total"], "cdg_taxis": w["Comfort"] + w["CityCab"]})
    share["cdg_share"] = (share.cdg_taxis / share.total_taxis).round(4)
    tr = pd.DataFrame(trips, columns=["month", "channel", "avg_daily_trips"]).pivot(index="month", columns="channel",
                                                                                     values="avg_daily_trips")
    share = share.join(tr.add_prefix("p2p_daily_trips_"))
    share.to_csv(STATIC / "lta_cdg_share_monthly.csv", date_format="%Y-%m")
    print(share.iloc[[0, 12, 24, 36, 48, -1]].to_string())


def storm_days(n_fit: int = 20, n_test: int = 10, min_gap_days: int = 7) -> pd.DataFrame:
    """Rank days by peak island-mean rain over 30-minute windows (working gauges only)."""
    regimes = pd.read_csv("data/interim/feed_daily.csv", parse_dates=["date"]).set_index("date")
    rows = []
    for f in sorted(Path("data/raw/rain").glob("*_readings.csv.gz")):
        rd = pd.read_csv(f, parse_dates=["ts"])
        comp = pd.read_csv(f.with_name(f.name.replace("readings", "completeness")), parse_dates=["date"])
        ok = comp[comp.n_readings >= 0.8 * 288]
        n_ok = ok.groupby("date").station_id.nunique()
        rd["date"] = rd.ts.dt.normalize()
        rd = rd.merge(ok[["date", "station_id"]], on=["date", "station_id"])
        rd["win"] = rd.ts.dt.ceil("30min")       # window (t-30, t]
        w = rd.groupby(["date", "win"]).mm.sum().reset_index()
        w["mmh"] = 2 * w.mm / w.date.map(n_ok)
        w = w[(w.win.dt.hour >= 7) & (w.win.dt.hour <= 22)]
        rows.append(w.loc[w.groupby("date").mmh.idxmax(), ["date", "win", "mmh"]])
    peaks = pd.concat(rows).rename(columns={"win": "peak_end", "mmh": "peak_mmh"})
    peaks = peaks[~peaks.date.map(regimes.exclude).fillna(True).astype(bool)]
    out = []
    for name, a, b, n in (("fit", "2022-04-01", "2025-03-31", n_fit), ("test", "2025-10-01", "2026-09-30", n_test)):
        cand = peaks[(peaks.date >= a) & (peaks.date <= b)].sort_values("peak_mmh", ascending=False)
        chosen = []
        for r in cand.itertuples():
            if all(abs((r.date - c.date).days) >= min_gap_days for c in chosen):
                chosen.append(r)
            if len(chosen) == n:
                break
        out += [dict(period=name, date=r.date, peak_end=r.peak_end, peak_mmh=round(r.peak_mmh, 2)) for r in chosen]
    return pd.DataFrame(out)


def storm_positions(hours_before: int = 3, hours_after: int = 4):
    STORM_DIR.mkdir(parents=True, exist_ok=True)
    days = storm_days()
    days.to_csv(STORM_DIR / "storm_days.csv", index=False)
    print(days.to_string(index=False))
    client = Client()
    for r in days.itertuples():
        step = "15min" if r.date >= pd.Timestamp("2024-10-01") else "30min"
        times = pd.date_range(r.peak_end - pd.Timedelta(hours=hours_before),
                              r.peak_end + pd.Timedelta(hours=hours_after), freq=step)
        out = STORM_DIR / f"{r.date:%Y-%m-%d}_positions.parquet"
        if out.exists():
            continue
        with ThreadPoolExecutor(4) as ex:
            res = list(ex.map(lambda t: taxi_snapshot(client, t), times))
        parts = [pd.DataFrame({"req_ts": x["req_ts"], "act_ts": x["act_ts"], "lon": x["lon"], "lat": x["lat"]})
                 for x in res if x["status"] == "ok"]
        df = pd.concat(parts, ignore_index=True)
        df.to_parquet(out, index=False, compression="zstd")
        print(out.name, len(parts), "snapshots", len(df), "points")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--skip-storms", action="store_true")
    a = p.parse_args()
    STATIC.mkdir(parents=True, exist_ok=True)
    taxi_stands()
    holidays()
    fleet()
    if not a.skip_storms:
        storm_positions()


if __name__ == "__main__":
    main()
