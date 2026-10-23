"""Step 3: rain associations (HANDOFF section 6, step 3), first part for the step-3 checkpoint.

Sample: fit period Apr 2022 - Mar 2025, main sample (drop_main == False), rain and lags present.
Estimator: Poisson PML with fixed effects and day-clustered errors (analysis/fepois_hd.py, validated against
pyfixest on 2023 with --validate). Effects are 100 * (exp(b) - 1) % with 95% CI.

Models
  abs     vacant ~ light + moderate + heavy + mmh_lag1 + mmh_lag2 | cell + how^month + ym^regime
          (ym^regime contains both the year-month and the regime effects of HANDOFF 3a)
  share   same regressors | cell + slot     (slot = snapshot; equivalent to a model of each cell's share of
          the citywide count, so any change in feed coverage at a snapshot is absorbed)
  offset  abs model with offset log(citywide count)
  share by regime: the share model fitted separately in each regime of the fit period
  event study: rain onsets (first 30-min window >= 1 mm/h after 2 h without rain in the cell; onsets within
          3 h of the previous onset merged), bins -60 ... +180 min; reported relative to -30 min.
          Reference group for estimation = cell-snapshots outside any event window.

Outputs: outputs/tables/effects_main.csv, effects_by_regime.csv, effects_event_study.csv,
effects_validation.csv, rain_onsets_summary.json; figures effects_main, effects_event_study, effects_by_regime.

Usage: .venv/bin/python -m analysis.03_effects [--validate]
"""
from __future__ import annotations

import argparse
import json
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.common import (BAND_COLORS, BLUE, BLUE_DARK, FIT, INK, INTERIM, MUTED, ORANGE, TABLES, load_panel,
                             save, style)
from analysis.fepois_hd import fepois, pct

BANDS = ["light", "moderate", "heavy"]
REGS = BANDS + ["mmh_lag1", "mmh_lag2"]
EVT_BINS = [-60, -30, 0, 30, 60, 90, 120, 150, 180]
COLS = ["ts", "cell", "vacant", "citywide", "rain_band", "mmh", "mmh_lag1", "mmh_lag2", "how", "month", "ym",
        "regime_id", "regime", "drop_main", "baseline"]


def load_fit(columns=COLS):
    p = load_panel(range(2022, 2026), columns=columns)
    p = p[(p.ts >= FIT[0] - pd.Timedelta(hours=3)) & (p.ts <= FIT[1])]
    return p.reset_index(drop=True)


def sample(p):
    return ((p.ts >= FIT[0]) & ~p.drop_main & (p.rain_band >= 0) & p.mmh_lag1.notna()
            & p.mmh_lag2.notna()).values


def design(p):
    X = np.column_stack([p.rain_band.values == 1, p.rain_band.values == 2, p.rain_band.values == 3,
                         p.mmh_lag1.values, p.mmh_lag2.values]).astype("float32")
    fe_abs = [p.cell.values, p.how.values.astype(np.int32) * 100 + p.month.values,
              p.ym.values.astype(np.int64) * 100 + p.regime_id.values]
    fe_share = [p.cell.values, p.ts.values]
    day = p.ts.values.astype("datetime64[D]")
    return X, fe_abs, fe_share, day


def run(name, y, X, names, fes, day, offset=None):
    t0 = time.time()
    r = fepois(y, X, names, fes, day, offset=offset)
    r = pct(r)
    r.insert(0, "model", name)
    r["n"] = r.attrs["n"]
    r["clusters"] = r.attrs["clusters"]
    print(f"{name}: n={r.attrs['n']:,} dropped={r.attrs['n_dropped']:,} it={r.attrs['iterations']} "
          f"{time.time() - t0:.0f}s", flush=True)
    print(r[["coef", "se", "pct", "pct_lo", "pct_hi"]].round(4).to_string(), flush=True)
    return r


