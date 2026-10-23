"""Fetch and prepare the static data for phase 2 (steps 10-20). Every file is saved under data/static/phase2/
with its source and fetch date in data/static/phase2/SOURCES.csv.

Parts (run in order, or --part all):
  ura        URA Master Plan 2019 subzone boundaries and land use (data.gov.sg)
  pop        Census of Population 2020 residents by subzone and age group; by dwelling type (data.gov.sg)
             (SingStat's June 2025 subzone tables were not downloadable from this machine: 404)
  hdb        HDB property information (blocks, units, year built) geocoded with OneMap search; HDB resale prices
  private    private-housing transactions and project coordinates from ../DAO2702_project (median psf)
  pois       destinations: data.gov.sg (hotels, tourist attractions, hawker centres, LTA bus stops) and
             OpenStreetMap (malls, hospitals, offices, schools, nightlife/food, pick-up points)
  roads      OpenStreetMap drivable road network (osmnx), saved as GraphML
  fc24       NEA 24-hour weather forecasts, Oct 2021 - Sep 2026 (data.gov.sg v1 API by date)
Usage: .venv/bin/python -m analysis.prep_phase2_data --part all
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OUT = Path("data/static/phase2")
OLD = Path("../DAO2702_project")
UA = {"User-Agent": "its-raining-taxis/1.0 (NUS DAO2702 student project)"}
POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{}/poll-download"
DS = {"subzone": "d_8594ae9ff96d0c708bc2af633048edfb", "landuse": "d_90d86daa5bfaa371668b84fa5f01424f",
      "pop_age": "d_d95ae740c0f8961a0b10435836660ce0", "pop_dwelling": "d_7f243956483d5901f237e6f87b096636",
      "hdb_info": "d_17f5382f26140b1fdae0ba2ef6239d2f", "hdb_resale": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      "hotels": "d_654e22f14e5bb817423f0e0c9ac4f632", "attractions": "d_0f2f47515425404e6c9d2a040dd87354",
      "hawker": "d_4a086da0a5553be1d89383cd90d07ecd", "bus_stops": "d_3f172c6feb3f4f92a2f47d93eed2908a"}
BBOX = (103.59, 1.20, 104.06, 1.48)          # west, south, east, north
OVERPASS = ["https://overpass.kumi.systems/api", "https://overpass.private.coffee/api",
            "https://maps.mail.ru/osm/tools/overpass/api", "https://overpass-api.de/api"]


def with_overpass(fn):
    """Call an osmnx function, rotating Overpass endpoints with backoff (the main server is often at capacity)."""
    import osmnx as ox
    last = None
    for attempt in range(8):
        ox.settings.overpass_url = OVERPASS[attempt % len(OVERPASS)]
        try:
            return fn()
        except Exception as e:                     # noqa: BLE001
            last = e
            print("overpass retry", attempt, ox.settings.overpass_url, type(e).__name__, flush=True)
            time.sleep(min(120, 10 * 2 ** (attempt // len(OVERPASS))))
    raise last


def note(name, source, detail=""):
    f = OUT / "SOURCES.csv"
    new = not f.exists()
    with f.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["file", "source", "fetched", "detail"])
        w.writerow([name, source, date.today().isoformat(), detail])


def datagov(key, ext):
    out = OUT / f"{key}.{ext}"
    if out.exists():
        return out
    for attempt in range(5):
        j = requests.get(POLL.format(DS[key]), headers=UA, timeout=60).json()
        url = (j.get("data") or {}).get("url")
        if url:
            break
        time.sleep(5)
    r = requests.get(url, headers=UA, timeout=600)
    r.raise_for_status()
    out.write_bytes(r.content)
    note(out.name, f"data.gov.sg dataset {DS[key]}", f"{len(r.content) / 1e6:.1f} MB")
    print(key, round(len(r.content) / 1e6, 1), "MB", flush=True)
    return out


def part_ura():
    datagov("subzone", "geojson")
    datagov("landuse", "geojson")


def part_pop():
    datagov("pop_age", "csv")
    datagov("pop_dwelling", "csv")
    note("pop_age.csv", "Census of Population 2020 (via data.gov.sg)",
         "SingStat June 2025 subzone tables returned HTTP 404; Census 2020 used instead")


def onemap(addr, session):
    url = "https://www.onemap.gov.sg/api/common/elastic/search"
    for attempt in range(4):
        try:
            r = session.get(url, params={"searchVal": addr, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
                            timeout=30)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            res = r.json().get("results") or []
            if res:
                return float(res[0]["LATITUDE"]), float(res[0]["LONGITUDE"]), res[0].get("POSTAL")
            return None, None, None
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None, None, None


TOWN_PA = {"AMK": ["ANG MO KIO"], "BB": ["BUKIT BATOK"], "BD": ["BEDOK"], "BH": ["BISHAN"], "BM": ["BUKIT MERAH"],
           "BP": ["BUKIT PANJANG"], "BT": ["BUKIT TIMAH"], "CCK": ["CHOA CHU KANG"], "CL": ["CLEMENTI"],
           "CT": ["DOWNTOWN CORE", "OUTRAM", "ROCHOR", "SINGAPORE RIVER", "MUSEUM", "RIVER VALLEY"],
           "GL": ["GEYLANG"], "HG": ["HOUGANG"], "JE": ["JURONG EAST"], "JW": ["JURONG WEST", "BOON LAY"],
           "KWN": ["KALLANG", "NOVENA", "ROCHOR"], "MP": ["MARINE PARADE"], "PG": ["PUNGGOL"], "PRC": ["PASIR RIS"],
           "QT": ["QUEENSTOWN"], "SB": ["SEMBAWANG"], "SGN": ["SERANGOON"], "SK": ["SENGKANG"], "TAP": ["TAMPINES"],
           "TG": ["TENGAH"], "TP": ["TOA PAYOH"], "WL": ["WOODLANDS"], "YS": ["YISHUN"]}


def part_hdb():
    """HDB blocks located without per-block geocoding (OneMap throttles unauthenticated search to ~1 request/s and
    a street-by-street pass would take ~2 hours): each block in HDB Property Information is matched to the HDB
    Existing Building footprint with the same block number lying in (or nearest to) its HDB town's planning
    area(s); where a street geocode was already collected, the footprint nearest that street is used instead.
    Block numbers are unique within most HDB towns; remaining ties are flagged (match = "ambiguous")."""
    info = pd.read_csv(datagov("hdb_info", "csv"))
    datagov("hdb_resale", "csv")
    out = OUT / "hdb_blocks_geocoded.csv"
    if out.exists():
        return
    fp = OUT / "hdb_existing_building.geojson"
    if not fp.exists():
        j = requests.get(POLL.format("d_16b157c52ed637edd6ba1232e026258d"), headers=UA, timeout=60).json()
        fp.write_bytes(requests.get(j["data"]["url"], headers=UA, timeout=600).content)
        note(fp.name, "data.gov.sg HDB Existing Building (d_16b157c52ed637edd6ba1232e026258d)")
    import geopandas as gpd
    from analysis import geo
    from pipeline.grid import to_xy
    b = gpd.read_file(fp).to_crs(3414)
    b["geometry"] = b.geometry.centroid
    sz = geo.subzones().to_crs(3414)
    pa = sz.dissolve("planning_area")
    b = b.sjoin_nearest(pa[["geometry"]].reset_index(), how="left").drop_duplicates("OBJECTID")
    ll = b.to_crs(4326).geometry
    b = pd.DataFrame({"blk": b.BLK_NO.astype(str).str.strip().str.upper(), "pa": b.planning_area.values,
                      "lon": ll.x.values, "lat": ll.y.values, "postal": b.POSTAL_COD.values})
    info.columns = [x.lower() for x in info.columns]
    cache_f = OUT / "hdb_street_geocodes.csv"
    sg = pd.read_csv(cache_f).dropna().set_index("street") if cache_f.exists() else pd.DataFrame(columns=["lat", "lon"])
    bx, by = to_xy(b.lon.values, b.lat.values)
    lat_out, lon_out, post_out, how = [], [], [], []
    for blk, st, town in zip(info.blk_no.astype(str).str.strip().str.upper(), info.street.astype(str).str.strip(),
                             info.bldg_contract_town):
        cand = np.flatnonzero(b.blk.values == blk)
        j, h = None, "unmatched"
        if len(cand) and st in sg.index:
            ax, ay = to_xy([sg.loc[st, "lon"]], [sg.loc[st, "lat"]])
            d = np.hypot(bx[cand] - ax[0], by[cand] - ay[0])
            if d.min() <= 2000:
                j, h = cand[np.argmin(d)], "street"
        if j is None and len(cand):
            inside = cand[np.isin(b.pa.values[cand], TOWN_PA.get(town, []))]
            if len(inside) and b.postal.values[inside].astype(str).tolist().count(b.postal.values[inside[0]]) == len(inside):
                j, h = inside[0], "town"                     # one block drawn as several footprints
            elif len(inside) > 1:
                j, h = inside, "ambiguous"
        lat_out.append(j)
        how.append(h)
    # second pass: an ambiguous block takes the candidate nearest the median of its street's matched blocks
    info["match"] = how
    pick = pd.Series(lat_out, dtype=object)
    sure = info.match.isin(["street", "town"]).values
    sx = pd.DataFrame({"street": info.street.values[sure], "x": bx[pick[sure].astype(int)],
                       "y": by[pick[sure].astype(int)]}).groupby("street").median()
    for i in np.flatnonzero(info.match.values == "ambiguous"):
        cand, st = pick[i], info.street.iloc[i]
        if st in sx.index:
            pick[i] = cand[np.argmin(np.hypot(bx[cand] - sx.loc[st, "x"], by[cand] - sx.loc[st, "y"]))]
            info.loc[i, "match"] = "street median"
        else:
            pick[i] = None
            info.loc[i, "match"] = "unmatched (ambiguous)"
    ok = pick.notna().values
    idx = pick[ok].astype(int).values
    info["lat"], info["lon"], info["postal"] = np.nan, np.nan, None
    info.loc[ok, "lat"], info.loc[ok, "lon"], info.loc[ok, "postal"] = b.lat.values[idx], b.lon.values[idx], b.postal.values[idx]
    info.to_csv(out, index=False)
    vc = info.match.value_counts().to_dict()
    note(out.name, "HDB Property Information matched to HDB Existing Building footprints by block number within the "
         "HDB town's planning area(s) (street geocode where available)", f"match counts {vc}")
    print("match", vc, "units located", int(info.total_dwelling_units[info.lat.notna()].sum()), "of",
          int(info.total_dwelling_units.sum()), flush=True)


def part_private():
    parts = sorted((OLD / "data").glob("properties_2020_2025_clean.csv.part*"))
    raw = b"".join(p.read_bytes() for p in parts)
    import hashlib
    h = hashlib.sha256(raw).hexdigest()
    assert h == "edede72a9ab8c628d30ce9605dc6a6c7ddb8864f22a734c5a92c78117aacf8b6", h
    tx = pd.read_csv(io.BytesIO(raw), low_memory=False)
    co = pd.read_csv(OLD / "project_coords.csv")
    tx = tx.merge(co[["project", "street", "lat", "lon"]], on=["project", "street"], how="left")
    g = (tx.dropna(subset=["lat", "lon", "psf"]).groupby(["project", "street", "lat", "lon"])
         .agg(median_psf=("psf", "median"), transactions=("psf", "size")).reset_index())
    g.to_csv(OUT / "private_projects_psf.csv", index=False)
    note("private_projects_psf.csv", "DAO2702_project: properties_2020_2025_clean.csv (11 parts, SHA-256 checked) + "
         "project_coords.csv", f"{len(g)} projects with coordinates; {int(tx.lat.notna().sum())} of {len(tx)} "
         "transactions matched")
    for f in ("mrt_station_openings.csv",):
        (OUT / f).write_bytes((OLD / f).read_bytes())
        note(f, "DAO2702_project repository")
    print("private projects", len(g), flush=True)


def part_pois():
    for k in ("hotels", "attractions", "hawker", "bus_stops"):
        datagov(k, "geojson")
    import osmnx as ox
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OUT / "osm_cache")
    tags = {"shop": ["mall", "department_store"], "amenity": ["hospital", "school", "university", "college", "bar", "pub",
            "nightclub", "restaurant", "food_court", "cafe", "fast_food", "taxi"], "office": True,
            "building": ["office", "hospital", "school", "university", "hotel"], "tourism": ["attraction", "hotel"],
            "leisure": ["stadium"]}
    out = OUT / "osm_pois.parquet"
    if not out.exists():
        g = with_overpass(lambda: ox.features_from_bbox(BBOX, tags))
        g = g.reset_index()
        g["geometry"] = g.geometry.representative_point()
        keep = [c for c in ["element", "id", "name", "shop", "amenity", "office", "building", "tourism", "leisure"] if c in g]
        df = pd.DataFrame(g[keep])
        df["lon"], df["lat"] = g.geometry.x.values, g.geometry.y.values
        df = df.astype({c: "string" for c in keep if c not in ("id",)})
        df.to_parquet(out, index=False)
        note(out.name, "OpenStreetMap via osmnx (Overpass API)", f"{len(df)} features; tags {json.dumps(tags)}")
        print("osm pois", len(df), flush=True)


def part_roads():
    import osmnx as ox
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OUT / "osm_cache")
    out = OUT / "sg_drive.graphml"
    if out.exists():
        return
    G = with_overpass(lambda: ox.graph_from_bbox(BBOX, network_type="drive", simplify=True, retain_all=False))
    ox.save_graphml(G, out)
    note(out.name, "OpenStreetMap via osmnx graph_from_bbox(network_type='drive')",
         f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print("roads", G.number_of_nodes(), G.number_of_edges(), flush=True)


def part_fc24():
    out = OUT / "nea_24h_forecast.csv"
    if out.exists():
        return
    days = pd.date_range("2021-10-01", "2026-09-30")
    s = requests.Session()
    s.headers.update(UA)

    def get(d):
        for attempt in range(6):
            try:
                r = s.get("https://api.data.gov.sg/v1/environment/24-hour-weather-forecast",
                          params={"date": d.strftime("%Y-%m-%d")}, timeout=60)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                rows = []
                for it in r.json().get("items") or []:
                    gen = it.get("general") or {}
                    for p in it.get("periods") or []:
                        for reg, txt in (p.get("regions") or {}).items():
                            rows.append({"issued": it.get("update_timestamp"), "item_ts": it.get("timestamp"),
                                         "period_start": p["time"]["start"], "period_end": p["time"]["end"],
                                         "region": reg, "forecast": txt, "general": gen.get("forecast"),
                                         "rh_high": (gen.get("relative_humidity") or {}).get("high"),
                                         "t_high": (gen.get("temperature") or {}).get("high")})
                return rows
            except Exception:
                time.sleep(2 ** attempt)
        return [{"issued": None, "item_ts": d.strftime("%Y-%m-%d"), "period_start": None, "period_end": None,
                 "region": None, "forecast": "FETCH_FAILED", "general": None, "rh_high": None, "t_high": None}]

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(get, days))
    df = pd.DataFrame([r for rows in res for r in rows])
    for c in ("issued", "item_ts", "period_start", "period_end"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce").dt.tz_convert("Asia/Singapore").dt.tz_localize(None)
    df = df.drop_duplicates()
    df.to_csv(out, index=False)
    note(out.name, "data.gov.sg v1 environment/24-hour-weather-forecast (historical by date)",
         f"{df.issued.nunique()} issues, {len(days)} days requested, "
         f"{int((df.forecast == 'FETCH_FAILED').sum())} days failed")
    print("fc24 issues", df.issued.nunique(), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="all")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    parts = {"ura": part_ura, "pop": part_pop, "private": part_private, "pois": part_pois, "roads": part_roads,
             "fc24": part_fc24, "hdb": part_hdb}
    for name, fn in parts.items():
        if a.part in ("all", name):
            t0 = time.time()
            fn()
            print("==", name, f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
