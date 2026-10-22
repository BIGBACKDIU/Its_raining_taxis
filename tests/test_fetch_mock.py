"""Offline test of the downloader with fake API payloads (same shapes as the real APIs)."""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import fetch_month, grid, sources  # noqa: E402

rng = np.random.default_rng(0)


def fake_get_json(self, url, params=None):
    self._bump("calls"); self._bump("ok")
    if url == sources.TAXI_URL:
        ts = pd.Timestamp(params["date_time"]) - pd.Timedelta("1s")
        n = 1800 + rng.integers(0, 200)
        pts = np.c_[rng.uniform(103.62, 104.0, n), rng.uniform(1.25, 1.45, n)].round(5).tolist()
        return {"type": "FeatureCollection", "features": [{"type": "Feature",
                "geometry": {"type": "MultiPoint", "coordinates": pts},
                "properties": {"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S+08:00"), "taxi_count": n,
                               "api_info": {"status": "healthy"}}}]}
    if url == sources.RAIN_V1:
        day = pd.Timestamp(params["date"])
        times = pd.date_range(day + pd.Timedelta("5min"), day + pd.Timedelta("1D"), freq="5min")[:-1]
        st = [{"id": f"S{i}", "device_id": f"S{i}", "name": f"Gauge {i}",
               "location": {"latitude": 1.3 + i / 100, "longitude": 103.8 + i / 100}} for i in range(5)]
        items = [{"timestamp": t.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                  "readings": [{"station_id": s["id"], "value": float(rng.choice([0, 0, 0, 0.2, 1.4]))} for s in st]}
                 for t in times]
        return {"metadata": {"stations": st, "reading_type": "TB1 Rainfall 5 Minute Total F", "reading_unit": "mm"},
                "items": items, "api_info": {"status": "healthy"}}
    if url == sources.FORECAST_V1:
        day = pd.Timestamp(params["date"])
        items = []
        for h in range(0, 24):
            t = day + pd.Timedelta(hours=h, minutes=5)
            items.append({"update_timestamp": t.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                          "timestamp": t.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                          "valid_period": {"start": (t - pd.Timedelta('5min')).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                                           "end": (t + pd.Timedelta('115min')).strftime("%Y-%m-%dT%H:%M:%S+08:00")},
                          "forecasts": [{"area": "Bedok", "forecast": "Thundery Showers"},
                                        {"area": "Bishan", "forecast": "Cloudy"}]})
        return {"area_metadata": [{"name": "Bedok", "label_location": {"latitude": 1.32, "longitude": 103.92}},
                                  {"name": "Bishan", "label_location": {"latitude": 1.35, "longitude": 103.84}}],
                "items": items, "api_info": {"status": "healthy"}}
    raise AssertionError(url)


def test_month():
    sources.Client.get_json = fake_get_json
    with tempfile.TemporaryDirectory() as d:
        fetch_month.main(["--month", "2026-02", "--out", d, "--workers", "4", "--limit", "20"])
        out = Path(d)
        z = np.load(out / "taxi" / "2026-02_cells500.npz")
        sn = pd.read_csv(out / "taxi" / "2026-02_snapshots.csv.gz")
        assert len(sn) == 20 and (sn.status == "ok").all()
        assert z["n"].sum() == sn.n_points.sum(), "every taxi lands in exactly one cell"
        assert set(np.unique(z["snap"])) == set(range(20))
        offs = (pd.to_datetime(sn.act_ts) - pd.to_datetime(sn.req_ts)).dt.total_seconds()
        assert (offs == -1).all()
        rd = pd.read_csv(out / "rain" / "2026-02_readings.csv.gz")
        comp = pd.read_csv(out / "rain" / "2026-02_completeness.csv.gz")
        assert (rd.mm > 0).all() and comp.n_readings.max() >= 287
        assert comp.date.nunique() == 28
        fc = pd.read_csv(out / "forecast" / "2026-02_forecast.csv.gz")
        assert len(fc) == 28 * 24 * 2
        log = json.loads((out / "logs" / "2026-02.json").read_text())
        assert log["rain_days_v1"] == 28 and log["snapshots_ok"] == 20
        print("snapshots ok; cells file", (out / "taxi" / "2026-02_cells500.npz").stat().st_size, "bytes for 20 snapshots")


def test_grid():
    # 1 km cells nest exactly in 500 m cells; a degree of latitude is about 110.6 km
    lon, lat = rng.uniform(103.6, 104.05, 10000), rng.uniform(1.2, 1.48, 10000)
    assert (grid.coarsen(grid.cell_ids(lon, lat, 500)) == grid.cell_ids(lon, lat, 1000)).all()
    x0, y0 = grid.to_xy(103.8, 1.30); x1, y1 = grid.to_xy(103.8, 1.31)
    assert abs((y1 - y0) - 1105.7) < 5
    lo, la = grid.to_lonlat(*grid.to_xy(103.85, 1.29))
    assert abs(lo - 103.85) < 1e-9 and abs(la - 1.29) < 1e-9


if __name__ == "__main__":
    test_grid(); test_month(); print("all tests passed")