# ----------------------------------------------------------------------------- event study
def onsets(p, thr=1.0, dry_windows=4, merge_min=180):
    """Event time (minutes from the cell's rain onset) for every row; NaN outside -60..+180."""
    mm = p.pivot_table(index="ts", columns="cell", values="mmh", aggfunc="first")
    grid = pd.date_range(mm.index.min(), mm.index.max(), freq="30min")
    mm = mm.reindex(grid)
    M = mm.values
    on = M >= thr
    for k in range(1, dry_windows + 1):
        prev = np.vstack([np.full((k, M.shape[1]), np.nan), M[:-k]])
        on &= prev == 0                                          # known and dry (NaN fails)
    evt = np.full(M.shape, np.nan)
    n_on, n_merged = 0, 0
    for j in range(M.shape[1]):
        idx = np.flatnonzero(on[:, j])
        kept = []
        for i in idx:
            if kept and (i - kept[-1]) * 30 <= merge_min:
                n_merged += 1
                continue
            kept.append(i)
        n_on += len(kept)
        kept = np.array(kept, int)
        if not len(kept):
            continue
        t = np.arange(M.shape[0])
        last = np.searchsorted(kept, t, "right") - 1               # latest onset <= t
        nxt = last + 1                                             # next onset > t
        rel_last = np.where(last >= 0, (t - kept[last.clip(0)]) * 30, 10 ** 6)
        rel_next = np.where(nxt < len(kept), (t - kept[nxt.clip(max=len(kept) - 1)]) * 30, -10 ** 6)
        e = np.where(rel_last <= 180, rel_last, np.where(rel_next >= -60, rel_next, np.nan))
        evt[:, j] = e
    ev = pd.DataFrame(evt, index=grid, columns=mm.columns).stack(future_stack=True).rename("evt")
    key = pd.MultiIndex.from_arrays([p.ts, p.cell])
    return ev.reindex(key).values, {"onsets": int(n_on), "merged_within_3h": int(n_merged), "threshold_mmh": thr}


def event_study(name, y, evt, fes, day, offset=None):
    X = np.column_stack([evt == b for b in EVT_BINS]).astype("float32")
    names = [f"evt_{b}" for b in EVT_BINS]
    r = fepois(y, X, names, fes, day, offset=offset)
    V = r.attrs["vcov"]
    ref = "evt_-30"
    rows = []
    for b, nm in zip(EVT_BINS, names):
        d = r.coef[nm] - r.coef[ref]
        se = 0.0 if nm == ref else np.sqrt(V.loc[nm, nm] + V.loc[ref, ref] - 2 * V.loc[nm, ref])
        rows.append({"model": name, "event_min": b, "coef": d, "se": se, "n_rows": int(X[:, EVT_BINS.index(b)].sum())})
    out = pct(pd.DataFrame(rows))
    print(name, out[["event_min", "pct", "pct_lo", "pct_hi"]].round(2).to_string(index=False), flush=True)
    return out


# ----------------------------------------------------------------------------- charts
def chart_main(tab):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    models = [("abs", "Absolute count (cell + how^month + ym^regime FE)", BLUE_DARK),
              ("share", "Share of citywide count (cell + snapshot FE)", BLUE),
              ("offset", "Absolute with log(citywide) offset", "#7fb0e8")]
    for k, (m, lab, col) in enumerate(models):
        t = tab[tab.model == m].loc[BANDS]
        x = np.arange(3) + (k - 1) * 0.25
        ax.errorbar(x, t.pct, yerr=[t.pct - t.pct_lo, t.pct_hi - t.pct], fmt="o", color=col, ms=7, capsize=3,
                    lw=1.5, label=lab)
        for xi, v in zip(x, t.pct):
            ax.text(xi + 0.04, v, f"{v:.1f}%", fontsize=7.5, color=MUTED, va="center")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xticks(range(3), ["Light\n(0-2.5 mm/h)", "Moderate\n(2.5-10 mm/h)", "Heavy\n(> 10 mm/h)"])
    ax.set_ylabel("% change in vacant taxis vs dry\n(rain in previous 30 min)")
    ax.legend(fontsize=7.5, loc="lower left")
    ax.set_title("Rain in the previous 30 minutes is associated with fewer vacant taxis in the cell", fontsize=10.5)
    fig.tight_layout()
    save(fig, "effects_main", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025, 1 km cells, "
         "Poisson with fixed effects, 95% CI clustered by day. Association, not cause.")
    plt.close(fig)


