"""Download helpers for the public Singapore feeds used in the project.

Only pandas, numpy and requests are needed, so the same code runs on a laptop,
in Colab or on GitHub Actions.
"""
from __future__ import annotations

import os
import random
import threading
import time

import numpy as np
import pandas as pd
import requests

TAXI_URL = "https://api.data.gov.sg/v1/transport/taxi-availability"
RAIN_V1 = "https://api.data.gov.sg/v1/environment/rainfall"
RAIN_V2 = "https://api-open.data.gov.sg/v2/real-time/api/rainfall"
FORECAST_V1 = "https://api.data.gov.sg/v1/environment/2-hour-weather-forecast"


class Client:
    """Thin HTTP client with retries, backoff on rate limits, and call statistics."""

    def __init__(self, api_key: str | None = None, timeout: int = 45, tries: int = 8):
        self.timeout, self.tries = timeout, tries
        self.local = threading.local()
        self.api_key = api_key if api_key is not None else os.environ.get("DATAGOV_KEY", "")
        self.lock = threading.Lock()
        self.stats = {"calls": 0, "ok": 0, "retries": 0, "rate_limited": 0, "failed": 0}

    def _session(self) -> requests.Session:
        s = getattr(self.local, "s", None)
        if s is None:
            s = requests.Session()
            s.headers["User-Agent"] = "its-raining-taxis/1.0 (NUS DAO2702 student project)"
            if self.api_key:
                s.headers["x-api-key"] = self.api_key
            self.local.s = s
        return s

    def _bump(self, key: str) -> None:
        with self.lock:
            self.stats[key] += 1

    def get_json(self, url: str, params: dict | None = None):
        for attempt in range(self.tries):
            self._bump("calls")
            try:
                r = self._session().get(url, params=params, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    self._bump("rate_limited" if r.status_code == 429 else "retries")
                    time.sleep(min(60, 2 ** attempt) + random.random())
                    continue
                r.raise_for_status()
                self._bump("ok")
                return r.json()
            except (requests.RequestException, ValueError):
                self._bump("retries")
                time.sleep(min(60, 2 ** attempt) + random.random())
        self._bump("failed")
        return None


def _naive_sgt(ts) -> pd.Timestamp:
    """Parse an API timestamp (with +08:00) to a naive Singapore-time Timestamp."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Singapore").tz_localize(None)
    return t


def taxi_snapshot(client: Client, req_ts: pd.Timestamp) -> dict:
    """One vacant-taxi snapshot at (or just before) req_ts, Singapore time."""
    j = client.get_json(TAXI_URL, {"date_time": req_ts.strftime("%Y-%m-%dT%H:%M:%S")})
    out = {"req_ts": req_ts, "act_ts": pd.NaT, "taxi_count": np.nan,
           "lon": np.empty(0), "lat": np.empty(0), "status": "failed"}
    if not j:
        return out
    try:
        f = j["features"][0]
        xy = np.asarray(f["geometry"]["coordinates"], dtype="float64").reshape(-1, 2)
        out.update(act_ts=_naive_sgt(f["properties"]["timestamp"]),
                   taxi_count=f["properties"].get("taxi_count", np.nan),
                   lon=xy[:, 0], lat=xy[:, 1], status="ok" if len(xy) else "empty")
    except (KeyError, IndexError, TypeError, ValueError):
        out["status"] = "bad_payload"
    return out


def rain_day_v2(client: Client, day: pd.Timestamp):
    readings, stations, token, pages = [], {}, None, 0
    while True:
        params = {"date": day.strftime("%Y-%m-%d")}
        if token:
            params["paginationToken"] = token
        j = client.get_json(RAIN_V2, params)
        if not j or "data" not in j:
            break
        d = j["data"]
        pages += 1
        for s in d.get("stations", []):
            loc = s.get("location") or s.get("labelLocation") or {}
            stations[s["id"]] = (s.get("name"), loc.get("latitude"), loc.get("longitude"))
        for it in d.get("readings", []):
            ts = it["timestamp"]
            readings += [(ts, x["stationId"], x["value"]) for x in it.get("data", [])]
        token = d.get("paginationToken")
        if not token or pages > 200:
            break
    return readings, stations


def rain_day(client: Client, day: pd.Timestamp):
    """5-minute rainfall for one day: readings (ts, station_id, mm) and station list."""
    readings, stations = [], {}
    j = client.get_json(RAIN_V1, {"date": day.strftime("%Y-%m-%d")})
    if j and j.get("items"):
        for s in j.get("metadata", {}).get("stations", []):
            loc = s.get("location", {})
            stations[s["id"]] = (s.get("name"), loc.get("latitude"), loc.get("longitude"))
        for it in j["items"]:
            readings += [(it["timestamp"], x["station_id"], x["value"]) for x in it.get("readings", [])]
    n_ts = len({r[0] for r in readings})
    source = "v1"
    if n_ts < 280:  # not a full day of 5-minute readings: use the paged v2 API instead
        r2, s2 = rain_day_v2(client, day)
        if len({r[0] for r in r2}) > n_ts:
            readings, stations, source = r2, s2, "v2"
    rd = pd.DataFrame(readings, columns=["ts", "station_id", "mm"])
    if len(rd):
        rd["ts"] = pd.to_datetime(rd.ts, utc=True).dt.tz_convert("Asia/Singapore").dt.tz_localize(None)
        rd["mm"] = pd.to_numeric(rd.mm, errors="coerce")
        rd = rd.drop_duplicates(["ts", "station_id"])
    st = pd.DataFrame([(k, *v) for k, v in stations.items()], columns=["station_id", "name", "lat", "lon"])
    st.insert(0, "date", day.normalize())
    return rd, st, source


def forecast_day(client: Client, day: pd.Timestamp):
    """All 2-hour area forecasts issued on one day, with issue and validity times."""
    j = client.get_json(FORECAST_V1, {"date": day.strftime("%Y-%m-%d")})
    fc_rows, areas = [], []
    if j:
        for it in j.get("items", []):
            vp = it.get("valid_period", {})
            for f in it.get("forecasts", []):
                fc_rows.append((it.get("update_timestamp"), it.get("timestamp"),
                                vp.get("start"), vp.get("end"), f.get("area"), f.get("forecast")))
        for a in j.get("area_metadata", []):
            loc = a.get("label_location", {})
            areas.append((a.get("name"), loc.get("latitude"), loc.get("longitude")))
    fc = pd.DataFrame(fc_rows, columns=["issued", "item_ts", "valid_start", "valid_end", "area", "forecast"])
    for c in ["issued", "item_ts", "valid_start", "valid_end"]:
        if len(fc):
            fc[c] = pd.to_datetime(fc[c], utc=True).dt.tz_convert("Asia/Singapore").dt.tz_localize(None)
    fc = fc.drop_duplicates()
    ar = pd.DataFrame(areas, columns=["area", "lat", "lon"]).drop_duplicates("area")
    return fc, ar
