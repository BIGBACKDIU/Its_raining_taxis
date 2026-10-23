"""Step 2: describe availability in dry and rainy conditions (HANDOFF section 6, step 2).

All availability comparisons use the ratio of vacant taxis to the expected baseline (which carries the
coverage-regime level), so feed coverage changes do not show up as rain effects. Main sample only
(drop_main == False), fit period (Apr 2022 - Mar 2025) unless stated.

Charts (outputs/figures/): desc_profile_rain_bands, desc_maps_dry_heavy, desc_storm_<date>.gif (+ key frame),
desc_trend_vs_fleet, desc_rain_band_frequency. Tables (outputs/tables/): desc_*.csv

Usage: .venv/bin/python -m analysis.02_describe
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Patch

from analysis.common import (BAND_COLORS, BLUE, BLUE_DARK, FIT, FIGS, INK, INTERIM, MUTED, NOT_ANALYSED, ORANGE,
                             RAIN_BANDS, SEED, STATIC, TABLES, cells, load_panel, save, style)
from pipeline.grid import to_lonlat

COLS = ["ts", "date", "cell", "vacant", "baseline", "rain_band", "mmh", "hod", "dow", "daytype", "drop_main",
        "regime_id", "ym"]


def fit_panel(columns=COLS):
    p = load_panel(range(2022, 2026), columns=columns)
    p = p[(p.ts >= FIT[0]) & (p.ts <= FIT[1]) & ~p.drop_main & (p.rain_band >= 0) & p.baseline.notna()]
    return p


# ----------------------------------------------------------------------------- 1. profiles
def profiles(p: pd.DataFrame, n_boot=200):
    """Ratio sum(vacant) / sum(baseline) by 2-hour block of day x weekday/weekend x rain band, with day-bootstrap 95% CI."""
    p = p.assign(hour=(p.hod // 4) * 2, wk=np.where(p.daytype == 0, "Weekday", "Weekend or holiday"))
    d = p.groupby(["date", "wk", "hour", "rain_band"], observed=True)[["vacant", "baseline"]].sum().reset_index()
    rng = np.random.default_rng(SEED)
    days = d.date.unique()
    est = d.groupby(["wk", "hour", "rain_band"])[["vacant", "baseline"]].sum()
    est["ratio"] = est.vacant / est.baseline
    boots = []
    dd = d.set_index("date")
    for b in range(n_boot):
        pick = pd.Series(rng.choice(days, len(days), replace=True))
        w = pick.value_counts()
        x = dd.loc[dd.index.isin(w.index)].copy()
        x["w"] = x.index.map(w)
        g = x.assign(v=x.vacant * x.w, bb=x.baseline * x.w).groupby(["wk", "hour", "rain_band"])[["v", "bb"]].sum()
        boots.append(g.v / g.bb)
    B = pd.concat(boots, axis=1)
    est["lo"], est["hi"] = B.quantile(0.025, axis=1), B.quantile(0.975, axis=1)
    est["cell_snapshots"] = p.groupby(["wk", "hour", "rain_band"]).size()
    est = est.reset_index()
    est["band"] = est.rain_band.map(dict(enumerate(RAIN_BANDS)))
    est.to_csv(TABLES / "desc_profile_rain_bands.csv", index=False, float_format="%.4f")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, wk in zip(axes, ["Weekday", "Weekend or holiday"]):
        for b, name in enumerate(RAIN_BANDS):
            e = est[(est.wk == wk) & (est.rain_band == b) & (est.cell_snapshots >= 200)]
            ax.fill_between(e.hour, e.lo * 100, e.hi * 100, color=BAND_COLORS[name], alpha=0.25, lw=0)
            ax.plot(e.hour, e.ratio * 100, color=BAND_COLORS[name], lw=2, label=name.capitalize())
        ax.axhline(100, color=MUTED, lw=0.8, ls="--")
        ax.set_title(wk, fontsize=9.5)
        ax.set_xticks(range(0, 24, 3), [f"{h:02d}:00" for h in range(0, 24, 3)])
        ax.set_xlabel("Hour of day (2-hour blocks, start time)")
    axes[0].set_ylabel("Vacant taxis as % of expected level")
    axes[0].legend(title="Rain in previous 30 min", fontsize=8, title_fontsize=8, loc="lower left")
    fig.suptitle("In rain, cells hold about 5-20% fewer vacant taxis than expected at most times of day",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    save(fig, "desc_profile_rain_bands", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025, "
         "1 km cells, nearest working gauge. Bands: light <= 2.5, moderate <= 10, heavy > 10 mm/h. 95% day-bootstrap bands.")
    plt.close(fig)
    return est


# ----------------------------------------------------------------------------- 2. maps
def draw_base(ax):
    m = json.load(open(STATIC / "sg_map.json"))
    for ring in m["land"]:
        r = np.asarray(ring)
        ax.fill(r[:, 0], r[:, 1], color="#f4f3f0", lw=0, zorder=0)
        ax.plot(r[:, 0], r[:, 1], color="#bdbcb7", lw=0.4, zorder=1)
    ax.set_aspect(1 / np.cos(np.deg2rad(1.35)))
    ax.set_xlim(103.6, 104.05)
    ax.set_ylim(1.215, 1.475)
    ax.axis("off")


def cell_squares(ax, cell_ids, values, cmap, norm, allc):
    cx, cy = cell_ids // 1000, cell_ids % 1000
    for c, x, y, v in zip(cell_ids, cx, cy, values):
        lon0, lat0 = to_lonlat(x * 1000, y * 1000)
        lon1, lat1 = to_lonlat((x + 1) * 1000, (y + 1) * 1000)
        col = NOT_ANALYSED if (v is None or np.isnan(v)) else cmap(norm(v))
        ax.add_patch(plt.Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0, facecolor=col, edgecolor="white",
                                   lw=0.3, zorder=2))
    # not analysed: cells seen in the feed but not eligible
    ne = allc[~allc.eligible]
    for x, y in zip(ne.cx, ne.cy):
        lon0, lat0 = to_lonlat(x * 1000, y * 1000)
        lon1, lat1 = to_lonlat((x + 1) * 1000, (y + 1) * 1000)
        ax.add_patch(plt.Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0, facecolor=NOT_ANALYSED,
                                   edgecolor="white", lw=0.3, zorder=2))


def maps(p: pd.DataFrame):
    allc = cells()
    g = p.groupby(["cell", "rain_band"])[["vacant", "baseline"]].sum()
    g["n"] = p.groupby(["cell", "rain_band"]).size()
    r = (g.vacant / g.baseline).unstack()
    n = g.n.unstack()
    # mean vacant per cell in dry and heavy rain, in normal-coverage regimes only (level 0.8-1.25)
    reg = pd.read_csv(INTERIM / "feed_regimes.csv").set_index("regime_id").level_ratio
    normal = p.regime_id.map(reg).between(0.8, 1.25)
    mv = p[normal].groupby(["cell", "rain_band"]).vacant.mean().unstack()
    t = pd.DataFrame({"mean_vacant_dry": mv[0], "mean_vacant_heavy": mv[3], "ratio_dry": r[0], "ratio_heavy": r[3],
                      "n_dry": n[0], "n_heavy": n[3]})
    t["pct_change_heavy_vs_dry"] = 100 * (t.ratio_heavy / t.ratio_dry - 1)
    t.loc[t.n_heavy < 100, "pct_change_heavy_vs_dry"] = np.nan          # too few heavy-rain snapshots
    t.to_csv(TABLES / "desc_maps_dry_heavy.csv", float_format="%.4f")

    blues = LinearSegmentedColormap.from_list("b", ["#e3eefb", "#a9c9ef", "#2a78d6", "#0d2f5c"])
    div = LinearSegmentedColormap.from_list("d", ["#b8431c", ORANGE, "#f2f1ed", "#7fb0e8", BLUE_DARK])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    bounds = [0, 1, 2, 4, 8, 16, 32, 64]
    for ax, col, title in ((axes[0], "mean_vacant_dry", "Dry: mean vacant taxis per 1 km cell"),
                           (axes[1], "mean_vacant_heavy", "Heavy rain (> 10 mm/h): mean vacant taxis")):
        draw_base(ax)
        norm = BoundaryNorm(bounds, blues.N, extend="max")
        cell_squares(ax, t.index.values, t[col].values, blues, norm, allc)
        ax.set_title(title, fontsize=9.5)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=blues)
        fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.05, pad=0.02, label="Vacant taxis (normal-coverage regimes)")
    ax = axes[2]
    draw_base(ax)
    norm = TwoSlopeNorm(vcenter=0, vmin=-60, vmax=20)
    cell_squares(ax, t.index.values, t.pct_change_heavy_vs_dry.clip(-60, 20).values, div, norm, allc)
    ax.set_title("Heavy rain vs dry: % change relative to expected level", fontsize=9.5)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=div)
    fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.05, pad=0.02, label="% change (vacant / expected)")
    axes[2].legend(handles=[Patch(color=NOT_ANALYSED, label="Not analysed")], loc="upper left", fontsize=8)
    med = t.pct_change_heavy_vs_dry.median()
    fig.suptitle(f"In heavy rain most cells have fewer vacant taxis than normal (median cell {med:+.0f}%)",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    save(fig, "desc_maps_dry_heavy", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025. "
         "Grey: not analysed (mean < 0.5 vacant taxis) or < 100 heavy-rain snapshots.")
    plt.close(fig)
    return t


# ----------------------------------------------------------------------------- 3. storm animation
def storm_animation(date="2023-07-20"):
    allc = cells()
    d0 = pd.Timestamp(date)
    p = load_panel([d0.year], columns=["ts", "cell", "vacant", "baseline", "mmh"])
    s = pd.read_csv("data/raw/storm_positions/storm_days.csv", parse_dates=["peak_end"])
    peak = s[s.peak_end.dt.normalize() == d0].peak_end.iloc[0]
    p = p[(p.ts >= peak - pd.Timedelta(hours=3)) & (p.ts <= peak + pd.Timedelta(hours=4))]
    p["pct"] = 100 * (p.vacant / p.baseline.clip(lower=1) - 1)
    times = sorted(p.ts.unique())
    blues = LinearSegmentedColormap.from_list("b", ["#f2f1ed", "#a9c9ef", "#2a78d6", "#0d2f5c"])
    div = LinearSegmentedColormap.from_list("d", ["#b8431c", ORANGE, "#f2f1ed", "#7fb0e8", BLUE_DARK])
    rnorm = BoundaryNorm([0, 0.01, 2.5, 10, 30, 60], blues.N, extend="max")
    pnorm = TwoSlopeNorm(vcenter=0, vmin=-100, vmax=50)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))

    def frame(i):
        for ax in axes:
            ax.clear()
            draw_base(ax)
        f = p[p.ts == times[i]]
        cell_squares(axes[0], f.cell.values, f.mmh.values, blues, rnorm, allc)
        cell_squares(axes[1], f.cell.values, f.pct.clip(-100, 50).values, div, pnorm, allc)
        tt = pd.Timestamp(times[i])
        axes[0].set_title(f"Rain in previous 30 min (mm/h), {tt:%d %b %Y %H:%M}", fontsize=9.5)
        axes[1].set_title(f"Vacant taxis vs expected (%), {tt:%H:%M}", fontsize=9.5)
        return []

    frame(0)
    fig.colorbar(plt.cm.ScalarMappable(norm=rnorm, cmap=blues), ax=axes[0], orientation="horizontal", fraction=0.05,
                 pad=0.02, label="mm/h at nearest working gauge")
    fig.colorbar(plt.cm.ScalarMappable(norm=pnorm, cmap=div), ax=axes[1], orientation="horizontal", fraction=0.05,
                 pad=0.02, label="% vs expected level (grey: not analysed)")
    fig.text(0.01, 0.005, "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Association, not cause.",
             fontsize=7, color=MUTED)
    anim = FuncAnimation(fig, frame, frames=len(times), blit=False)
    anim.save(FIGS / f"desc_storm_{date}.gif", writer=PillowWriter(fps=2))
    # key frame at the rain peak for the report
    frame(times.index(np.datetime64(peak)) if np.datetime64(peak) in times else len(times) // 2)
    for ext in ("png", "svg"):
        fig.savefig(FIGS / f"desc_storm_{date}_peak.{ext}", bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- 4. trend vs fleet
def trend_vs_fleet():
    fd = pd.read_csv(INTERIM / "feed_daily.csv", parse_dates=["date"])
    fd = fd[~fd.regime.eq("spell") & fd.usable]
    feed = fd.set_index("date").median_count.resample("MS").median()
    fl = pd.read_csv(STATIC / "lta_cdg_share_monthly.csv", parse_dates=["month"]).set_index("month")
    base = pd.Timestamp("2022-04-01")
    idx = pd.DataFrame({"feed": feed, "fleet": fl.total_taxis, "street_hail": fl.p2p_daily_trips_street_hail})
    idx = idx[idx.index >= "2021-10-01"]
    idx = 100 * idx / idx.loc[base]
    idx.to_csv(TABLES / "desc_trend_vs_fleet.csv", float_format="%.2f")
    reg = pd.read_csv(INTERIM / "feed_regimes.csv", parse_dates=["start", "end"])
    fig, ax = plt.subplots(figsize=(10, 4))
    for r in reg[reg.kind == "regime"].itertuples():
        if not 0.8 <= r.level_ratio <= 1.25:
            ax.axvspan(r.start, r.end, color="#eef2f7", lw=0, zorder=0)
    ax.plot(idx.index, idx.feed, color=BLUE, lw=2, label="Vacant taxis in feed (monthly median)")
    ax.plot(idx.index, idx.fleet, color=INK, lw=2, label="LTA taxi fleet")
    ax.plot(idx.index, idx.street_hail, color=ORANGE, lw=2, label="Street-hail trips per day (LTA)")
    ax.axhline(100, color=MUTED, lw=0.8, ls="--")
    ax.set_ylabel("Index, Apr 2022 = 100")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("The fleet shrank 18% and street hails more than halved, while the feed's level mostly tracks coverage",
                 fontsize=10.5)
    fig.tight_layout()
    save(fig, "desc_trend_vs_fleet", "Sources: data.gov.sg taxi availability; LTA P2P statistics (fleet by company, "
         "street-hail trips). Shaded: feed regimes outside 0.8-1.25x normal coverage.")
    plt.close(fig)
    return idx


# ----------------------------------------------------------------------------- 5. rain-band frequency
def band_frequency():
    p = load_panel(columns=["ts", "rain_band", "drop_main"])
    p = p[~p.drop_main & (p.rain_band >= 0)]
    t = pd.crosstab(p.ts.dt.year, p.rain_band, normalize="index") * 100
    t.columns = [RAIN_BANDS[c] for c in t.columns]
    t["cell_snapshots"] = p.groupby(p.ts.dt.year).size()
    t.to_csv(TABLES / "desc_rain_band_frequency.csv", float_format="%.3f")
    fig, ax = plt.subplots(figsize=(7, 3.6))
    x = np.arange(len(t))
    w = 0.26
    for k, b in enumerate(["light", "moderate", "heavy"]):
        bars = ax.bar(x + (k - 1) * w, t[b], w - 0.02, color=BAND_COLORS[b], label=b.capitalize())
        ax.bar_label(bars, fmt="%.1f", fontsize=6.5, color=MUTED, padding=1)
    ax.set_xticks(x, [str(y) + ("*" if y in (2021, 2026) else "") for y in t.index])
    ax.set_ylabel("% of cell-snapshots")
    ax.legend(fontsize=8)
    ax.set_title(f"Rain is rare in any given half hour: {100 - t.dry.mean():.1f}% of cell-snapshots are wet", fontsize=10.5)
    fig.tight_layout()
    save(fig, "desc_rain_band_frequency", "Sources: NEA rainfall (nearest working gauge, previous 30 min), 1 km cells, "
         "main sample. *2021: Oct-Dec only; 2026: Jan-Sep.")
    plt.close(fig)
    return t


def main():
    style()
    p = fit_panel()
    print("fit-period main-sample rows:", len(p))
    est = profiles(p)
    print(est[(est.wk == "Weekday") & est.hour.isin([8, 18])][["hour", "band", "ratio", "lo", "hi"]].round(3).to_string())
    t = maps(p)
    print(t.describe().round(2).to_string())
    del p
    storm_animation()
    print(trend_vs_fleet().iloc[::6].round(1).to_string())
    print(band_frequency().round(3).to_string())


if __name__ == "__main__":
    main()
