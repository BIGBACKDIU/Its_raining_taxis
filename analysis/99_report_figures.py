"""Final report figure set (HANDOFF section 7): builds four summary charts from saved tables and copies the chosen
charts (PNG + SVG) into outputs/figures/report/ with numbered names and an index of captions.

Usage: .venv/bin/python -m analysis.99_report_figures
"""
from __future__ import annotations

import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.common import BLUE, BLUE_DARK, FIGS, MUTED, ORANGE, TABLES, save, style

REPORT = FIGS / "report"
SET = [
    ("feed_regimes", "The taxi feed's coverage changes between regimes; every model allows for this."),
    ("desc_profile_rain_bands", "Vacant taxis relative to the expected level by time of day, dry vs rain bands."),
    ("desc_maps_dry_heavy", "Vacant taxis per 1 km cell, dry vs heavy rain, and % change vs expected."),
    ("effects_main", "Main rain associations: absolute, share and offset models (95% CI by day)."),
    ("effects_event_study", "Vacant taxis around rain onset in a cell (event study)."),
    ("effects_approach_forecast", "Vacant taxis thin before rain arrives: rain 2-5 km away and NEA forecasts."),
    ("effects_robustness", "The heavy-rain association across robustness checks."),
    ("inference_hotspots", "Cells with significantly fewer vacant taxis in heavy rain (BH FDR 10%)."),
    ("risk_vulnerability", "Where heavy rain most raises the chance of unusually low availability."),
    ("forecast_topk_both_labels", "Early warning at a fixed workload, retrospective and issue-time labels."),
    ("s1_weather_gain", "Weather's added skill across 36 scale x horizon x label comparisons (none material)."),
    ("planning_forecast_rain", "Planning view: availability under an NEA rain forecast by area and hour."),
    ("policy_diagnosis", "Repositioning plan vs forecast ranking: what the constraints cost in targeting."),
    ("sim_heldout_storms", "Simulation vs observed on held-out storms (scenario-based; did not pass plausibility)."),
    ("names_rain_hit_map", "Named places where heavy rain goes with the most taxis lost and the largest share losses."),
    ("minutes_to_taxi_maps", "Drive minutes to the nearest vacant taxi, dry, and the extra in heavy rain, by place."),
    ("dry_supply_by_band", "Dry-weather vacant-taxi supply by time band, best-supplied places named."),
    ("taxi_deserts_map", "Taxi deserts: residential areas with the fewest dry-weather vacant taxis per resident."),
    ("factors_contrasts", "Why: heavy-rain effect by place type (Central Area, MRT, taxi stand, mall) in the panel model."),
    ("factors_shap", "Which characteristics separate places that lose more (random forest; weak out-of-area fit)."),
    ("dose_intensity_hangover", "Intensity-response curve and the after-rain shortfall."),
    ("mrt_did_event_study", "New MRT stations: dry-weather supply nearby before and after opening (pre-trends fail)."),
    ("fleet_trend", "Monthly heavy-rain effect against the LTA fleet size."),
    ("stands_predicted_sensitivity", "Predicted heavy-rain sensitivity for every land cell (planning map)."),
    ("spillover_islandwide_map", "Island-wide rain: which named places gain or lose share of vacant taxis."),
    ("sim2_diagnosis", "Why the step-8 simulation failed its plausibility check: level, timing, spatial pattern."),
    ("sim2_heldout_storms", "Simulation v2 vs observed on held-out storms (illustration only; did not pass)."),
]


def forecast_topk():
    e = pd.read_csv(TABLES / "forecast_eval_both_labels.csv")
    e = e[(e.analysis == "primary") & (e.subset == "all")]
    models = [("persistence", "Persistence"), ("glm_no_weather", "Regression"), ("lgb_no_weather", "LightGBM"),
              ("lgb_weather", "LightGBM + weather")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, h in zip(axes, (30, 60)):
        for k, (ver, col) in enumerate((("retrospective", BLUE_DARK), ("issue-time", BLUE))):
            r = e[(e.h == h) & (e.label_version == ver)].iloc[0]
            v = [100 * r[f"topk_precision_{m}"] for m, _ in models]
            x = np.arange(len(models)) + (k - 0.5) * 0.36
            b = ax.bar(x, v, 0.34, color=col, label=f"{ver.capitalize()} label")
            ax.bar_label(b, fmt="%.0f", fontsize=7, color=MUTED, padding=1)
        ax.axhline(100 * e[(e.h == h)].base_rate.iloc[0], color=MUTED, lw=0.8, ls=":")
        ax.set_xticks(range(len(models)), [m for _, m in models], fontsize=8)
        ax.set_title(f"{h} minutes ahead", fontsize=9.5)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("% of the 19 alerted cells really low\n(per half hour, test year)")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Fixed-workload early warning: forecasts beat persistence; weather adds no material skill",
                 x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "forecast_topk_both_labels", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall and forecasts. "
         "Oct 2025 - Sep 2026; top 19 of 374 cells per issue time among cells expected >= 4. Dotted: base rate.")
    plt.close(fig)