def chart_event(es):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for m, lab, col in (("abs", "Absolute count", BLUE_DARK), ("share", "Share of citywide count", BLUE)):
        t = es[es.model == f"event_{m}"]
        ax.fill_between(t.event_min, t.pct_lo, t.pct_hi, color=col, alpha=0.15, lw=0)
        ax.plot(t.event_min, t.pct, "o-", color=col, lw=2, ms=5, label=lab)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.axvline(-15, color=MUTED, lw=0.8, ls="--")
    ax.text(-12, ax.get_ylim()[1] * 0.9 if ax.get_ylim()[1] > 0 else 1, "rain starts", fontsize=7.5, color=MUTED)
    ax.set_xticks(EVT_BINS)
    ax.set_xlabel("Minutes from rain onset in the cell (snapshot at end of the 30-min window)")
    ax.set_ylabel("% vacant taxis vs 30 min before onset")
    ax.legend(fontsize=8, loc="lower left")
    ax.set_title("Vacant taxis fall as rain starts and recover within about two hours", fontsize=10.5)
    fig.tight_layout()
    save(fig, "effects_event_study", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Apr 2022 - Mar 2025. Onset: "
         "first window >= 1 mm/h after 2 h dry; onsets within 3 h merged. 95% CI clustered by day.")
    plt.close(fig)


def chart_regime(br):
    fig, ax = plt.subplots(figsize=(9, 4))
    br = br.sort_values("start")
    regs = br.regime.unique()
    for k, b in enumerate(BANDS):
        t = br[br.term == b].set_index("regime").loc[regs]
        x = np.arange(len(regs)) + (k - 1) * 0.25
        ax.errorbar(x, t.pct, yerr=[t.pct - t.pct_lo, t.pct_hi - t.pct], fmt="o", ms=5, capsize=2, lw=1.2,
                    color=BAND_COLORS[b] if b != "light" else "#7fb0e8", label=b.capitalize())
    lv = br.drop_duplicates("regime").set_index("regime").loc[regs]
    ax.set_xticks(range(len(regs)), [f"{r}\n{l:.2f}x\n{s:%b %y}" for r, l, s in zip(regs, lv.level_ratio, lv.start)],
                  fontsize=7.5)
    ax.axhline(0, color=MUTED, lw=0.8)
    pooled = br.attrs.get("pooled_heavy")
    if pooled is not None:
        ax.axhline(pooled, color=BLUE_DARK, lw=0.8, ls="--")
    ax.set_ylabel("% change in cell's share vs dry")
    ax.set_xlabel("Feed regime, coverage level (x normal), start")
    ax.legend(fontsize=8, ncol=3, loc="lower left")
    h = heterogeneity(br).set_index("term")
    ax.set_title(f"Heavy rain lowers a cell's share in 9 of 10 regimes, but the size varies "
                 f"(heterogeneity p = {h.loc['heavy', 'p']:.3f})", fontsize=10.5)
    fig.tight_layout()
    save(fig, "effects_by_regime", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall. Share model (cell + snapshot FE) "
         "fitted separately per regime within Apr 2022 - Mar 2025. Dashed: pooled heavy-rain effect. 95% CI by day.")
    plt.close(fig)


def heterogeneity(br):
    """Cochran's Q and I^2 across regimes for each rain band (inverse-variance pooled log effect)."""
    from scipy.stats import chi2
    rows = []
    for t in BANDS:
        for label, x in (("all regimes", br[br.term == t]), ("without R10", br[(br.term == t) & (br.regime != "R10")])):
            w = 1 / x.se ** 2
            m = (w * x.coef).sum() / w.sum()
            q = (w * (x.coef - m) ** 2).sum()
            k = len(x)
            rows.append({"term": t, "set": label, "regimes": k, "pooled_pct": 100 * (np.exp(m) - 1), "Q": q,
                         "df": k - 1, "p": chi2.sf(q, k - 1), "I2": max(0.0, (q - (k - 1)) / q)})
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "effects_by_regime_heterogeneity.csv", index=False, float_format="%.4f")
    return out[out.set == "all regimes"]


