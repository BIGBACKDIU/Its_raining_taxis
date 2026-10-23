"""Step 10: name every cell and describe the geography of supply and rain sensitivity (pre-registration:
outputs/decisions.md items 98-101). Fit period Apr 2022 - Mar 2025, main sample; supply associations only.

Outputs (outputs/tables/): names_cells.csv, rain_hit_top30_absolute.csv, rain_hit_top30_share.csv,
rain_sensitive_type0.csv, rain_gainers.csv, cell_rain_effects.csv, dry_supply_by_band.csv, taxi_deserts.csv
Figures: names_rain_hit_map, dry_supply_by_band, taxi_deserts_map
Usage: .venv/bin/python -m analysis.10_names
"""
from __future__ import annotations

import importlib

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Patch

from analysis import geo
from analysis.common import (BLUE_DARK, FIT, INK, INTERIM, MUTED, NOT_ANALYSED, ORANGE, SEED, TABLES, load_panel,
                             save, style)
from pipeline.grid import to_lonlat

B_BOOT = 1000
BANDS = [("07-10", 7, 10), ("10-17", 10, 17), ("17-20", 17, 20), ("20-24", 20, 24), ("00-07", 0, 7)]


def names_table():
    seen = pd.read_parquet(INTERIM / "cells.parquet")[["cell", "lon", "lat", "eligible", "mean_fit"]]
    lc = geo.land_cells()[["cell", "lon", "lat", "subzone", "planning_area", "region"]]
    allc = pd.concat([lc.assign(land=True), seen[~seen.cell.isin(lc.cell)][["cell", "lon", "lat"]].assign(land=False)],
                     ignore_index=True)
    miss = allc.subzone.isna()
    if miss.any():                               # centres at sea / outside subzones: nearest subzone
        pts = gpd.GeoDataFrame(allc[miss][["cell"]], geometry=gpd.points_from_xy(allc[miss].lon, allc[miss].lat), crs=4326)
        nn = gpd.sjoin_nearest(pts.to_crs(geo.CRS), geo.subzones().to_crs(geo.CRS), how="left").drop_duplicates("cell")
        allc.loc[miss, ["subzone", "planning_area", "region"]] = nn[["subzone", "planning_area", "region"]].values
    allc = allc.merge(seen[["cell", "eligible", "mean_fit"]], on="cell", how="left")
    allc["eligible"] = allc.eligible.fillna(False).astype(bool)
    allc["mean_fit"] = allc.mean_fit.fillna(0.0)
    allc["nearest_mrt"] = geo.nearest_mrt(allc.lon, allc.lat)
    allc["landmarks"] = geo.landmarks(allc.lon, allc.lat)
    allc["place"] = allc.apply(geo.place_label, axis=1)
    allc.to_csv(TABLES / "names_cells.csv", index=False)
    return allc