def policy_diagnosis():
    g = pd.read_csv(TABLES / "policy_diagnosis.csv")
    g = g[g.split == "test"].set_index("variant")
    order = ["(c) top-19 forecast ranking, no constraints", "(c) restricted to cells with a staging point",
             "(c) ... and modelled shortfall S(0) >= 0.05", "(c) ... and reachable from a surplus cell within 60 min",
             "(b) policy, weights = forecast risk, 19 cells with most taxis", "(b) policy, weights = forecast risk",
             "(a) policy as designed, 19 cells with most taxis", "(a) policy as designed",
             "all candidate cells (expected >= 4)"]
    order = [o for o in order if o in g.index]
    t = g.loc[order]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(t))[::-1]
    ax.barh(y + 0.18, 100 * t.precision_retrospective, 0.34, color=BLUE_DARK, label="Retrospective label")
    ax.barh(y - 0.18, 100 * t.precision_issue_time, 0.34, color=BLUE, label="Issue-time label")
    for yy, v, n in zip(y, t.precision_retrospective, t.cells_per_decision):
        ax.text(100 * v + 0.5, yy + 0.18, f"{100 * v:.0f}% ({n:.0f} cells)", va="center", fontsize=7, color=MUTED)
    ax.set_yticks(y, order, fontsize=7.5)
    ax.set_xlabel("% of selected cells really low 60 min later (test year)")
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Each policy constraint narrows the choice of cells; spreading taxis over many cells dilutes targeting",
                 fontsize=10)
    fig.tight_layout()
    save(fig, "policy_diagnosis", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, LTA fleet statistics. "
         "300 test-year decision times. Travel times and staging rules are modelled assumptions.")
    plt.close(fig)


def factors_contrasts():
    t = pd.read_csv(TABLES / "factors_panel_interactions.csv")
    t = t[t.term.str.startswith("CONTRAST")].copy()
    t["label"] = t.term.str.replace("CONTRAST: heavy, ", "", regex=False).str.replace(" (vs >= 1 km reference)", "",
                                                                                         regex=False)
    order = ["Central Area", "MRT < 300 m", "MRT 300-1000 m", "MRT >= 1 km (reference)", "taxi stand within 300 m",
             "mall in cell"]
    nice = {"Central Area": "URA Central Area", "MRT < 300 m": "MRT exit < 300 m", "MRT 300-1000 m": "MRT exit 300-1,000 m",
            "MRT >= 1 km (reference)": "MRT exit >= 1 km (reference)", "taxi stand within 300 m": "Taxi stand within 300 m",
            "mall in cell": "Mall in cell"}
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, kind, col in ((axes[0], "abs", BLUE_DARK), (axes[1], "share", BLUE)):
        q = t[t.model == kind].set_index("label").reindex(order)
        y = np.arange(len(q))[::-1]
        ax.errorbar(q.pct, y, xerr=[q.pct - q.pct_lo, q.pct_hi - q.pct], fmt="o", color=col, capsize=3, ms=6)
        for yy, v in zip(y, q.pct):
            ax.text(v, yy + 0.22, f"{v:.1f}%", ha="center", fontsize=7.5, color=MUTED)
        ref = q.loc["MRT >= 1 km (reference)", "pct"]
        ax.axvline(ref, color=MUTED, lw=0.8, ls=":")
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.set_yticks(y, [nice[o] for o in order], fontsize=8.5)
        ax.set_xlabel("Heavy rain vs dry: % vacant taxis" if kind == "abs" else "Heavy rain: % change in share of citywide")
        ax.set_title("Absolute" if kind == "abs" else "Share of citywide vacant taxis", fontsize=9.5)
    fig.suptitle("Why some places lose more: the city centre stands out; MRT, taxi stands and malls make no clear "
                 "difference", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    save(fig, "factors_contrasts", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, URA MP2019, LTA, OSM. "
         "Apr 2022 - Mar 2025; Poisson FE with heavy-rain interactions, 95% CI clustered by day. Association, not cause.")
    plt.close(fig)


def spillover_map():
    import importlib
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    N = importlib.import_module("analysis.10_names")
    d02 = importlib.import_module("analysis.02_describe")
    r = pd.read_csv(TABLES / "spillover_islandwide_share.csv")
    fig, ax = plt.subplots(figsize=(9, 5.4))
    d02.draw_base(ax)
    div = LinearSegmentedColormap.from_list("d", ["#b8431c", ORANGE, "#f2f1ed", "#7fb0e8", BLUE_DARK])
    norm = TwoSlopeNorm(vcenter=0, vmin=-40, vmax=30)
    sig = r[r.direction != "no clear change"]
    N.draw_cells(ax, r.cell.values, np.where(r.direction == "no clear change", 0, r.share_pct.clip(-40, 30)), div, norm)
    lab = pd.concat([sig.nsmallest(6, "share_pct"), sig.nlargest(6, "share_pct")])
    lab = lab.assign(short=[f"{v:+.0f}%  {p}" for p, v in zip(lab.place, lab.share_pct)])
    N.label(ax, lab, "short", 12)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=div), ax=ax, orientation="horizontal", fraction=0.05, pad=0.02,
                 label="% change in the cell's share of citywide vacant taxis in island-wide rain (grey-white: no clear change)")
    ax.set_title("Island-wide rain: taxis gather at the airport and in suburbs, thin out in the centre", fontsize=10)
    fig.tight_layout()
    save(fig, "spillover_islandwide_map", "Sources: data.gov.sg taxi availability (LTA), NEA rainfall, URA MP2019, OSM. "
         "Apr 2022 - Mar 2025; island-wide = >= 50% of working gauges wet; day-bootstrap 95% CI. Association, not cause.")
    plt.close(fig)


def main():
    style()
    forecast_topk()
    policy_diagnosis()
    factors_contrasts()
    spillover_map()
    REPORT.mkdir(parents=True, exist_ok=True)
    lines = ["# Report figures", "", "PNG and SVG; numbered in suggested report order. Sources and notes are printed "
             "under each chart.", ""]
    for k, (name, cap) in enumerate(SET, start=1):
        for ext in ("png", "svg"):
            shutil.copy(FIGS / f"{name}.{ext}", REPORT / f"fig{k:02d}_{name}.{ext}")
        lines.append(f"{k:2d}. `fig{k:02d}_{name}` - {cap}")
    (REPORT / "README.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
