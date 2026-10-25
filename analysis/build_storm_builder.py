"""Build presentation-only Storm Builder from frozen model inputs and local OSM roads."""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import wkt
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.grid import to_xy, LON0, LAT0, M_PER_DEG_LAT, M_PER_DEG_LON

OUT = ROOT / "sim/v3"
TABLES = ROOT / "outputs/tables"
CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary"]


def roads(cells):
    source = ROOT / "data/static/phase2/sg_drive.graphml"
    original = nx.read_graphml(source)
    graph = nx.MultiDiGraph()
    for u, v, key, edge in original.edges(keys=True, data=True):
        hw = edge.get("highway", "")
        hw = ast.literal_eval(hw) if hw.startswith("[") else [hw]
        allowed = [h for h in hw if h in CLASSES or h.removesuffix("_link") in CLASSES]
        # A simplified mixed-class edge has no per-segment tags: conservatively omit
        # it if ANY original class is outside the requested major-road set.
        if not allowed or len(allowed) != len(hw):
            continue
        category = min(CLASSES.index(h.removesuffix("_link")) for h in allowed)
        graph.add_edge(u, v, key=key, **edge, category=category)
    component = max(nx.strongly_connected_components(graph), key=len)
    graph = graph.subgraph(component).copy()
    ids = sorted(graph.nodes, key=int)
    index = {node: i for i, node in enumerate(ids)}
    lon = np.array([float(original.nodes[n]["x"]) for n in ids])
    lat = np.array([float(original.nodes[n]["y"]) for n in ids])
    xy = np.rint(np.column_stack(to_xy(lon, lat))).astype(int)
    edges = []
    before, after = 0, 0
    for u, v, edge in graph.edges(data=True):
        a, b = index[u], index[v]
        if "geometry" in edge:
            coords = np.asarray(wkt.loads(edge["geometry"]).coords)
            geometry = np.column_stack(to_xy(coords[:, 0], coords[:, 1]))
        else:
            geometry = xy[[a, b]].astype(float)
        before += len(geometry)
        if np.linalg.norm(geometry[-1]-xy[a]) < np.linalg.norm(geometry[0]-xy[a]):
            geometry = geometry[::-1]
        geometry[0], geometry[-1] = xy[a], xy[b]
        simple = np.rint(np.asarray(LineString(geometry).simplify(15, preserve_topology=False).coords)).astype(int)
        after += len(simple)
        length = max(1, int(np.ceil(np.linalg.norm(np.diff(simple, axis=0), axis=1).sum())))
        # Endpoint coordinates are already stored as nodes. Only interior points are repeated.
        edges.append([a, b, edge["category"], length, *simple[1:-1].ravel().tolist()])
    cx, cy = to_xy(np.array(cells["lon"]), np.array(cells["lat"]))
    distance, snap = cKDTree(xy).query(np.column_stack((cx, cy)))
    graph_data = dict(nodes=xy.ravel().tolist(), edges=edges, cellNodes=snap.tolist(),
                      attribution="Map data © OpenStreetMap contributors (ODbL)",
                      toleranceMetres=15, projection="pipeline.grid local equirectangular, integer metres")
    road_bytes = len(json.dumps(graph_data, separators=(",", ":")).encode())
    assert road_bytes < 3_000_000, road_bytes
    pd.DataFrame(dict(cell=cells["cell"], node=snap, node_x=xy[snap, 0], node_y=xy[snap, 1],
                      snap_metres=distance)).to_csv(TABLES / "storm_builder_cell_nodes.csv", index=False)
    report = dict(source_nodes=len(original), source_edges=original.number_of_edges(), nodes=len(ids),
                  directed_edges=len(edges), geometry_points_before=before, geometry_points_after=after,
                  inlined_road_bytes=road_bytes, max_snap_metres=float(distance.max()),
                  median_snap_metres=float(np.median(distance)), disconnected_cell_pairs=0,
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    print("roads", report, flush=True)
    return graph_data, report


def baseline(cells):
    """Export the EXISTING separable Poisson predictions; do not fit a new model."""
    order = cells["cell"]
    levels = pd.read_csv(TABLES / "baseline_regime_levels_30.csv").set_index("regime_id").log_level
    regimes = pd.read_csv(ROOT / "data/interim/feed_regimes.csv", parse_dates=["start", "end"])
    normal = regimes[(regimes.kind == "regime") & regimes.level_ratio.between(.8, 1.25) &
                     (regimes.start <= "2025-03-31") & (regimes.end >= "2022-04-01")]
    normal_level = float(np.exp(levels.reindex(normal.regime_id).median()))
    probe = pd.Timestamp("2023-07-12 12:00")
    p = pd.read_parquet(ROOT / "data/interim/panel30_2023.parquet", columns=["ts", "cell", "baseline"],
                        filters=[("ts", "==", probe)]).set_index("cell").reindex(order)
    ratios = p.baseline.to_numpy()/p.baseline.iloc[0]
    pieces = []
    for year in range(2022, 2026):
        p = pd.read_parquet(ROOT / f"data/interim/panel30_{year}.parquet",
                            columns=["ts", "cell", "baseline", "regime_id", "drop_main"],
                            filters=[("cell", "==", order[0]), ("ts", ">=", pd.Timestamp("2022-04-01")),
                                     ("ts", "<", pd.Timestamp("2025-04-01")), ("drop_main", "==", False)])
        p["normal"] = p.baseline/np.exp(p.regime_id.map(levels))
        p["dow"] = p.ts.dt.day_of_week
        p["half"] = p.ts.dt.hour*2+p.ts.dt.minute//30
        p["month"] = p.ts.dt.month
        pieces.append(p)
    p = pd.concat(pieces)
    # Equal weighting across months/days, independent of rain or outcome selection.
    h = p.groupby(["month", "dow", "half"]).normal.mean().reset_index()
    h["weekend"] = (h.dow >= 5).astype(int)
    ref = h.groupby(["weekend", "half"]).normal.mean()
    assert len(ref) == 96 and np.isfinite(ratios).all()
    profile = [np.round(ref.loc[w].reindex(range(48)).to_numpy()[:, None]*ratios[None, :]*normal_level, 3).tolist()
               for w in (0, 1)]
    report = dict(source="frozen step-5 predictions; cell ratios and how×month pattern, no refit",
                  calendar="equal-month mean of Monday-Friday / Saturday-Sunday half-hours",
                  normal_regime_multiplier=normal_level, reference_cell=order[0],
                  profiles=96, fit_start="2022-04-01", fit_end="2025-03-31")
    return profile, report


LANDUSE = {"green": {"PARK", "OPEN SPACE", "RESERVE SITE", "AGRICULTURE", "CEMETERY", "SPORTS & RECREATION"},
           "sand": {"BEACH AREA"}, "water": {"WATERBODY"},
           "industry": {"BUSINESS 1", "BUSINESS 2", "BUSINESS 1 - WHITE", "BUSINESS 2 - WHITE", "UTILITY",
                        "PORT / AIRPORT", "SPECIAL USE"}}


def landuse():
    """URA Master Plan 2019 land use, dissolved into a few drawing classes and simplified (presentation only)."""
    import geopandas as gpd
    from shapely import ops
    d = pd.read_parquet(ROOT / "data/static/phase2/landuse.parquet")
    g = gpd.GeoDataFrame(d.drop(columns="geometry"), geometry=gpd.GeoSeries.from_wkb(d.geometry), crs=4326)
    g = g[g.LU_DESC != "ROAD"]
    cls = g.LU_DESC.map(lambda v: next((k for k, s in LANDUSE.items() if v in s), "urban"))
    project = lambda x, y, z=None: to_xy(np.asarray(x), np.asarray(y))
    out, report = {}, {}
    for name in ("urban", "industry", "green", "sand", "water"):
        geom = ops.transform(project, g[cls == name].geometry.buffer(0).union_all())
        geom = geom.buffer(6).buffer(-6).simplify(18, preserve_topology=True)
        polys = [p for p in getattr(geom, "geoms", [geom]) if p.area > 3000]
        rings = []
        for p in polys:
            rings.append([np.rint(np.asarray(r.coords)[:-1]).astype(int).ravel().tolist()
                          for r in [p.exterior, *[i for i in p.interiors if i.area > 3000]]])
        out[name] = rings
        report[name] = dict(polygons=len(rings), points=sum(len(r) // 2 for p in rings for r in p))
    print("landuse", report, flush=True)
    return out, report


def main():
    OUT.mkdir(exist_ok=True)
    frozen = json.loads((ROOT / "sim/v2/data.json").read_text())
    cells = {k: frozen["cells"][k] for k in ("cell", "lon", "lat", "stands", "centre", "place")}
    cx, cy = to_xy(cells["lon"], cells["lat"])
    cells["x"], cells["y"] = np.rint(cx).astype(int).tolist(), np.rint(cy).astype(int).tolist()
    road, road_report = roads(cells)
    profiles, baseline_report = baseline(cells)
    landuse_layers, landuse_report = landuse()
    # World needs stands plus the cell ID. All tuned weights and drive times are reused unchanged.
    land = []
    for ring in frozen["land"]:
        r = np.asarray(ring); x, y = to_xy(r[:, 0], r[:, 1])
        land.append(np.rint(np.column_stack((x, y))).astype(int).tolist())
    data = dict(cells=cells, T=frozen["T"], weights=frozen["weights"], off_scale=frozen["off_scale"],
                road=road, profiles=profiles, land=land, landuse=landuse_layers,
                tuned=pd.read_csv(TABLES / "sim2_tuning.csv").to_dict("records"),
                share=float(frozen["storms"][0]["share"]), baselineNote=baseline_report,
                projection=dict(lon0=LON0,lat0=LAT0,metresLon=M_PER_DEG_LON,metresLat=M_PER_DEG_LAT))
    data_json = json.dumps(data, separators=(",", ":"), allow_nan=False)
    (OUT / "data.json").write_text(data_json)
    html = (OUT / "template.html").read_text()
    for marker, value in (("/*__DATA__*/", "const DATA="+data_json+";"),
                          ("/*__ENGINE__*/", (ROOT / "sim/v2/engine_v2.js").read_text()),
                          ("/*__ROUTER__*/", (OUT / "roads.js").read_text()),
                          ("/*__SCENARIO__*/", (OUT / "scenario.js").read_text()),
                          ("/*__PLANNER__*/", (OUT / "planner.js").read_text()),
                          ("/*__APP__*/", (OUT / "app.js").read_text())):
        assert marker in html, marker
        html = html.replace(marker, value)
    size = len(html.encode())
    assert size < 10_000_000
    (OUT / "index.html").write_text(html)
    report = {**road_report, "landuse": landuse_report, "html_bytes": size, "data_bytes": len(data_json.encode()),
              "baseline": baseline_report, "engine_sha256": hashlib.sha256((ROOT / "sim/v2/engine_v2.js").read_bytes()).hexdigest()}
    (TABLES / "storm_builder_build.json").write_text(json.dumps(report, indent=2))
    print("HTML bytes", size, flush=True)


if __name__ == "__main__":
    main()