def cell_effects(names):
    inf = importlib.import_module("analysis.04_inference")
    p = inf.load()
    f0, _ = inf.fit0(p)
    p["fit0"] = f0
    p = p[np.isfinite(p.fit0)].reset_index(drop=True)
    tot = p.groupby("ts")[["vacant", "fit0"]].transform("sum")
    p["fit0s"] = p.fit0 * tot.vacant / tot.fit0
    h = p[p.rain_band == 3]
    days = np.sort(h.ts.dt.normalize().unique())
    di = np.searchsorted(days, h.ts.dt.normalize().values)
    cc, cl = pd.factorize(h.cell)
    D, C = len(days), len(cl)
    M = {}
    for col in ("vacant", "fit0", "fit0s"):
        A = np.zeros((D, C))
        np.add.at(A, (di, cc), h[col].values)
        M[col] = A
    n_rows = np.bincount(cc, minlength=C)
    n_slots = h.groupby("cell").ts.nunique().reindex(cl).values
    rng = np.random.default_rng(SEED)
    W = rng.multinomial(D, np.full(D, 1 / D), size=B_BOOT).astype(float)
    V, F, Fs = (M[k].sum(0) for k in ("vacant", "fit0", "fit0s"))
    with np.errstate(divide="ignore", invalid="ignore"):
        ba = (W @ M["vacant"]) / (W @ M["fit0"]) - 1
        bs = (W @ M["vacant"]) / (W @ M["fit0s"]) - 1
    e = pd.DataFrame({"cell": cl, "heavy_rows": n_rows, "heavy_half_hours": n_slots,
                      "expected_vacant_heavy": F / n_slots,
                      "taxis_lost_per_heavy_half_hour": (F - V) / n_slots,
                      "abs_pct": 100 * (V / F - 1), "abs_lo": 100 * np.nanquantile(ba, 0.025, 0),
                      "abs_hi": 100 * np.nanquantile(ba, 0.975, 0), "share_pct": 100 * (V / Fs - 1),
                      "share_lo": 100 * np.nanquantile(bs, 0.025, 0), "share_hi": 100 * np.nanquantile(bs, 0.975, 0)})
    e["tested"] = e.heavy_rows >= 100
    # absolute change in taxis per heavy-rain half-hour with its day-bootstrap CI (shown beside share results)
    e["abs_change_per_half_hour"] = (V - F) / n_slots
    e["abs_change_lo"] = e.abs_lo / 100 * e.expected_vacant_heavy
    e["abs_change_hi"] = e.abs_hi / 100 * e.expected_vacant_heavy
    # two-sided day-bootstrap p-values and Benjamini-Hochberg q-values across tested cells (decision 133)
    for k, b in (("abs", ba), ("share", bs)):
        p_ = 2 * np.minimum(np.nanmean(b >= 0, 0), np.nanmean(b <= 0, 0))
        e[f"{k}_p"] = np.clip(p_, 1 / B_BOOT, 1)
        e[f"{k}_q"] = np.nan
        t = e.tested.values
        e.loc[t, f"{k}_q"] = bh(e.loc[t, f"{k}_p"].values)
    e["presentable_abs"] = e.tested & (e.expected_vacant_heavy >= 4) & (e.abs_q < 0.10)
    e["presentable_share"] = e.tested & (e.expected_vacant_heavy >= 4) & (e.share_q < 0.10)
    e = e.merge(names[["cell", "planning_area", "subzone", "nearest_mrt", "landmarks", "place", "lon", "lat"]],
                on="cell", how="left")
    e.to_csv(TABLES / "cell_rain_effects.csv", index=False, float_format="%.4f")
    return e, p


def bh(p):
    """Benjamini-Hochberg q-values."""
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = np.empty(n)
    q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def named(t, cols):
    keep = ["rank", "planning_area", "subzone", "nearest_mrt", "landmarks"] + cols
    t = t.copy()
    t.insert(0, "rank", np.arange(1, len(t) + 1))
    t["planning_area"] = t.planning_area.str.title().str.replace("'S", "'s")
    t["subzone"] = t.subzone.str.title().str.replace("'S", "'s")
    return t[keep + ["cell"]]


ABS_COLS = ["abs_change_per_half_hour", "abs_change_lo", "abs_change_hi"]


