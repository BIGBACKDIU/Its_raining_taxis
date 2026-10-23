"""Shared geography for phase 2: land grid, names, MRT, destinations, residents, housing.

All distances are computed in SVY21 (EPSG:3414) or with pipeline.grid's local metric projection.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import Point, box

from pipeline.grid import cell_centre, split_id, to_lonlat, to_xy

P2 = Path("data/static/phase2")
STATIC = Path("data/static")
CRS = "EPSG:3414"
CITY_CENTRE = (103.8519, 1.2834)        # Raffles Place MRT
AIRPORT = (103.9893, 1.3592)            # Changi Airport T3 taxi stands


def _square(cx, cy, size=1000):
    lon0, lat0 = to_lonlat(cx * size, cy * size)
    lon1, lat1 = to_lonlat((cx + 1) * size, (cy + 1) * size)
    return box(lon0, lat0, lon1, lat1)


@lru_cache
def subzones() -> gpd.GeoDataFrame:
    g = gpd.read_file(P2 / "subzone.geojson")[["SUBZONE_N", "PLN_AREA_N", "REGION_N", "CA_IND", "geometry"]]
    return g.rename(columns={"SUBZONE_N": "subzone", "PLN_AREA_N": "planning_area", "REGION_N": "region",
                             "CA_IND": "central_area"})


@lru_cache
def land_cells(size: int = 1000) -> gpd.GeoDataFrame:
    """Grid cells (size m) whose centre lies inside an MP2019 subzone, with names; geometry = cell square (lon/lat)."""
    sz = subzones()
    w, s, e, n = sz.total_bounds
    x0, y0 = to_xy([w], [s])
    x1, y1 = to_xy([e], [n])
    cxs = np.arange(int(x0[0] // size), int(x1[0] // size) + 1)
    cys = np.arange(int(y0[0] // size), int(y1[0] // size) + 1)
    cx, cy = np.meshgrid(cxs, cys)
    cx, cy = cx.ravel(), cy.ravel()
    lon, lat = to_lonlat((cx + 0.5) * size, (cy + 0.5) * size)
    pts = gpd.GeoDataFrame({"cx": cx, "cy": cy, "lon": lon, "lat": lat}, geometry=gpd.points_from_xy(lon, lat), crs=4326)
    j = gpd.sjoin(pts, sz, how="inner", predicate="within").drop(columns="index_right")
    j = j.drop_duplicates(["cx", "cy"])
    j["cell"] = (j["cx"] * 1000 + j["cy"]).astype(int)
    j["geometry"] = [_square(a, b, size) for a, b in zip(j["cx"], j["cy"])]
    return gpd.GeoDataFrame(j.reset_index(drop=True), geometry="geometry", crs=4326)


@lru_cache
def mrt() -> pd.DataFrame:
    m = json.load(open(STATIC / "sg_mrt.json"))
    st = pd.DataFrame(m["stations"], columns=["name", "code", "network", "lat", "lon"])
    # a station's code can combine several lines ("NS24-NE6-CC1"): every MRT line prefix counts (decision 137).
    # MRT lines only: LRT codes (BP, PTC, STC, SW, SE, PE, PW) are not lines; the Changi Airport branch CG is EW.
    lrt = {"BP", "PTC", "STC", "SW", "SE", "PE", "PW"}
    st["line_set"] = st.code.map(lambda c: frozenset("EW" if p == "CG" else p for p in re.findall(r"([A-Z]+)\d*", c)
                                                     if p not in lrt))
    g = st.groupby("name").agg(lat=("lat", "mean"), lon=("lon", "mean"), codes=("code", lambda c: " ".join(sorted(c))),
                               line_set=("line_set", lambda l: frozenset().union(*l)),
                               network=("network", "first")).reset_index()
    g["lines"] = g.line_set.map(len)
    g["interchange"] = g.lines >= 2
    op = pd.read_csv(P2 / "mrt_station_openings.csv", parse_dates=["opened"])
    g = g.merge(op[["station", "opened", "stage"]].rename(columns={"station": "name"}), on="name", how="left")
    ex = pd.DataFrame(m["exits"], columns=["station", "network", "lat", "lon"])
    return g, ex


@lru_cache
def pois() -> pd.DataFrame:
    rows = []
    a = json.load(open(P2 / "attractions.geojson"))["features"]
    rows += [("attraction", f["properties"].get("PAGETITLE"), *f["geometry"]["coordinates"][:2]) for f in a]
    for k, field, cat in (("hotels", "NAME", "hotel"), ("hawker", "NAME", "hawker centre")):
        for f in json.load(open(P2 / f"{k}.geojson"))["features"]:
            rows.append((cat, f["properties"].get(field), *f["geometry"]["coordinates"][:2]))
    for f in json.load(open(P2 / "bus_stops.geojson"))["features"]:
        rows.append(("bus stop", None, *f["geometry"]["coordinates"][:2]))
    df = pd.DataFrame(rows, columns=["category", "name", "lon", "lat"])
    f = P2 / "osm_pois.parquet"
    if f.exists():
        o = pd.read_parquet(f)
        cat = np.select(
            [o.shop.isin(["mall", "department_store"]), o.amenity.eq("hospital") | o.building.eq("hospital"),
             o.amenity.isin(["university", "college"]) | o.building.eq("university"),
             o.amenity.eq("school") | o.building.eq("school"),
             o.amenity.isin(["bar", "pub", "nightclub"]), o.amenity.isin(["restaurant", "food_court", "cafe", "fast_food"]),
             o.office.notna() | o.building.eq("office"), o.amenity.eq("taxi"),
             o.tourism.eq("attraction"), o.tourism.eq("hotel") | o.building.eq("hotel")],
            ["mall", "hospital", "university", "school", "nightlife", "food", "office", "taxi point", "attraction (OSM)",
             "hotel (OSM)"], "other")
        o = pd.DataFrame({"category": cat, "name": o.name, "lon": o.lon, "lat": o.lat})
        df = pd.concat([df, o[o.category != "other"]], ignore_index=True)
    df = df.dropna(subset=["lon", "lat"])
    df["name"] = df.name.map(_fix_text)
    hw = df.category.eq("hawker centre") & df.name.str.contains(r"\(.+\)", na=False)
    df.loc[hw, "name"] = df.loc[hw, "name"].str.extract(r"\((.+)\)", expand=False)    # "Blk 17 (X Food Centre)" -> X
    df = df[(df.lon > 103.5) & (df.lon < 104.1) & (df.lat > 1.15) & (df.lat < 1.5)]
    return df.reset_index(drop=True)


LANDMARK_PRIORITY = ["attraction", "mall", "hospital", "university", "hotel", "hawker centre", "school"]


def _fix_text(s):
    """Repair UTF-8 text that was decoded as cp1252 (e.g. 'Marina Bay SandsÂ®')."""
    if not isinstance(s, str):
        return s
    try:
        t = s.encode("cp1252").decode("utf-8")
        s = t
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s.replace("®", "").replace("™", "").strip()


def landmarks(lon, lat, radius_m=700, k=3):
    """Up to k named destinations within radius of each point, by category priority then distance."""
    p = pois()
    p = p[p.category.isin(LANDMARK_PRIORITY) & p.name.notna() & (p.name.str.len() > 2)
          & ~p.name.str.match(r"(?i)^(blk|block|tower|building|level)\s*[\w-]{0,4}$", na=False)].copy()
    p["prio"] = p.category.map({c: i for i, c in enumerate(LANDMARK_PRIORITY)})
    px, py = to_xy(p.lon.values, p.lat.values)
    tree = cKDTree(np.c_[px, py])
    x, y = to_xy(np.asarray(lon), np.asarray(lat))
    out = []
    for xi, yi in zip(x, y):
        idx = tree.query_ball_point([xi, yi], radius_m)
        if not idx:
            out.append("")
            continue
        c = p.iloc[idx].assign(d=np.hypot(px[idx] - xi, py[idx] - yi)).sort_values(["prio", "d"])
        names = list(dict.fromkeys(c.name.str.strip()))[:k]
        out.append("; ".join(names))
    return out


def nearest_mrt(lon, lat, k=2):
    st, _ = mrt()
    sx, sy = to_xy(st.lon.values, st.lat.values)
    x, y = to_xy(np.asarray(lon), np.asarray(lat))
    d, i = cKDTree(np.c_[sx, sy]).query(np.c_[x, y], k=k)
    return [", ".join(f"{st.name.iloc[j]} ({dd / 1000:.1f} km)" for j, dd in zip(ii, di)) for ii, di in zip(i, d)]


def place_label(row):
    lm = row.get("landmarks") or ""
    first = lm.split(";")[0].strip() if lm else ""
    sz, pa = row["subzone"].title().replace("'S", "'s"), row["planning_area"].title().replace("'S", "'s")
    return f"{sz} ({first})" if first else f"{sz}, {pa}"


@lru_cache
def residents_by_cell(size: int = 1000) -> pd.DataFrame:
    """Census 2020 residents per land cell: subzone totals allocated by MP2019 residential land-use area."""
    pop = pd.read_csv(P2 / "pop_age.csv")
    pop["key"] = pop.Number.str.strip().str.upper()
    num = lambda c: pd.to_numeric(pop[c].astype(str).str.replace(",", "").replace("-", "0"), errors="coerce").fillna(0)
    pop["residents"] = num("Total_Total")
    pop["age65"] = sum(num(c) for c in pop.columns if c.startswith("Total_") and c.split("_")[1].isdigit()
                       and int(c.split("_")[1]) >= 65) + num("Total_90andOver")
    sz = subzones().to_crs(CRS)
    sz["key"] = sz.subzone.str.upper()
    sz = sz.merge(pop[["key", "residents", "age65"]], on="key", how="left").fillna({"residents": 0, "age65": 0})
    lu = gpd.read_parquet(P2 / "landuse.parquet").to_crs(CRS)
    res = lu[lu.LU_DESC.str.contains("RESIDENTIAL", na=False)][["geometry"]]
    cells = land_cells(size).to_crs(CRS)[["cell", "geometry"]]
    a = gpd.overlay(res, sz[["key", "residents", "age65", "geometry"]], how="intersection", keep_geom_type=True)
    a["a_sz"] = a.area
    tot = a.groupby("key").a_sz.sum()
    b = gpd.overlay(a, cells, how="intersection", keep_geom_type=True)
    b["w"] = b.area / b.key.map(tot)
    b["res"] = b.w * b.residents
    b["a65"] = b.w * b.age65
    out = b.groupby("cell").agg(residents=("res", "sum"), age65=("a65", "sum")).reset_index()
    out["share_65plus"] = np.where(out.residents > 0, out.age65 / out.residents, np.nan)
    return out


def landuse_shares(size: int = 1000) -> pd.DataFrame:
    lu = gpd.read_parquet(P2 / "landuse.parquet").to_crs(CRS)
    groups = {"residential": "RESIDENTIAL", "commercial": "COMMERCIAL|HOTEL|WHITE",
              "business": "BUSINESS", "institution": "INSTITUTION|EDUCATIONAL|HEALTH|CIVIC",
              "park": "PARK|OPEN SPACE|BEACH|SPORTS"}
    cells = land_cells(size).to_crs(CRS)[["cell", "geometry"]]
    cells["cell_area"] = cells.area
    out = cells[["cell", "cell_area"]].copy()
    for k, pat in groups.items():
        sub = lu[lu.LU_DESC.str.contains(pat, na=False)][["geometry"]]
        ov = gpd.overlay(sub, cells[["cell", "geometry"]], how="intersection", keep_geom_type=True)
        out[f"lu_{k}"] = out.cell.map(ov.assign(a=ov.area).groupby("cell").a.sum()).fillna(0) / out.cell_area
    return out.drop(columns="cell_area")


def counts_within(lon, lat, plon, plat, radius_m):
    px, py = to_xy(np.asarray(plon), np.asarray(plat))
    x, y = to_xy(np.asarray(lon), np.asarray(lat))
    tree = cKDTree(np.c_[px, py])
    return np.array([len(v) for v in tree.query_ball_point(np.c_[x, y], radius_m)])


def dist_to(lon, lat, plon, plat):
    px, py = to_xy(np.asarray(plon), np.asarray(plat))
    x, y = to_xy(np.asarray(lon), np.asarray(lat))
    return cKDTree(np.c_[px, py]).query(np.c_[x, y])[0]
