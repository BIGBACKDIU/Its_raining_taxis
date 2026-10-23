"""Final report figure set (HANDOFF section 7): builds two summary charts from saved tables and copies the chosen
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


def main():
    style()
    forecast_topk()
    policy_diagnosis()
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