def rankings(e):
    """Presentation lists: tested cells with >= 4 expected vacant taxis in heavy rain and a BH q < 0.10 effect;
    the full sorted lists are kept as appendix tables (*_all.csv)."""
    tested = e[e.tested]
    cols_a = ["taxis_lost_per_heavy_half_hour", "expected_vacant_heavy", "abs_pct", "abs_lo", "abs_hi", "abs_q"]
    full = tested.sort_values("taxis_lost_per_heavy_half_hour", ascending=False)
    named(full, cols_a + ["presentable_abs"]).to_csv(TABLES / "rain_hit_absolute_all.csv", index=False, float_format="%.3f")
    a = named(full[full.presentable_abs].head(30), cols_a)
    a.to_csv(TABLES / "rain_hit_top30_absolute.csv", index=False, float_format="%.2f")
    cols_s = ["share_pct", "share_lo", "share_hi", "share_q", "expected_vacant_heavy"] + ABS_COLS + ["abs_pct"]
    full = tested.sort_values("share_pct")
    named(full, cols_s + ["presentable_share"]).to_csv(TABLES / "rain_hit_share_all.csv", index=False, float_format="%.3f")
    s = named(full[full.presentable_share & (full.share_hi < 0)].head(30), cols_s)
    s.to_csv(TABLES / "rain_hit_top30_share.csv", index=False, float_format="%.2f")
    ty = pd.read_csv(TABLES / "risk_types.csv")
    t0 = e.merge(ty[["cell", "type"]], on="cell")
    t0 = named(t0[t0.type == 0].sort_values("abs_pct"), ["abs_pct", "abs_lo", "abs_hi", "share_pct",
                                                          "taxis_lost_per_heavy_half_hour"])
    t0.to_csv(TABLES / "rain_sensitive_type0.csv", index=False, float_format="%.2f")
    hs = pd.read_csv(TABLES / "inference_hotspots.csv").set_index("cell").hotspot
    g = tested[(tested.share_lo > 0) | (tested.cell.map(hs) == "significantly higher")].sort_values("share_pct",
                                                                                                   ascending=False)
    cols_g = ["share_pct", "share_lo", "share_hi", "share_q", "expected_vacant_heavy"] + ABS_COLS + \
        ["abs_pct", "abs_lo", "abs_hi", "presentable_share"]
    g = named(g, cols_g)
    # gaining share is not gaining taxis: flag cells whose absolute count rises with a CI above 0
    g["absolute_gain"] = g.abs_change_lo > 0
    g.to_csv(TABLES / "rain_gainers.csv", index=False, float_format="%.2f")
    return a, s, t0, g


def dry_supply(p, names):
    reg = pd.read_csv(INTERIM / "feed_regimes.csv").set_index("regime_id").level_ratio
    dry = (p.mmh == 0) & (p.mmh_lag1 == 0) & (p.mmh_lag2 == 0) & p.regime_id.map(reg).between(0.8, 1.25)
    q = p[dry]
    hr = q.ts.dt.hour
    rows = []
    for lab, a, b in BANDS:
        m = (hr >= a) & (hr < b)
        s = q[m].groupby("cell").vacant.mean().rename("mean_vacant_dry").reset_index()
        s["band"] = lab
        rows.append(s)
    t = pd.concat(rows).merge(names[["cell", "planning_area", "subzone", "place", "lon", "lat"]], on="cell")
    t.to_csv(TABLES / "dry_supply_by_band.csv", index=False, float_format="%.3f")
    allday = q.groupby("cell").vacant.mean().rename("dry_mean_vacant")       # all hours, dry snapshots only
    allday.to_csv(TABLES / "dry_supply_all_hours.csv", float_format="%.4f")
    return t


def deserts(names):
    r = geo.residents_by_cell()
    t = names[names.land].merge(r, on="cell", how="left").fillna({"residents": 0, "age65": 0})
    hdb = geo.P2 / "hdb_blocks_geocoded.csv"
    if hdb.exists():
        b = pd.read_csv(hdb).dropna(subset=["lat", "lon"])
        from pipeline.grid import cell_ids, coarsen
        b["cell"] = coarsen(cell_ids(b.lon.values, b.lat.values, 500))
        t["hdb_units"] = t.cell.map(b.groupby("cell").total_dwelling_units.sum()).fillna(0)
    else:
        t["hdb_units"] = np.nan
    # dry-weather supply (decision 134): mean vacant taxis over dry, normal-coverage snapshots, all hours
    dm = pd.read_csv(TABLES / "dry_supply_all_hours.csv").set_index("cell").dry_mean_vacant
    t["dry_mean_vacant"] = t.cell.map(dm)
    t["vacant_per_10k_residents"] = np.where(t.residents > 0, t.dry_mean_vacant / t.residents * 1e4, np.nan)
    cand = t[((t.residents >= 5000) | (t.hdb_units.fillna(0) >= 2000)) & t.dry_mean_vacant.notna()]
    d = cand.sort_values("vacant_per_10k_residents").head(25)
    d = named(d, ["residents", "hdb_units", "share_65plus", "dry_mean_vacant", "vacant_per_10k_residents", "eligible"])
    d.to_csv(TABLES / "taxi_deserts.csv", index=False, float_format="%.3f")
    t.to_csv(TABLES / "cells_residents_supply.csv", index=False, float_format="%.3f")
    return d, t


