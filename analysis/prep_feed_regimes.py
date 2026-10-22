"""Detect coverage regimes in the vacant-taxi feed (HANDOFF section 3a).

The citywide number of vacant taxis jumps between levels that do not look like real market
changes (e.g. roughly x0.55 in Aug-Nov 2022, roughly x2 in Oct-Dec 2025). This script

1. builds a daily coverage index: each snapshot's citywide count divided by the median count
   for its half-hour-of-week slot (so time-of-day and day-of-week drop out), then the daily
   median of the log ratio;
2. finds change points in that index with PELT (ruptures, L2 cost);
3. merges neighbouring segments whose levels differ by less than MERGE_TOL, and labels
   segments shorter than MIN_REGIME_DAYS either "spell" (an anomalous short level, excluded
   from modelling) or folds them into the neighbouring regime if they are not anomalous;
4. checks whether cell-level shares of the citywide count are stable across each boundary
   (the share-of-citywide model relies on this);
5. summarises the duplicate-coordinate check on raw positions saved in data/raw/feed_check/.

Outputs: data/interim/feed_daily.csv, data/interim/feed_regimes.csv,
outputs/tables/feed_regimes.csv, outputs/tables/feed_share_stability.csv,
outputs/tables/feed_duplicate_check.csv, outputs/figures/feed_regimes.png/.svg

Usage: .venv/bin/python -m analysis.prep_feed_regimes
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import ruptures as rpt
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from pipeline.grid import coarsen, to_xy

RAW = Path("data/raw/taxi")
INTERIM = Path("data/interim")
TABLES = Path("outputs/tables")
FIGS = Path("outputs/figures")
MAX_OFFSET_MIN = 10        # HANDOFF 3a: drop snapshots more than 10 min off
MIN_DAY_SHARE = 0.5        # a day needs half its snapshots to get an index value
MERGE_TOL = 0.10           # log-level difference below which neighbouring segments merge (~10%)
PEN_MULT = 40              # PELT penalty = PEN_MULT * sigma^2 * log(n); daily noise is autocorrelated, so BIC (2-3) over-splits
DAY_TOL = 0.35             # a single day this far (log) from its regime level is flagged anomalous
MIN_REGIME_DAYS = 14       # shorter segments are not regimes
SPELL_TOL = 0.15           # a short segment this far (log) from both neighbours is an anomalous spell

BLUE, BLUE_LIGHT, ORANGE, INK, MUTED = "#2a78d6", "#a9c9ef", "#eb6834", "#0b0b0b", "#52514e"


def load_snapshots() -> pd.DataFrame:
    sn = pd.concat([pd.read_csv(f, parse_dates=["req_ts", "act_ts"]) for f in sorted(RAW.glob("*_snapshots.csv.gz"))],
                   ignore_index=True)
    sn = sn[(sn.status == "ok")]
    off = (sn.act_ts - sn.req_ts).dt.total_seconds().abs() / 60
    sn = sn[off <= MAX_OFFSET_MIN].copy()
    sn["date"] = sn.req_ts.dt.normalize()
    sn["how"] = sn.req_ts.dt.day_of_week * 48 + sn.req_ts.dt.hour * 2 + sn.req_ts.dt.minute // 30
    return sn


def daily_index(sn: pd.DataFrame) -> pd.DataFrame:
    prof = sn.groupby("how").n_points.median()
    sn["lr"] = np.log(sn.n_points.clip(lower=1) / sn.how.map(prof))
    per_day = sn.req_ts.dt.normalize().map(lambda d: 96 if d >= pd.Timestamp("2024-10-01") else 48)
    d = sn.assign(full=per_day).groupby("date").agg(
        n_snap=("lr", "size"), full=("full", "first"), lr=("lr", "median"), median_count=("n_points", "median"))
    days = pd.date_range("2021-10-01", "2026-09-30", freq="D")
    d = d.reindex(days)
    d.index.name = "date"
    d["n_snap"] = d.n_snap.fillna(0).astype(int)
    d["full"] = np.where(d.index >= pd.Timestamp("2024-10-01"), 96, 48)
    d["usable"] = d.n_snap >= MIN_DAY_SHARE * d.full
    d.loc[~d.usable, "lr"] = np.nan
    return d


def segment(d: pd.DataFrame) -> pd.DataFrame:
    s = d.lr.dropna()
    y = s.values.reshape(-1, 1)
    sigma = np.median(np.abs(np.diff(s.values))) / 0.6745 / np.sqrt(2)
    pen = PEN_MULT * sigma ** 2 * np.log(len(s))
    bkps = rpt.Pelt(model="l2", min_size=5).fit(y).predict(pen=pen)
    starts = [0] + bkps[:-1]
    seg = pd.DataFrame({"start": s.index[starts], "end": s.index[np.array(bkps) - 1]})
    seg["level"] = [s.values[a:b].mean() for a, b in zip(starts, bkps)]

    def days(r):
        return (r.end - r.start).days + 1

    segs = [dict(start=a, end=b, level=l, kind="regime") for a, b, l in zip(seg.start, seg.end, seg.level)]

    def merge(i, j):
        """Merge segment j into its immediate neighbour i (day-weighted level)."""
        a, b = segs[min(i, j)], segs[max(i, j)]
        w = [(a["end"] - a["start"]).days + 1, (b["end"] - b["start"]).days + 1]
        segs[min(i, j)] = dict(start=a["start"], end=b["end"], kind="regime",
                               level=np.average([a["level"], b["level"]], weights=w))
        del segs[max(i, j)]

    # 1) merge neighbouring regimes with near-equal levels, closest pair first
    while True:
        cand = [(abs(segs[i]["level"] - segs[i + 1]["level"]), i) for i in range(len(segs) - 1)
                if segs[i]["kind"] == segs[i + 1]["kind"] == "regime"]
        if not cand or min(cand)[0] >= MERGE_TOL:
            break
        merge(min(cand)[1], min(cand)[1] + 1)
    # 2) short segments, shortest first: an anomalous spell if far from both immediate neighbours,
    #    otherwise absorbed by the closer-level neighbour; then re-run step 1 locally
    while True:
        short = [i for i, g in enumerate(segs) if g["kind"] == "regime"
                 and (g["end"] - g["start"]).days + 1 < MIN_REGIME_DAYS]
        if not short:
            break
        i = min(short, key=lambda i: (segs[i]["end"] - segs[i]["start"]).days)
        nbs = [j for j in (i - 1, i + 1) if 0 <= j < len(segs) and segs[j]["kind"] == "regime"]
        dist = {j: abs(segs[j]["level"] - segs[i]["level"]) for j in nbs}
        # neighbour regimes one step away across a spell (e.g. a level interrupted by a 5-day dip)
        far = [j for j, k in ((i - 2, i - 1), (i + 2, i + 1)) if 0 <= j < len(segs)
               and segs[k]["kind"] == "spell" and segs[j]["kind"] == "regime"]
        if nbs and min(dist.values()) < SPELL_TOL:
            merge(min(dist, key=dist.get), i)
        elif far and min(abs(segs[j]["level"] - segs[i]["level"]) for j in far) < MERGE_TOL:
            j = min(far, key=lambda j: abs(segs[j]["level"] - segs[i]["level"]))
            segs[i]["kind"] = "alias"            # same coverage level as regime j, not contiguous
            segs[i]["alias_start"] = segs[j]["start"]
        else:
            segs[i]["kind"] = "spell"
    for i in range(len(segs) - 2, -1, -1):
        if segs[i]["kind"] == segs[i + 1]["kind"] == "regime" and abs(segs[i]["level"] - segs[i + 1]["level"]) < MERGE_TOL:
            merge(i, i + 1)
    seg = pd.DataFrame(segs)
    # make segments contiguous over the full calendar (gap days belong to the segment before them)
    seg["end"] = list(seg.start.iloc[1:] - pd.Timedelta(days=1)) + [d.index.max()]
    seg.loc[0, "start"] = d.index.min()
    seg["n_days"] = (seg.end - seg.start).dt.days + 1
    seg["level_log"] = [d.lr[r.start:r.end].mean() for r in seg.itertuples()]
    seg["level_ratio"] = np.exp(seg.level_log)
    seg["median_count"] = [d.median_count[r.start:r.end].median() for r in seg.itertuples()]
    seg["usable_days"] = [int(d.usable[r.start:r.end].sum()) for r in seg.itertuples()]
    reg = seg.kind == "regime"
    seg["regime"] = np.where(reg, "R" + reg.cumsum().astype(str).str.zfill(2), "spell")
    if "alias_start" in seg:
        # the alias target may have grown after aliasing; find the regime containing its old start
        for i in seg.index[seg.kind == "alias"]:
            t = seg[(seg.kind == "regime") & (seg.start <= seg.alias_start[i]) & (seg.end >= seg.alias_start[i])]
            seg.loc[i, "regime"] = t.regime.iloc[0]
            seg.loc[i, "kind"] = "regime"
    seg["regime_id"] = np.arange(len(seg))
    return seg[["regime_id", "regime", "kind", "start", "end", "n_days", "usable_days",
                "level_ratio", "level_log", "median_count"]]


def share_stability(seg: pd.DataFrame, window: int = 28) -> pd.DataFrame:
    """For each boundary between regimes, compare 1 km cell shares in the 28 days before and after."""
    cache: dict[str, tuple] = {}

    def month_shares(month):
        if month not in cache:
            z = np.load(RAW / f"{month}_cells500.npz")
            sn = pd.read_csv(RAW / f"{month}_snapshots.csv.gz", parse_dates=["req_ts"])
            df = pd.DataFrame({"snap": z["snap"], "cell": coarsen(z["cell"]), "n": z["n"].astype(int)})
            df = df.groupby(["snap", "cell"]).n.sum().reset_index()
            df["date"] = df.snap.map(sn.set_index("snap").req_ts.dt.normalize())
            cache[month] = df
        return cache[month]

    def shares(a, b):
        months = pd.period_range(a, b, freq="M").astype(str)
        df = pd.concat([month_shares(m) for m in months])
        df = df[(df.date >= a) & (df.date <= b)]
        tot = df.groupby("cell").n.sum()
        return tot / tot.sum()

    rows = []
    regs = seg[seg.kind == "regime"].reset_index(drop=True)
    for i in range(1, len(regs)):
        b = regs.start[i]
        before = shares(max(regs.start[i - 1], b - pd.Timedelta(days=window)), b - pd.Timedelta(days=1))
        after = shares(b, min(regs.end[i], b + pd.Timedelta(days=window - 1)))
        s = pd.concat([before, after], axis=1, keys=["before", "after"]).fillna(0)
        s = s[(s.before > 0.0005) | (s.after > 0.0005)]
        slope = np.polyfit(s.before, s.after, 1)[0]
        rows.append({"boundary": b.date(), "from": regs.regime[i - 1], "to": regs.regime[i],
                     "level_change": regs.level_ratio[i] / regs.level_ratio[i - 1],
                     "cells": len(s), "share_corr": s.corr().iloc[0, 1], "share_slope": slope,
                     "abs_share_shift": 0.5 * (s.before - s.after).abs().sum()})
    return pd.DataFrame(rows)


def duplicate_check() -> pd.DataFrame:
    rows = []
    for f in sorted(Path("data/raw/feed_check").glob("*_positions.csv.gz")):
        df = pd.read_csv(f)
        x, y = to_xy(df.lon, df.lat)
        tree = cKDTree(np.c_[x, y])
        nn = tree.query(np.c_[x, y], k=2)[0][:, 1]
        r = {"snapshot": f.name[:15].replace("_", " "), "points": len(df),
             "exact_duplicate_rows": int(df.duplicated().sum()),
             "median_nn_m": round(float(np.median(nn)), 1), "share_nn_lt_5m": round(float((nn < 5).mean()), 3)}
        for rad in (5, 10):
            r[f"after_merge_{rad}m"] = connected_components(
                tree.sparse_distance_matrix(tree, rad, output_type="coo_matrix"), directed=False)[0]
        rows.append(r)
    return pd.DataFrame(rows)


def plot(d: pd.DataFrame, seg: pd.DataFrame):
    plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 9, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED})
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    regs = seg[seg.kind == "regime"]
    for k, r in enumerate(regs.itertuples()):
        if k % 2:
            ax.axvspan(r.start, r.end + pd.Timedelta(days=1), color="#eef2f7", lw=0, zorder=0)
        mid = r.start + (r.end - r.start) / 2
        ax.hlines(r.median_count, r.start, r.end + pd.Timedelta(days=1), color=INK, lw=1.2, zorder=3)
        if r.n_days >= 40:
            ax.text(mid, 4850, r.regime, ha="center", va="top", fontsize=7.5, color=MUTED)
    for r in seg[seg.kind == "spell"].itertuples():
        ax.axvspan(r.start, r.end + pd.Timedelta(days=1), color=ORANGE, alpha=0.35, lw=0, zorder=1)
    ax.plot(d.index, d.median_count, color=BLUE, lw=0.8, zorder=2)
    odd = d[d.anomalous_day & (d.regime != "spell") & d.usable]
    ax.scatter(odd.index, odd.median_count, s=10, facecolor="white", edgecolor=ORANGE, lw=1, zorder=4)
    gaps = d.index[~d.usable]
    ax.scatter(gaps, np.full(len(gaps), 120), marker="|", color="#e34948", s=25, lw=0.8, zorder=3)
    ax.set_ylim(0, 4900)
    ax.set_xlim(d.index.min(), d.index.max())
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="y", color="#e5e5e2", lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel("Vacant taxis in feed, daily median (citywide)")
    ax.set_title("The taxi feed's coverage shifts between regimes; levels jump without a matching change in the market",
                 loc="left", fontsize=10.5, color=INK)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.legend(handles=[Line2D([], [], color=BLUE, lw=1, label="Daily median of snapshots"),
                       Line2D([], [], color=INK, lw=1.2, label="Regime median (change-point detection)"),
                       Patch(color=ORANGE, alpha=0.35, label="Short anomalous spell (excluded)"),
                       Line2D([], [], color=ORANGE, marker="o", mfc="white", lw=0, label="Unusual day (flagged, kept)"),
                       Line2D([], [], color="#e34948", marker="|", lw=0, label="Day missing (<50% snapshots)")],
              loc="upper left", bbox_to_anchor=(0, -0.1), ncol=3, frameon=False, fontsize=8)
    fig.text(0.01, 0.01, "Source: data.gov.sg taxi-availability API (LTA), Oct 2021 - Sep 2026. "
             "Regimes: PELT on log(count / half-hour-of-week median).", fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for ext in ("png", "svg"):
        fig.savefig(FIGS / f"feed_regimes.{ext}")
    plt.close(fig)


def main():
    for p in (INTERIM, TABLES, FIGS):
        p.mkdir(parents=True, exist_ok=True)
    sn = load_snapshots()
    d = daily_index(sn)
    seg = segment(d)
    day_seg = pd.cut(d.index.map(pd.Timestamp.toordinal),
                     bins=[s.toordinal() - 0.5 for s in seg.start] + [seg.end.iloc[-1].toordinal() + 0.5],
                     labels=False)
    d["regime"] = seg.regime.values[day_seg]
    d["regime_id"] = seg.regime_id.values[day_seg]
    lvl = d.regime_id.map(seg.set_index("regime_id").level_log)
    d["anomalous_day"] = (d.regime == "spell") | ((d.lr - lvl).abs() > DAY_TOL)
    # single anomalous days are only flagged: a dip can be a holiday or a heavy-rain day, and
    # dropping days on the outcome would bias the rain effects. Step 0 inspects them.
    d["exclude"] = (d.regime == "spell") | ~d.usable
    d.reset_index().to_csv(INTERIM / "feed_daily.csv", index=False, float_format="%.4f")
    for p in (INTERIM / "feed_regimes.csv", TABLES / "feed_regimes.csv"):
        seg.to_csv(p, index=False, float_format="%.4f")
    stab = share_stability(seg)
    stab.to_csv(TABLES / "feed_share_stability.csv", index=False, float_format="%.4f")
    dup = duplicate_check()
    dup.to_csv(TABLES / "feed_duplicate_check.csv", index=False)
    plot(d, seg)
    pd.set_option("display.width", 200)
    print(seg.to_string(index=False))
    print("anomalous days:", int(d.anomalous_day.sum()), "excluded days:", int(d.exclude.sum()))
    print(d[d.anomalous_day & (d.regime != "spell")].index.strftime("%Y-%m-%d").tolist())
    print(stab.to_string(index=False))
    print(dup.to_string(index=False))


if __name__ == "__main__":
    main()
