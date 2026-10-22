"""Step 0: data audit (HANDOFF section 6, step 0).

Decides which snapshots, days and gauge-days are usable before any rain result is looked at.

Snapshot level
  - status ok and |act_ts - req_ts| <= 10 min (HANDOFF 3a)
  - glitch: a single snapshot whose citywide count is below 50% of the median of the surrounding
    +-2 snapshots, with both the snapshot before and the one after back at >= 80% of that median
    (a spike). Sustained drops are not touched.
  - dip: a run of 1-3 consecutive snapshots below 25% of the median of the surrounding +-2 hours
    (run excluded); longer runs are sustained drops and are kept
  - robust z-score of the change in log citywide count between consecutive snapshots; z > 6 listed
Day level
  - feed regimes and short spells from prep_feed_regimes.py
  - each "unusual" day (daily level > 0.35 log from its regime) is classified as a feed outage or kept.
    A feed outage scales every cell by about the same factor, so the day's cell shares stay as correlated
    with the regime's normal shares (same 3-hour block of the day) as on a normal day, and the island is dry.
    Rain thins taxis unevenly in space and coincides with gauge rain.
Gauge level
  - gauge-day complete if >= 80% of 5-minute readings present (HANDOFF 5)
  - stuck gauge: >= 7 consecutive complete days of 0 mm while its 3 nearest complete neighbours record
    rain on >= 3 of those days
Month level appendix table: share of expected snapshots present, offsets, glitches, jumps, regimes, spells,
gauge completeness, stuck gauges, forecast coverage, COVID flag.

Outputs
  data/interim/snapshot_flags.csv.gz, data/interim/day_flags.csv, data/interim/gauge_day_flags.csv.gz
  outputs/tables/audit_monthly.csv, audit_unusual_days.csv, audit_glitches.csv, audit_jumps.csv,
  audit_stuck_gauges.csv, audit_summary.json
  outputs/figures/audit_unusual_days.png/.svg

Usage: .venv/bin/python -m analysis.00_audit
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from pipeline.grid import coarsen, to_xy

RAW = Path("data/raw")
INTERIM = Path("data/interim")
TABLES = Path("outputs/tables")
FIGS = Path("outputs/figures")
FINE_START = pd.Timestamp("2024-10-01")
MAX_OFFSET_MIN = 10
GLITCH_LOW, GLITCH_BACK = 0.5, 0.8
DIP_LOW, DIP_MAX_RUN, DIP_WINDOW_MIN = 0.25, 3, 120   # multi-snapshot dips (agreed at step-0 checkpoint)
JUMP_Z = 6
GAUGE_COMPLETE = 0.8 * 288
STUCK_DAYS, STUCK_NEIGHBOURS, STUCK_WET_DAYS = 7, 3, 3
BLOCK_HOURS = 3                     # time-of-day blocks for the share comparison
SHARE_Q = 0.10                      # "high" share correlation: at least the 10th percentile of normal days in the regime
DRY_MM = 2.0                        # "little rain": island-mean daily rain below 2 mm ...
DRY_MAX_GAUGE_MM = 20.0             # ... and no complete gauge above 20 mm that day
ANY_RAIN_MM = 0.2
COVID = (pd.Timestamp("2021-10-01"), pd.Timestamp("2022-03-31"))

BLUE, ORANGE, AQUA, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#e5e5e2"


# ----------------------------------------------------------------------------- snapshots
def load_snapshots() -> pd.DataFrame:
    parts = []
    for f in sorted((RAW / "taxi").glob("*_snapshots.csv.gz")):
        sn = pd.read_csv(f, parse_dates=["req_ts", "act_ts"])
        retry = RAW / "taxi_retry" / f.name
        if retry.exists():                                   # overlay recovered retries (none so far)
            rt = pd.read_csv(retry, parse_dates=["req_ts", "act_ts"]).set_index("snap")
            rec = rt[rt.status == "ok"]
            sn = sn.set_index("snap")
            sn.loc[rec.index, rec.columns] = rec
            sn = sn.reset_index()
        sn.insert(0, "month", f.name[:7])
        parts.append(sn)
    sn = pd.concat(parts, ignore_index=True)
    sn["offset_min"] = (sn.act_ts - sn.req_ts).dt.total_seconds() / 60
    sn["ok"] = sn.status == "ok"
    sn["offset_bad"] = sn.ok & (sn.offset_min.abs() > MAX_OFFSET_MIN)
    return sn


def flag_glitches(sn: pd.DataFrame) -> pd.DataFrame:
    v = sn[sn.ok & ~sn.offset_bad].sort_values("req_ts")
    n = v.n_points.astype(float).values
    t = v.req_ts.values
    step = np.where(v.req_ts >= FINE_START, 15, 30)
    nb = np.full((len(v), 4), np.nan)
    for k, s in enumerate((-2, -1, 1, 2)):
        idx = np.arange(len(v)) + s
        okk = (idx >= 0) & (idx < len(v))
        j = idx[okk]
        gap = np.abs((t[j] - t[okk]).astype("timedelta64[m]").astype(float))
        val = np.where(gap <= abs(s) * step[okk] + 1, n[j], np.nan)   # neighbours must be the adjacent slots
        nb[okk, k] = val
    m = np.nanmedian(nb, axis=1)
    enough = (~np.isnan(nb)).sum(1) >= 3
    glitch = enough & (n < GLITCH_LOW * m) & (nb[:, 1] >= GLITCH_BACK * m) & (nb[:, 2] >= GLITCH_BACK * m)
    sn["neighbour_median"] = pd.Series(m, index=v.index)
    sn["glitch_spike"] = False
    sn.loc[v.index[glitch], "glitch_spike"] = True
    sn["glitch_dip"] = flag_dips(sn[sn.ok & ~sn.offset_bad & ~sn.glitch_spike]).reindex(sn.index, fill_value=False)
    sn["glitch"] = sn.glitch_spike | sn.glitch_dip
    # robust z of jumps in log count, after glitches are removed
    w = sn[sn.ok & ~sn.offset_bad & ~sn.glitch].sort_values("req_ts")
    dl = np.log(w.n_points.clip(lower=1)).diff()
    gap = w.req_ts.diff().dt.total_seconds() / 60
    dl[gap > 31] = np.nan                                     # only consecutive slots
    # remove the normal change for that slot (e.g. the morning ramp): median change by resolution x
    # quarter-hour of week
    slot = (w.req_ts.dt.day_of_week * 96 + w.req_ts.dt.hour * 4 + w.req_ts.dt.minute // 15).astype(str) + \
        np.where(w.req_ts >= FINE_START, "f", "c")
    dl = dl - dl.groupby(slot).transform("median")
    mad = np.nanmedian(np.abs(dl - np.nanmedian(dl)))
    sn["jump_z"] = ((dl - np.nanmedian(dl)) / (1.4826 * mad)).reindex(sn.index)
    sn["usable"] = sn.ok & ~sn.offset_bad & ~sn.glitch
    return sn


def flag_dips(v: pd.DataFrame) -> pd.Series:
    """Runs of 1-3 consecutive snapshots below DIP_LOW x the median of the surrounding +-2 hours
    (the run itself excluded). Longer runs are sustained drops and are kept."""
    v = v.sort_values("req_ts")
    t = v.req_ts.values.astype("datetime64[m]").astype(np.int64)
    n = v.n_points.astype(float).values
    lo = np.searchsorted(t, t - DIP_WINDOW_MIN, "left")
    hi = np.searchsorted(t, t + DIP_WINDOW_MIN, "right")

    def window_median(a, b, skip):
        idx = np.r_[lo[a]:hi[b]]
        idx = idx[(idx < a) | (idx > b)] if skip else idx[idx != a]
        return np.median(n[idx]) if len(idx) >= 4 else np.nan

    cand = np.array([n[i] < DIP_LOW * window_median(i, i, False) for i in range(len(n))])
    step = np.where(v.req_ts >= FINE_START, 15, 30)
    out = np.zeros(len(n), bool)
    i = 0
    while i < len(n):
        if not cand[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(n) and cand[j + 1] and t[j + 1] - t[j] <= step[j]:
            j += 1
        if j - i + 1 <= DIP_MAX_RUN:
            m = window_median(i, j, True)
            if np.all(n[i:j + 1] < DIP_LOW * m):
                out[i:j + 1] = True
        i = j + 1
    return pd.Series(out, index=v.index)


# ----------------------------------------------------------------------------- rain gauges
def load_gauges():
    comp = pd.concat([pd.read_csv(f, parse_dates=["date"]) for f in sorted((RAW / "rain").glob("*_completeness.csv.gz"))])
    st = pd.concat([pd.read_csv(f, parse_dates=["date"]) for f in sorted((RAW / "rain").glob("*_stations.csv.gz"))])
    comp = comp.merge(st[["date", "station_id", "lat", "lon"]].drop_duplicates(["date", "station_id"]),
                      on=["date", "station_id"], how="left")
    loc = st.groupby("station_id")[["lat", "lon"]].last()
    comp["lat"] = comp.lat.fillna(comp.station_id.map(loc.lat))
    comp["lon"] = comp.lon.fillna(comp.station_id.map(loc.lon))
    comp["complete"] = comp.n_readings >= GAUGE_COMPLETE
    return comp


def flag_stuck(comp: pd.DataFrame) -> pd.DataFrame:
    c = comp[comp.complete].copy()
    c["nb_mm"] = np.nan
    for day, g in c.groupby("date"):
        if len(g) < STUCK_NEIGHBOURS + 1:
            continue
        x, y = to_xy(g.lon.values, g.lat.values)
        _, idx = cKDTree(np.c_[x, y]).query(np.c_[x, y], k=STUCK_NEIGHBOURS + 1)
        c.loc[g.index, "nb_mm"] = g.mm_total.values[idx[:, 1:]].mean(1)
    c = c.sort_values(["station_id", "date"])
    c["stuck"] = False
    for sid, g in c.groupby("station_id"):
        zero = (g.mm_total == 0).values
        consec = np.r_[True, np.diff(g.date.values).astype("timedelta64[D]").astype(int) == 1]
        # a run continues only through consecutive calendar days that are all zero
        run_id = np.cumsum(~(zero & consec & np.r_[False, zero[:-1]]))
        run_id = np.where(zero, run_id, -1)
        for rid in np.unique(run_id[run_id >= 0]):
            sel = run_id == rid
            if sel.sum() >= STUCK_DAYS and (g.nb_mm.values[sel] > 1.0).sum() >= STUCK_WET_DAYS:
                c.loc[g.index[sel], "stuck"] = True
    comp = comp.merge(c[["date", "station_id", "nb_mm", "stuck"]], on=["date", "station_id"], how="left")
    comp["stuck"] = comp.stuck.fillna(False).astype(bool)
    comp["working"] = comp.complete & ~comp.stuck
    return comp


def island_rain(comp: pd.DataFrame) -> pd.DataFrame:
    w = comp[comp.working]
    return w.groupby("date").agg(island_mm=("mm_total", "mean"), max_gauge_mm=("mm_total", "max"),
                                 gauges_working=("station_id", "nunique"))


# ----------------------------------------------------------------------------- unusual days
def day_block_shares(sn: pd.DataFrame) -> pd.DataFrame:
    """Vacant taxis summed per (date, 3-hour block, 1 km cell), usable snapshots only."""
    good = sn[sn.usable].set_index(["month", "snap"]).req_ts
    parts = []
    for f in sorted((RAW / "taxi").glob("*_cells500.npz")):
        month = f.name[:7]
        z = np.load(f)
        df = pd.DataFrame({"snap": z["snap"], "cell": coarsen(z["cell"]), "n": z["n"].astype("int32")})
        ts = good.loc[month] if month in good.index.get_level_values(0) else pd.Series(dtype="datetime64[ns]")
        df = df[df.snap.isin(ts.index)]
        df["ts"] = df.snap.map(ts)
        df["date"] = df.ts.dt.normalize()
        df["block"] = df.ts.dt.hour // BLOCK_HOURS
        parts.append(df.groupby(["date", "block", "cell"]).n.sum().reset_index())
    return pd.concat(parts, ignore_index=True)


def _corr(day_counts: pd.Series, ref: pd.Series) -> float:
    """sqrt-share Pearson correlation over the union of cells (cells with no taxis count as 0)."""
    idx = ref.index.union(day_counts.index)
    s = day_counts.reindex(idx).fillna(0)
    r = ref.reindex(idx).fillna(0)
    if s.sum() <= 0:
        return np.nan
    return np.corrcoef(np.sqrt(s / s.sum()), np.sqrt(r))[0, 1]


def classify_unusual(daily: pd.DataFrame, cells: pd.DataFrame, rain: pd.DataFrame, n_null: int = 40) -> pd.DataFrame:
    """Feed outage vs rain-like for each unusual day.

    Under a feed outage every cell keeps its normal share and only the total shrinks. Fewer taxis make the
    observed shares noisier, so the day is compared with a null built from the same regime's normal days,
    binomially thinned to the day's own level (p = day count / regime-normal count, per 3-hour block).
    "High share correlation" = at least the 10th percentile of that null. Upward days (p > 1, a regime
    temporarily back at another coverage level) are compared with unthinned normal days.
    """
    rng = np.random.default_rng(2702)
    daily = daily.join(rain)
    cells = cells.merge(daily[["regime"]], left_on="date", right_index=True)
    normal_days = daily.index[~daily.anomalous_day & ~daily.exclude]
    nc = cells[cells.date.isin(normal_days)]
    ref = nc.groupby(["regime", "block", "cell"]).n.sum()
    ref = (ref / ref.groupby(level=[0, 1]).transform("sum")).rename("ref")
    norm_tot = nc.groupby(["regime", "block", "date"]).n.sum().groupby(level=[0, 1]).median()
    by = {k: g.set_index("cell").n for k, g in cells.groupby(["date", "block"])}
    rows = []
    for d in daily.index[daily.anomalous_day & (daily.regime != "spell")]:
        regime = daily.regime[d]
        pool = rng.choice(normal_days[daily.regime[normal_days] == regime], size=n_null, replace=True)
        obs, null = [], np.zeros(n_null)
        w_tot = 0
        for b in range(24 // BLOCK_HOURS):
            if (d, b) not in by or (regime, b) not in norm_tot.index:
                continue
            day_n = by[(d, b)]
            r = ref.loc[(regime, b)]
            p = min(1.0, day_n.sum() / norm_tot.loc[(regime, b)])
            w = day_n.sum()
            obs.append(w * _corr(day_n, r))
            for k, nd in enumerate(pool):
                base = by.get((nd, b))
                if base is None:
                    null[k] += w * np.nan
                    continue
                thinned = pd.Series(rng.binomial(base.values, p), index=base.index)
                null[k] += w * _corr(thinned, r)
            w_tot += w
        if w_tot == 0:
            continue
        null = null / w_tot
        rows.append((d, np.sum(obs) / w_tot, np.nanquantile(null, SHARE_Q), np.nanmedian(null)))
    sc = pd.DataFrame(rows, columns=["date", "share_corr", "corr_threshold", "null_median"]).set_index("date")
    daily = daily.join(sc)
    dry = (daily.island_mm < DRY_MM) & (daily.max_gauge_mm < DRY_MAX_GAUGE_MM)
    daily["unusual_class"] = np.where(~daily.anomalous_day | (daily.regime == "spell"), "",
                              np.where((daily.share_corr >= daily.corr_threshold) & dry, "feed_outage", "kept"))
    return daily


# ----------------------------------------------------------------------------- monthly appendix
def monthly_table(sn, daily, comp, glitches_by_month):
    m = sn.groupby("month").agg(expected=("snap", "size"), returned_ok=("ok", "sum"),
                                offset_dropped=("offset_bad", "sum"), glitches=("glitch_spike", "sum"), dips=("glitch_dip", "sum"),
                                usable=("usable", "sum"), median_offset_min=("offset_min", "median"),
                                jumps_z_gt6=("jump_z", lambda z: int((z.abs() > JUMP_Z).sum())),
                                median_citywide=("n_points", "median"))
    m["share_present"] = (m.usable / m.expected).round(4)
    d = daily.reset_index()
    d["month"] = d.date.dt.strftime("%Y-%m")
    dm = d.groupby("month").agg(days=("date", "size"), days_missing=("usable", lambda u: int((~u).sum())),
                                spell_days=("regime", lambda r: int((r == "spell").sum())),
                                feed_outage_days=("unusual_class", lambda c: int((c == "feed_outage").sum())),
                                unusual_kept_days=("unusual_class", lambda c: int((c == "kept").sum())),
                                regimes=("regime", lambda r: " ".join(sorted(set(r) - {"spell"}))))
    dm["days_excluded_main"] = d.groupby("month").exclude_main.sum().astype(int)
    comp = comp.copy()
    comp["month"] = comp.date.dt.strftime("%Y-%m")
    gm = comp.groupby("month").agg(gauges=("station_id", "nunique"), gauge_days=("station_id", "size"),
                                   gauge_days_complete=("complete", "sum"), gauge_days_stuck=("stuck", "sum"))
    gm["gauge_complete_share"] = (gm.gauge_days_complete / gm.gauge_days).round(4)
    fc = []
    for f in sorted((RAW / "forecast").glob("*_forecast.csv.gz")):
        x = pd.read_csv(f, usecols=["issued"], parse_dates=["issued"])
        days_in = pd.Period(f.name[:7]).days_in_month
        fc.append((f.name[:7], x.issued.nunique(), x.issued.dt.normalize().nunique() / days_in))
    fm = pd.DataFrame(fc, columns=["month", "forecast_issues", "forecast_day_coverage"]).set_index("month")
    out = m.join(dm).join(gm).join(fm)
    p = pd.PeriodIndex(out.index, freq="M")
    out["covid_flag"] = (p >= COVID[0].to_period("M")) & (p <= COVID[1].to_period("M"))
    out["period"] = np.select([p < pd.Period("2022-04"), p <= pd.Period("2025-03"), p <= pd.Period("2025-09")],
                              ["pre-fit (COVID)", "fit", "calibrate"], "test")
    cols = ["period", "covid_flag", "expected", "returned_ok", "offset_dropped", "glitches", "dips", "usable", "share_present",
            "median_offset_min", "jumps_z_gt6", "median_citywide", "regimes", "days", "days_missing", "spell_days",
            "feed_outage_days", "unusual_kept_days", "days_excluded_main", "gauges", "gauge_complete_share",
            "gauge_days_stuck", "forecast_issues", "forecast_day_coverage"]
    return out[cols]


def plot_unusual(daily: pd.DataFrame):
    plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 9, "axes.edgecolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": INK})
    d = daily.copy()
    d["rel_corr"] = d.share_corr - d.corr_threshold
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150)
    for cls, col, lab in (("kept", BLUE, "Unusual day, kept (rain-like or mixed)"),
                          ("feed_outage", ORANGE, "Unusual day, feed outage (excluded from main)")):
        g = d[d.unusual_class == cls]
        ax.scatter(g.island_mm + 0.1, g.rel_corr, s=22, color=col, edgecolor="white", lw=0.8, label=f"{lab}: {len(g)}",
                   zorder=3)
    ax.axhline(0, color=MUTED, lw=0.8, ls="--")
    ax.axvline(DRY_MM + 0.1, color=MUTED, lw=0.8, ls="--")
    ax.set_xscale("log")
    ax.set_xlabel("Island-mean rain that day (mm, working gauges; +0.1 for log scale)")
    ax.set_ylabel("Cell-share correlation with regime normal\nminus feed-outage null (10th percentile)")
    ax.grid(color=GRID, lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Unusual days: dry days whose spatial pattern looks normal are treated as feed outages",
                 loc="left", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.text(0.01, 0.01, "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Shares: 1 km cells, 3-hour blocks, "
             "sqrt-share Pearson correlation; null = normal days thinned to the day's level.", fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    for ext in ("png", "svg"):
        fig.savefig(FIGS / f"audit_unusual_days.{ext}")
    plt.close(fig)


def main():
    for p in (INTERIM, TABLES, FIGS):
        p.mkdir(parents=True, exist_ok=True)
    sn = flag_glitches(load_snapshots())
    comp = flag_stuck(load_gauges())
    rain = island_rain(comp)
    daily = pd.read_csv(INTERIM / "feed_daily.csv", parse_dates=["date"]).set_index("date")
    daily = classify_unusual(daily, day_block_shares(sn), rain)
    daily["feed_outage"] = daily.unusual_class == "feed_outage"
    daily["exclude_main"] = daily.exclude | daily.feed_outage
    # robustness set: main + feed-outage days + the ambiguous rain/feed spell of 26 Feb - 1 Mar 2023
    daily["exclude_robust"] = daily.exclude & ~daily.index.to_series().between("2023-02-26", "2023-03-01")
    daily["covid"] = daily.index.to_series().between(*COVID)

    # ---- save
    sn[["month", "snap", "req_ts", "act_ts", "n_points", "status", "offset_min", "offset_bad", "glitch_spike",
        "glitch_dip", "glitch", "neighbour_median", "jump_z", "usable"]].to_csv(INTERIM / "snapshot_flags.csv.gz", index=False,
                                                         float_format="%.3f")
    daily.reset_index().to_csv(INTERIM / "day_flags.csv", index=False, float_format="%.4f")
    comp[["date", "station_id", "n_readings", "mm_total", "complete", "stuck", "working", "nb_mm"]].to_csv(
        INTERIM / "gauge_day_flags.csv.gz", index=False, float_format="%.2f")
    gl = sn[sn.glitch][["req_ts", "n_points", "neighbour_median", "glitch_spike", "glitch_dip"]]
    gl.to_csv(TABLES / "audit_glitches.csv", index=False)
    jumps = sn[sn.jump_z.abs() > JUMP_Z].sort_values("jump_z", key=np.abs, ascending=False)
    jumps[["req_ts", "n_points", "jump_z"]].to_csv(TABLES / "audit_jumps.csv", index=False, float_format="%.2f")
    stuck = (comp[comp.stuck].groupby("station_id").agg(first=("date", "min"), last=("date", "max"),
                                                        stuck_days=("date", "size"), nb_mm_total=("nb_mm", "sum")))
    stuck.to_csv(TABLES / "audit_stuck_gauges.csv", float_format="%.1f")
    un = daily[daily.unusual_class != ""][["regime", "median_count", "lr", "island_mm", "max_gauge_mm", "share_corr",
                                           "corr_threshold", "null_median", "unusual_class"]]
    un.to_csv(TABLES / "audit_unusual_days.csv", float_format="%.4f")
    monthly = monthly_table(sn, daily, comp, None)
    monthly.to_csv(TABLES / "audit_monthly.csv", float_format="%.3f")
    plot_unusual(daily)

    fo = daily[daily.feed_outage]
    summary = {
        "snapshots_expected": int(len(sn)), "snapshots_ok": int(sn.ok.sum()),
        "dropped_offset_gt_10min": int(sn.offset_bad.sum()), "dropped_glitch_spike": int(sn.glitch_spike.sum()), "dropped_glitch_dip": int(sn.glitch_dip.sum()),
        "snapshots_usable": int(sn.usable.sum()), "jumps_abs_z_gt6_after_glitches": int(len(jumps)),
        "days_total": int(len(daily)), "days_missing_lt50pct": int((~daily.usable).sum()),
        "spell_days": int((daily.regime == "spell").sum()),
        "unusual_days": int((daily.unusual_class != "").sum()),
        "unusual_feed_outage": int(len(fo)), "unusual_kept": int((daily.unusual_class == "kept").sum()),
        "feed_outage_days_any_rain_gt0.2mm": int((fo.island_mm > ANY_RAIN_MM).sum()),
        "feed_outage_days_list": [d.strftime("%Y-%m-%d") for d in fo.index],
        "days_excluded_main": int(daily.exclude_main.sum()),
        "gauge_days_complete_share": round(float(comp.complete.mean()), 4),
        "gauge_days_stuck": int(comp.stuck.sum()), "stuck_gauges": int(comp[comp.stuck].station_id.nunique()),
        "thresholds": {"share_q": SHARE_Q, "dry_mm": DRY_MM, "dry_max_gauge_mm": DRY_MAX_GAUGE_MM,
                       "glitch_low": GLITCH_LOW, "glitch_back": GLITCH_BACK, "dip_low": DIP_LOW, "dip_max_run": DIP_MAX_RUN, "jump_z": JUMP_Z},
    }
    (TABLES / "audit_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    pd.set_option("display.width", 220)
    print(un.round(3).to_string())


if __name__ == "__main__":
    main()