# ----------------------------------------------------------------------------- maps
def draw_cells(ax, cells, values, cmap, norm, grey=None):
    for c, v in zip(cells, values):
        x, y = c // 1000, c % 1000
        lon0, lat0 = to_lonlat(x * 1000, y * 1000)
        lon1, lat1 = to_lonlat((x + 1) * 1000, (y + 1) * 1000)
        col = NOT_ANALYSED if (v is None or not np.isfinite(v)) else cmap(norm(v))
        ax.add_patch(plt.Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0, facecolor=col, edgecolor="white", lw=0.3,
                                   zorder=2))


def short(text, n=34):
    """Shorten a place label at a word boundary, closing an open bracket."""
    text = str(text)
    if len(text) <= n:
        return text
    cut = text[:n - 1].rsplit(" ", 1)[0].rstrip(",;( ")
    return cut + ("...)" if cut.count("(") > cut.count(")") else "...")


def label(ax, df, text_col, n, fs=6.5, loc="upper left", width=40):
    """Numbered markers on the map and a numbered key in a corner box (no overlapping place labels)."""
    rows = list(df.head(n).itertuples())
    for k, r in enumerate(rows, 1):
        ax.plot(r.lon, r.lat, "o", ms=7, mfc="white", mec=INK, mew=0.8, zorder=5)
        ax.annotate(str(k), (r.lon, r.lat), ha="center", va="center", fontsize=fs - 1.5, color=INK, zorder=6)
    key = "\n".join(f"{k}  {short(getattr(r, text_col), width)}" for k, r in enumerate(rows, 1))
    x, ha = (0.01, "left") if "left" in loc else (0.99, "right")
    y, va = (0.01, "bottom") if "lower" in loc else (0.99, "top")
    ax.text(x, y, key, transform=ax.transAxes, ha=ha, va=va, fontsize=fs, color=INK, zorder=7, linespacing=1.35,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#d9d8d4", alpha=0.92))


def maps(e, ds, deserts_t, names):
    d02 = importlib.import_module("analysis.02_describe")
    div = LinearSegmentedColormap.from_list("d", ["#b8431c", ORANGE, "#f2f1ed", "#7fb0e8", BLUE_DARK])
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.2))
    for ax, col, title in ((axes[0], "abs_pct", "Heavy rain vs no-rain model: % vacant taxis"),
                           (axes[1], "share_pct", "Heavy rain: % change in the cell's share of citywide vacant taxis")):
        d02.draw_base(ax)
        norm = TwoSlopeNorm(vcenter=0, vmin=-40, vmax=20)
        t = e[e.tested]
        draw_cells(ax, t.cell.values, t[col].clip(-40, 20).values, div, norm)
        t_lab = t[t.presentable_abs] if col == "abs_pct" else t[t.presentable_share & (t.share_hi < 0)]
        lab = t_lab.sort_values("taxis_lost_per_heavy_half_hour" if col == "abs_pct" else "share_pct",
                            ascending=col != "abs_pct")
        label(ax, lab.assign(short=lab.place), "short", 10)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=div), ax=ax, orientation="horizontal", fraction=0.05,
                     pad=0.02, label="%")
        ax.set_title(title, fontsize=9.5)
    fig.suptitle("Where heavy rain goes with the fewest vacant taxis (labels: 10 largest losses among cells with >= 4 "
                 "expected taxis and FDR q < 0.10)", x=0.01, ha="left",
                 fontsize=10.5)
    fig.tight_layout()
    save(fig, "names_rain_hit_map", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, URA MP2019, OSM. "
         "Apr 2022 - Mar 2025; cells with >= 100 heavy-rain rows. Association, not cause.")
    plt.close(fig)
    blues = LinearSegmentedColormap.from_list("b", ["#e3eefb", "#a9c9ef", "#2a78d6", "#0d2f5c"])
    norm = BoundaryNorm([0, 1, 2, 4, 8, 16, 32, 64], blues.N, extend="max")
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5))
    for ax, (lab, _, _) in zip(axes.ravel(), BANDS):
        d02.draw_base(ax)
        t = ds[ds.band == lab]
        draw_cells(ax, t.cell.values, t.mean_vacant_dry.values, blues, norm)
        tt = t.sort_values("mean_vacant_dry", ascending=False)
        label(ax, tt.assign(short=tt.place), "short", 8, fs=6)
        ax.set_title(f"Dry weather, {lab}", fontsize=9.5)
    ax = axes.ravel()[-1]
    ax.axis("off")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=blues), ax=ax, orientation="horizontal", fraction=0.3,
                 label="Mean vacant taxis per 1 km cell (dry, normal-coverage regimes)")
    fig.suptitle("Dry-weather supply by time of day; labels: 8 best-supplied cells", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "dry_supply_by_band", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, URA MP2019, OSM. "
         "Apr 2022 - Mar 2025, no rain at the cell for 90 min.")
    plt.close(fig)
    t = deserts_t
    oranges = LinearSegmentedColormap.from_list("o", ["#fbe3d6", ORANGE, "#8a2f10"])
    fig, ax = plt.subplots(figsize=(9, 5.4))
    d02.draw_base(ax)
    v = np.where(t.residents >= 2000, np.log10(np.maximum(t.vacant_per_10k_residents, 0.01)), np.nan)
    norm = TwoSlopeNorm(vcenter=np.log10(5), vmin=-2, vmax=np.log10(200))
    draw_cells(ax, t.cell.values, v, LinearSegmentedColormap.from_list("r", ["#8a2f10", ORANGE, "#f2f1ed", "#7fb0e8",
                                                                             BLUE_DARK]), norm)
    dd = deserts_t.merge(names[["cell"]], on="cell").sort_values("vacant_per_10k_residents")
    dd = dd[((dd.residents >= 5000) | (dd.hdb_units.fillna(0) >= 2000)) & dd.dry_mean_vacant.notna()]
    label(ax, dd.assign(short=dd.subzone.str.title().str.replace("'S", "'s")), "short", 12)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=LinearSegmentedColormap.from_list("r", ["#8a2f10", ORANGE, "#f2f1ed",
                                                                                       "#7fb0e8", BLUE_DARK]))
    cb = fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.05, pad=0.02)
    cb.set_ticks(np.log10([0.01, 0.1, 1, 5, 20, 100]), labels=["0.01", "0.1", "1", "5", "20", "100"])
    cb.set_label("Dry-weather mean vacant taxis per 10,000 residents (analysed cells with >= 2,000 residents)")
    ax.set_title("Dry-weather taxi deserts: residential areas with the fewest vacant taxis per resident (labels: 12 lowest)",
                 fontsize=10)
    fig.tight_layout()
    save(fig, "taxi_deserts_map", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, Census 2020 (SingStat), "
         "URA MP2019, HDB. Apr 2022 - Mar 2025, snapshots with no rain at the cell for 90 min, normal-coverage regimes; "
         "residents allocated to cells by residential land-use area.")
    plt.close(fig)


def main():
    style()
    names = names_table()
    print("named cells:", len(names), "with landmarks:", int((names.landmarks != "").sum()), flush=True)
    e, p = cell_effects(names)
    a, s, t0, g = rankings(e)
    print(a.head(10)[["rank", "planning_area", "subzone", "landmarks", "taxis_lost_per_heavy_half_hour", "abs_pct",
                      "abs_lo", "abs_hi"]].round(2).to_string(index=False))
    print(s.head(10)[["rank", "planning_area", "subzone", "share_pct", "share_lo", "share_hi"]].round(2).to_string(index=False))
    print("type 0 cells:", len(t0), " gainers:", len(g))
    print(g[["planning_area", "subzone", "landmarks", "share_pct", "share_lo", "share_hi"]].round(2).to_string(index=False))
    ds = dry_supply(p, names)
    del p
    d, t = deserts(names)
    print(d[["rank", "planning_area", "subzone", "residents", "hdb_units", "dry_mean_vacant", "vacant_per_10k_residents"]]
          .round(2).to_string(index=False))
    maps(e, ds, t, names)


if __name__ == "__main__":
    main()
