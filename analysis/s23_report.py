"""Paired day-block inference and figures for step-23 anonymous flow proxies."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.common import style, BLUE, ORANGE, save, NOT_ANALYSED
from analysis.s23_sample import LOCAL, TABLES


def bh(p):
    p = np.asarray(p)
    order = np.argsort(p)
    q = np.empty(len(p))
    q[order] = np.minimum.accumulate((p[order]*len(p)/np.arange(1, len(p)+1))[::-1])[::-1]
    return np.minimum(q, 1)


def bootstrap_indices(n):
    return np.random.default_rng(2702).integers(n, size=(1000, n))


def interval(values):
    values = np.asarray(values)
    finite = values[np.isfinite(values)]
    return (*np.quantile(finite, [.025, .975]), len(finite)) if len(finite) else (np.nan, np.nan, 0)


def load_city(sample):
    frames = []
    for s in sample.itertuples():
        for role, day in (("storm", s.storm_day), ("dry", s.dry_day)):
            for radius in (.5, 1., 2.):
                p = pd.read_parquet(LOCAL / f"{day}_{radius:g}.parquet", filters=[("cell", "==", -1)])
                onset = pd.Timestamp(day)+pd.Timedelta(hours=pd.Timestamp(s.onset).hour, minutes=pd.Timestamp(s.onset).minute)
                p["relative_min"] = (p.ts-onset).dt.total_seconds()/60
                # Event inventory, not unique active vehicles. At least 8 valid preceding bins.
                for _, ix in p.groupby("dense_excluded").groups.items():
                    p.loc[ix, "event_inventory"] = p.loc[ix, "V"].to_numpy()+p.loc[ix, "D"].rolling(8, min_periods=8).sum().to_numpy()
                frames.append(p[p.relative_min.between(-120, 225)])
    return pd.concat(frames, ignore_index=True)


def city_results(city):
    outcomes, curves, days = [], [], []
    for (radius, dense), d in city.groupby(["radius", "dense_excluded"]):
        a = d[d.role == "storm"].set_index(["pair", "relative_min"])
        b = d[d.role == "dry"].set_index(["pair", "relative_min"])
        cols = ["D", "A", "D_raw", "A_raw", "V", "speed", "outflow", "event_inventory"]
        merged = a[cols].join(b[cols], lsuffix="_storm", rsuffix="_dry", how="inner")
        pairs = sorted(merged.index.get_level_values("pair").unique())
        weights = bootstrap_indices(len(pairs))
        for metric in cols:
            for time, group in merged.groupby(level="relative_min"):
                storm = group[f"{metric}_storm"].reindex(pairs, level="pair").to_numpy()
                dry = group[f"{metric}_dry"].reindex(pairs, level="pair").to_numpy()
                ok = np.isfinite(storm) & np.isfinite(dry)
                diff = np.where(ok, storm-dry, np.nan)
                boot = np.nanmean(diff[weights], axis=1)
                lo, hi, count = interval(boot)
                curves.append(dict(radius=radius, dense_excluded=dense, metric=metric,
                                   relative_min=time, storm=np.nanmean(np.where(ok, storm, np.nan)),
                                   dry=np.nanmean(np.where(ok, dry, np.nan)), excess=np.nanmean(diff),
                                   lo=lo, hi=hi, pairs=int(ok.sum()), bootstrap_defined=count))
        per_day = []
        for pair, group in merged.groupby(level="pair"):
            time = group.index.get_level_values("relative_min")
            post = group[(time >= 0) & (time < 120)]
            complete = post[["D_storm", "D_dry", "A_storm", "A_dry"]].notna().all(axis=1)
            row = dict(pair=pair, radius=radius, dense_excluded=dense, bins=int(complete.sum()))
            valid = complete.sum() >= 7
            for metric in cols:
                good = post[[f"{metric}_storm", f"{metric}_dry"]].notna().all(axis=1) & complete
                for role in ("storm", "dry"):
                    row[f"{metric}_{role}"] = post.loc[good, f"{metric}_{role}"].mean() if valid and good.sum() >= 7 else np.nan
            per_day.append(row)
        p = pd.DataFrame(per_day).set_index("pair").reindex(pairs)
        days.append(p.reset_index())
        arrays = {c: p[c].to_numpy() for c in p.columns if c.endswith(("_storm", "_dry"))}
        mean = {c: np.nanmean(v) for c, v in arrays.items()}
        boot = {c: np.nanmean(v[weights], axis=1) for c, v in arrays.items()}
        den = mean["D_storm"]-mean["D_dry"]
        den_boot = boot["D_storm"]-boot["D_dry"]
        ratio = (mean["A_storm"]-mean["A_dry"])/den if den > 0 else np.nan
        ratios = np.divide(boot["A_storm"]-boot["A_dry"], den_boot,
                           out=np.full(1000, np.nan), where=den_boot > 0)
        metrics = dict(R=(ratio, ratios), one_minus_R=(1-ratio, 1-ratios))
        for metric in cols:
            metrics[f"excess_{metric}_per15"] = (mean[f"{metric}_storm"]-mean[f"{metric}_dry"],
                                                    boot[f"{metric}_storm"]-boot[f"{metric}_dry"])
        metrics["speed_pct"] = (100*(mean["speed_storm"]/mean["speed_dry"]-1),
                                100*(boot["speed_storm"]/boot["speed_dry"]-1))
        for metric, (value, boots) in metrics.items():
            lo, hi, count = interval(boots)
            outcomes.append(dict(radius=radius, dense_excluded=dense, metric=metric, estimate=value,
                                 lo=lo, hi=hi, pairs=len(pairs), bootstrap_defined=count,
                                 storm=mean.get(metric.removeprefix("excess_").removesuffix("_per15")+"_storm", np.nan),
                                 dry=mean.get(metric.removeprefix("excess_").removesuffix("_per15")+"_dry", np.nan),
                                 verdict=("undefined" if not np.isfinite(value) else
                                          "mostly consistent with hires (conditional proxy)" if value >= .7 else
                                          "mostly consistent with taxis leaving service (conditional proxy)" if value <= .4 else
                                          "mixed (conditional proxy)") if metric == "R" else ""))
        c = pd.DataFrame(curves)
        selected = c[(c.radius == radius) & (c.dense_excluded == dense)]
        peak_d = selected[(selected.metric == "D") & selected.relative_min.between(0, 105)].sort_values("relative_min")
        peak_a = selected[(selected.metric == "A") & selected.relative_min.between(0, 225)].sort_values("relative_min")
        outcomes.append(dict(radius=radius, dense_excluded=dense, metric="A_minus_D_peak_minutes",
                             estimate=peak_a.loc[peak_a.excess.idxmax(), "relative_min"]-peak_d.loc[peak_d.excess.idxmax(), "relative_min"]))
    pd.DataFrame(outcomes).to_csv(TABLES / "s23_results.csv", index=False)
    pd.DataFrame(curves).to_csv(TABLES / "s23_curves.csv", index=False)
    pd.concat(days).to_csv(TABLES / "s23_day_effects.csv", index=False)
    return pd.DataFrame(outcomes), pd.DataFrame(curves)


def geography(sample):
    rows, expected = [], []
    for s in sample.itertuples():
        per_role = {}
        for role, day in (("storm", s.storm_day), ("dry", s.dry_day)):
            onset = pd.Timestamp(day)+pd.Timedelta(hours=pd.Timestamp(s.onset).hour, minutes=pd.Timestamp(s.onset).minute)
            d = pd.read_parquet(LOCAL / f"{day}_1.parquet", filters=[("cell", "!=", -1), ("dense_excluded", "==", False)])
            d = d[(d.ts >= onset) & (d.ts < onset+pd.Timedelta(hours=2))]
            per_role[role] = d.groupby("cell")[["D", "A"]].agg(["mean", "count"])
            p = pd.read_parquet(ROOT / f"data/interim/panel30_{pd.Timestamp(day).year}.parquet",
                                columns=["ts", "cell", "baseline"], filters=[("ts", ">=", onset),
                                ("ts", "<", onset+pd.Timedelta(hours=2))])
            expected.append(p.groupby("cell").baseline.mean())
        for cell in per_role["storm"].index:
            row = dict(pair=s.pair, cell=cell)
            for metric in ("D", "A"):
                a, b = per_role["storm"].loc[cell, metric], per_role["dry"].loc[cell, metric]
                row[metric] = 8*(a["mean"]-b["mean"]) if min(a["count"], b["count"]) >= 7 else np.nan
            rows.append(row)
    d = pd.DataFrame(rows)
    e = pd.concat(expected, axis=1).mean(axis=1)
    names = pd.read_csv(TABLES / "names_cells.csv").set_index("cell")
    output = []
    for metric in ("D", "A"):
        a = d.pivot(index="pair", columns="cell", values=metric)
        weights = bootstrap_indices(len(a))
        boot = np.nanmean(a.to_numpy()[weights], axis=1)
        mean = a.mean().to_numpy()
        p = ttest_1samp(a.to_numpy(), 0, axis=0, nan_policy="omit").pvalue
        p = np.where(np.isfinite(p), p, 1.)
        q = bh(p)
        lo, hi = np.nanquantile(boot, [.025, .975], axis=0)
        for i, cell in enumerate(a.columns):
            output.append(dict(metric=metric, cell=cell, excess_two_hours=mean[i], lo=lo[i], hi=hi[i],
                               p=p[i], q=q[i], expected_vacant=e.get(cell, np.nan),
                               presentable=bool(e.get(cell, 0) >= 4 and q[i] < .10),
                               place=names.loc[cell, "place"], lon=names.loc[cell, "lon"], lat=names.loc[cell, "lat"]))
    out = pd.DataFrame(output)
    out.to_csv(TABLES / "s23_geography.csv", index=False)
    out[out.presentable].sort_values(["metric", "excess_two_hours"], ascending=[True, False]).to_csv(TABLES / "s23_named_places.csv", index=False)
    return out


def figures(results, curves, geo):
    style()
    c = curves[(curves.radius == 1) & ~curves.dense_excluded]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=True)
    for col, metric in enumerate(("D", "A")):
        p = c[c.metric == metric]
        axes[0, col].plot(p.relative_min, p.storm, color=BLUE, label="Storm days")
        axes[0, col].plot(p.relative_min, p.dry, color=ORANGE, label="Matched dry days")
        axes[0, col].set_title("Disappearance proxies" if metric == "D" else "Appearance proxies")
        axes[0, col].set_ylabel("Events per 15 min, citywide")
        axes[0, col].legend()
        axes[1, col].plot(p.relative_min, p.excess, color=BLUE)
        axes[1, col].fill_between(p.relative_min, p.lo, p.hi, color=BLUE, alpha=.2)
        axes[1, col].axhline(0, color="grey", lw=.7)
        axes[1, col].set_ylabel("Storm minus dry; 95% day CI")
        axes[1, col].set_xlabel("Minutes from gauge-defined onset")
    for ax in axes.flat:
        ax.axvline(0, color="grey", ls=":")
    fig.suptitle("Step 23 | Anonymous-coordinate flow proxies; mechanisms not identified", x=.01, ha="left")
    fig.tight_layout(rect=(0, .025, 1, .95))
    save(fig, "s23_flows")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    p = c[c.metric == "speed"]
    axes[0].plot(p.relative_min, p.storm, color=BLUE, label="Storm")
    axes[0].plot(p.relative_min, p.dry, color=ORANGE, label="Matched dry")
    axes[0].set(xlabel="Minutes from onset", ylabel="Inferred moving-point speed (km/h)")
    axes[0].legend()
    p = results[results.metric == "speed_pct"].copy()
    y = np.arange(len(p))
    axes[1].errorbar(p.estimate, y, xerr=np.maximum(0, np.array([p.estimate-p.lo, p.hi-p.estimate])), fmt="o", color=BLUE)
    axes[1].set_yticks(y, [f"{r.radius:g} km/min; {'exclude dense' if r.dense_excluded else 'all'}" for r in p.itertuples()])
    axes[1].axvline(-10, color=ORANGE, ls=":", label="Registered -10% threshold")
    axes[1].axvline(0, color="grey", lw=.7)
    axes[1].set_xlabel("Storm vs dry speed change (%); 95% day CI")
    fig.suptitle("Step 23 | Assignment-derived speed, conditional on inferred matching", x=.01, ha="left")
    fig.tight_layout(rect=(0, .03, 1, .93))
    save(fig, "s23_speed")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    names = pd.read_csv(TABLES / "names_cells.csv")
    limit = np.nanquantile(np.abs(geo.excess_two_hours), .98)
    for ax, metric, label in zip(axes, ("D", "A"), ("Disappearance proxies", "Appearance proxies")):
        p = geo[geo.metric == metric]
        background = names[~names.eligible]
        ax.scatter(background.lon, background.lat, c=NOT_ANALYSED, s=6, marker="s")
        im = ax.scatter(p.lon, p.lat, c=p.excess_two_hours, cmap="RdBu_r", vmin=-limit, vmax=limit, marker="s", s=9)
        top = p[p.presentable & (p.excess_two_hours > 0)].nlargest(3, "excess_two_hours")
        for r in top.itertuples():
            ax.annotate(r.place, (r.lon, r.lat), fontsize=5, xytext=(3, 3), textcoords="offset points")
        ax.set_title(label)
        ax.set_aspect(1/np.cos(np.deg2rad(1.35)))
        ax.set(xlabel="Longitude", ylabel="Latitude")
    fig.colorbar(im, ax=axes.tolist(), fraction=.02, pad=.02, label="Excess events, first 2 h (storm minus dry)")
    fig.suptitle("Step 23 | Flow geography; names require expected taxis >=4 and q<0.10", x=.01, ha="left")
    save(fig, "s23_geography")
    plt.close(fig)


def main():
    sample = pd.read_csv(TABLES / "s23_sample.csv")
    results, curves = city_results(load_city(sample))
    geo = geography(sample)
    figures(results, curves, geo)
    print(results[(results.radius == 1) & ~results.dense_excluded].to_string(index=False))


if __name__ == "__main__":
    main()
