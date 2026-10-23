"""Parse the Geofabrik OpenStreetMap extract (malaysia-singapore-brunei-latest.osm.pbf) locally with pyosmium.

The public Overpass API servers timed out or refused requests (Oct 2026), so destinations and the drivable road
network come from the Geofabrik extract instead. Output (data/static/phase2/):
  osm_pois.parquet        named destinations: element, id, name, shop, amenity, office, building, tourism, leisure,
                          lon, lat (areas -> representative point)
  osm_drive_nodes.parquet node id, lon, lat (nodes used by drivable ways)
  osm_drive_edges.parquet u, v, length_m, highway, maxspeed (one row per direction; oneway respected)
Drivable ways follow osmnx's "drive" filter in spirit: motorway ... living_street and service roads, excluding
areas, private / no access, and service = parking_aisle / driveway / private.
Usage: .venv/bin/python -m analysis.prep_osm
"""
from __future__ import annotations

import csv
from datetime import date

import numpy as np
import osmium
import pandas as pd
from shapely import wkb

from analysis.prep_phase2_data import BBOX, OUT, note

PBF = OUT / "osm" / "msb-latest.osm.pbf"
W, S, E, N = BBOX
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
POI_KEYS = {"shop": {"mall", "department_store"},
            "amenity": {"hospital", "school", "university", "college", "bar", "pub", "nightclub", "restaurant",
                        "food_court", "cafe", "fast_food", "taxi"},
            "office": None, "building": {"office", "hospital", "school", "university", "hotel"},
            "tourism": {"attraction", "hotel"}, "leisure": {"stadium"}}
COLS = ["shop", "amenity", "office", "building", "tourism", "leisure"]


def inside(lon, lat):
    return W <= lon <= E and S <= lat <= N


def is_poi(tags):
    for k, vals in POI_KEYS.items():
        v = tags.get(k)
        if v is not None and (vals is None or v in vals):
            return True
    return False


class Handler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.pois, self.edges, self.used = [], [], {}
        self.wkb = osmium.geom.WKBFactory()

    def node(self, n):
        if n.tags and n.location.valid() and inside(n.location.lon, n.location.lat) and is_poi(n.tags):
            self.pois.append(("node", n.id, n.tags.get("name"), *[n.tags.get(c) for c in COLS],
                              n.location.lon, n.location.lat))

    def area(self, a):
        if not is_poi(a.tags):
            return
        try:
            g = wkb.loads(self.wkb.create_multipolygon(a), hex=True)
        except Exception:                      # noqa: BLE001
            return
        p = g.representative_point()
        if inside(p.x, p.y):
            self.pois.append(("way" if a.from_way() else "relation", a.orig_id(), a.tags.get("name"),
                              *[a.tags.get(c) for c in COLS], p.x, p.y))

    def way(self, w):
        hw = w.tags.get("highway")
        if hw not in DRIVE or w.tags.get("area") == "yes":
            return
        if w.tags.get("access") in ("no", "private") or w.tags.get("motor_vehicle") in ("no", "private"):
            return
        if hw == "service" and w.tags.get("service") in ("parking_aisle", "driveway", "private", "emergency_access"):
            return
        try:
            locs = [(nd.ref, nd.lon, nd.lat) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if not any(inside(lo, la) for _, lo, la in locs):
            return
        ow = w.tags.get("oneway")
        oneway = ow in ("yes", "true", "1") or w.tags.get("junction") == "roundabout" or (hw == "motorway" and ow != "no")
        reverse = ow == "-1"
        ms = w.tags.get("maxspeed")
        for (u, lo1, la1), (v, lo2, la2) in zip(locs[:-1], locs[1:]):
            d = 6371000 * np.hypot(np.radians(lo2 - lo1) * np.cos(np.radians((la1 + la2) / 2)), np.radians(la2 - la1))
            self.used[u] = (lo1, la1)
            self.used[v] = (lo2, la2)
            if reverse:
                self.edges.append((v, u, d, hw, ms))
            else:
                self.edges.append((u, v, d, hw, ms))
                if not oneway:
                    self.edges.append((v, u, d, hw, ms))


def main():
    h = Handler()
    h.apply_file(str(PBF), locations=True, idx="flex_mem")
    p = pd.DataFrame(h.pois, columns=["element", "id", "name"] + COLS + ["lon", "lat"])
    p.to_parquet(OUT / "osm_pois.parquet", index=False)
    nodes = pd.DataFrame([(k, *v) for k, v in h.used.items()], columns=["node", "lon", "lat"])
    nodes.to_parquet(OUT / "osm_drive_nodes.parquet", index=False)
    e = pd.DataFrame(h.edges, columns=["u", "v", "length_m", "highway", "maxspeed"])
    e.to_parquet(OUT / "osm_drive_edges.parquet", index=False)
    src = "Geofabrik malaysia-singapore-brunei-latest.osm.pbf parsed with pyosmium (Overpass API unavailable)"
    note("osm_pois.parquet", src, f"{len(p)} features in bbox {BBOX}")
    note("osm_drive_edges.parquet", src, f"{len(nodes)} nodes, {len(e)} directed edges")
    print("pois", len(p), p.groupby(p.amenity.fillna(p.shop).fillna(p.tourism).fillna("other")).size()
          .sort_values(ascending=False).head(12).to_dict())
    print("nodes", len(nodes), "edges", len(e))


if __name__ == "__main__":
    main()
