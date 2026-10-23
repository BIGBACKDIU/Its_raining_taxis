"""Step 19: does the heavy-rain effect grow as the fleet shrinks? (pre-registration: decision 117)

Monthly heavy-rain effects (abs and share), Oct 2021 - Sep 2026 (test-year months used for this association
analysis and logged), then a meta-regression on the LTA fleet size, feed coverage level and season.
Usage: .venv/bin/python -m analysis.19_fleet
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.common import (BLUE, BLUE_DARK, INTERIM, MUTED, ORANGE, STATIC, TABLES, load_panel, log_test_scoring,
                             save, style)
from analysis.fepois_hd import fepois, pct

COLS = ["ts", "cell", "vacant", "rain_band", "mmh_lag1", "mmh_lag2", "how", "regime_id", "drop_main"]


def monthly():
    rows = []
    for y in range(2021, 2027):
        p = load_panel([y], columns=COLS)
        p = p[~p.drop_main & (p.rain_band >= 0) & p.mmh_lag1.notna() & p.mmh_lag2.notna()]
        for mth, q in p.groupby(p.ts.dt.to_period("M")):
            nh = int((q.rain_band == 3).sum())
            if nh < 2000:
                rows.append({"month": str(mth), "heavy_rows": nh})
                continue
            q = q.reset_index(drop=True)
            X = np.column_stack([q.rain_band == 1, q.rain_band == 2, q.rain_band == 3, q.mmh_lag1, q.mmh_lag2]).astype("float32")
            day = q.ts.values.astype("datetime64[D]")
            rec = {"month": str(mth), "heavy_rows": nh}
            for kind, fes in (("abs", [q.cell.values, q.how.values, q.regime_id.values]), ("share", [q.cell.values, q.ts.values])):
                r = fepois(q.vacant.values, X, ["light", "moderate", "heavy", "l1", "l2"], fes, day)
                rec[f"{kind}_coef"], rec[f"{kind}_se"] = float(r.coef["heavy"]), float(r.se["heavy"])
            rows.append(rec)
        print(y, flush=True)
    return pd.DataFrame(rows)


def main(meta_only=False):
    style()
    if meta_only:                    # reuse the monthly effects; re-run the meta-regression only
        log_test_scoring("19_fleet.py meta", "meta-regression re-run on saved monthly effects incl. test-year months "
                         "(registered coverage variable, HAC errors)", "step 19 fix")
        t = pd.read_csv(TABLES / "fleet_monthly_effects.csv")[["month", "heavy_rows", "abs_coef", "abs_se", "share_coef",
                                                                 "share_se"]]
    else:
        log_test_scoring("19_fleet.py", "monthly heavy-rain effects incl. test-year months (association only)", "step 19")
        t = monthly()
    fl = pd.read_csv(STATIC / "lta_cdg_share_monthly.csv", parse_dates=["month"])
    fl["month"] = fl.month.dt.to_period("M").astype(str)
    t = t.merge(fl[["month", "total_taxis"]], on="month", how="left")
    t["total_taxis"] = t.total_taxis.ffill()
    # registered coverage variable: the feed regime's log coverage level (feed_regimes.csv), averaged over the
    # month's days (decision 130; the first run used the daily level instead)
    dfl = pd.read_csv(INTERIM / "day_flags.csv", parse_dates=["date"])
    reg = pd.read_csv(TABLES / "feed_regimes.csv").set_index("regime_id").level_log
    dfl["regime_level"] = dfl.regime_id.map(reg)
    lev = dfl.groupby(dfl.date.dt.to_period("M").astype(str)).regime_level.mean()
    t["log_coverage"] = t.month.map(lev)
    mm = pd.PeriodIndex(t.month, freq="M").month
    t["season"] = np.select([np.isin(mm, [12, 1, 2, 3]), np.isin(mm, [6, 7, 8, 9])], ["NE monsoon", "SW monsoon"],
                            "inter-monsoon")
    t.to_csv(TABLES / "fleet_monthly_effects.csv", index=False, float_format="%.5f")
    import statsmodels.formula.api as smf
    res = []
    for kind in ("abs", "share"):
        d = t.dropna(subset=[f"{kind}_coef"]).copy()
        d["y"], d["se"] = d[f"{kind}_coef"], d[f"{kind}_se"]
        d["fleet_k"] = d.total_taxis / 1000
        ols = smf.wls("y ~ fleet_k + log_coverage + C(season)", data=d, weights=1 / d.se ** 2).fit()
        Q = float(np.sum(ols.resid ** 2 / d.se ** 2))
        tau2 = max(0.0, (Q - (len(d) - len(ols.params))) / np.sum(1 / d.se ** 2))
        d = d.sort_values("month").reset_index(drop=True)
        lag = int(np.floor(4 * (len(d) / 100) ** (2 / 9)))              # Newey-West rule of thumb
        m = smf.wls("y ~ fleet_k + log_coverage + C(season)", data=d, weights=1 / (d.se ** 2 + tau2)).fit(
            cov_type="HAC", cov_kwds={"maxlags": lag})
        b, s = m.params["fleet_k"], m.bse["fleet_k"]
        res.append({"model": kind, "months": len(d), "tau2": tau2, "se_type": f"HAC Newey-West, {lag} lags",
                    "slope_log_per_1000_taxis": b, "se": s, "p": m.pvalues["fleet_k"],
                    "pp_change_in_effect_per_1000_fewer_taxis": -100 * b,
                    "lo": -100 * (b + 1.96 * s), "hi": -100 * (b - 1.96 * s),
                    "coverage_coef": m.params["log_coverage"], "coverage_p": m.pvalues["log_coverage"]})
    rr = pd.DataFrame(res)
    rr.to_csv(TABLES / "fleet_meta_regression.csv", index=False, float_format="%.5f")
    print(rr.round(4).to_string(index=False))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, kind, col in ((axes[0], "abs", BLUE_DARK), (axes[1], "share", BLUE)):
        d = t.dropna(subset=[f"{kind}_coef"])
        x = d.total_taxis / 1000
        yv = 100 * (np.exp(d[f"{kind}_coef"]) - 1)
        lo = 100 * (np.exp(d[f"{kind}_coef"] - 1.96 * d[f"{kind}_se"]) - 1)
        hi = 100 * (np.exp(d[f"{kind}_coef"] + 1.96 * d[f"{kind}_se"]) - 1)
        ax.errorbar(x, yv, yerr=[yv - lo, hi - yv], fmt="o", ms=4, color=col, alpha=0.7, capsize=0, lw=0.8)
        r = rr[rr.model == kind].iloc[0]
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_xlabel("LTA taxi fleet (thousands)")
        ax.set_ylabel("Heavy-rain effect that month (%)")
        ax.set_title(f"{'Absolute' if kind == 'abs' else 'Share'}: {r.pp_change_in_effect_per_1000_fewer_taxis:+.1f} log-"
                     f"points per 1,000 fewer taxis (CI {r.lo:+.1f} to {r.hi:+.1f})", fontsize=9)
    fig.suptitle("Monthly heavy-rain effect against fleet size", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "fleet_trend", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, LTA P2P statistics. Oct 2021 - "
         "Sep 2026; meta-regression controls feed coverage level and season. Association, not cause.")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    main(meta_only=sys.argv[1:] == ["meta"])