# ----------------------------------------------------------------------------- validation
def validate():
    import pyfixest as pf
    p = load_panel([2023], columns=COLS)
    s = (~p.drop_main & (p.rain_band >= 0) & p.mmh_lag1.notna() & p.mmh_lag2.notna()).values
    p = p[s]
    X, fe_abs, fe_share, day = design(p)
    ours = fepois(p.vacant.values, X, REGS, fe_abs, day)
    d = pd.DataFrame(X.astype("float64"), columns=REGS)
    d["vacant"] = p.vacant.values.astype("float64")
    d["cell"], d["hm"] = fe_abs[0], fe_abs[1]
    d["ym"], d["regime_id"], d["day"] = p.ym.values, p.regime_id.values, pd.factorize(day)[0]
    m = pf.fepois("vacant ~ " + " + ".join(REGS) + " | cell + hm + ym + regime_id", data=d, vcov={"CRV1": "day"},
                  copy_data=False, store_data=False, lean=True)
    t = pd.DataFrame({"ours_coef": ours.coef, "ours_se": ours.se, "pyfixest_coef": m.coef(), "pyfixest_se": m.se()})
    t["max_abs_coef_diff"] = (t.ours_coef - t.pyfixest_coef).abs()
    t["se_ratio"] = t.ours_se / t.pyfixest_se
    t.to_csv(TABLES / "effects_validation.csv", float_format="%.8f")
    print(t.to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    style()
    if a.validate:
        validate()
    p = load_fit()
    ev, info = onsets(p)
    s = sample(p)
    info["sample_rows"] = int(s.sum())
    p, ev = p[s].reset_index(drop=True), ev[s]
    print(f"sample rows {len(p):,}", info, flush=True)
    X, fe_abs, fe_share, day = design(p)
    y = p.vacant.values
    res = [run("abs", y, X, REGS, fe_abs, day), run("share", y, X, REGS, fe_share, day),
           run("offset", y, X, REGS, fe_abs, day, offset=np.log(p.citywide.values.astype("float64")))]
    tab = pd.concat(res)
    tab.index.name = "term"
    tab.drop(columns=[], errors="ignore").to_csv(TABLES / "effects_main.csv", float_format="%.6f")
    chart_main(tab)
    # share model by regime
    reg = pd.read_csv(INTERIM / "feed_regimes.csv", parse_dates=["start"])
    lv = reg[reg.kind == "regime"].groupby("regime").agg(level_ratio=("level_ratio", "mean"), start=("start", "min"))
    rows = []
    for r, idx in p.groupby("regime", observed=True).indices.items():
        if r == "spell" or len(idx) < 200_000:
            continue
        t = run(f"share_{r}", y[idx], X[idx], REGS, [fe_share[0][idx], fe_share[1][idx]], day[idx])
        t["regime"] = r
        rows.append(t.reset_index(names="term"))
    br = pd.concat(rows).merge(lv, left_on="regime", right_index=True)
    br.attrs["pooled_heavy"] = float(tab[tab.model == "share"].loc["heavy", "pct"])
    br.to_csv(TABLES / "effects_by_regime.csv", index=False, float_format="%.6f")
    chart_regime(br)
    # event study
    evt = np.where(np.isnan(ev), -999, ev).astype(int)
    info["rows_in_event_windows"] = int((evt != -999).sum())
    es = pd.concat([event_study("event_abs", y, evt, fe_abs, day), event_study("event_share", y, evt, fe_share, day)])
    es.to_csv(TABLES / "effects_event_study.csv", index=False, float_format="%.6f")
    (TABLES / "rain_onsets_summary.json").write_text(json.dumps(info, indent=2))
    chart_event(es)


if __name__ == "__main__":
    main()
