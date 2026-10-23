"""Shared forecast-evaluation helpers (corrected definitions after the independent review of aac26fe).

Fixed workload (main operational metric): at every issue time, alert the top-K units by risk score. For the
deficit label the ranking set is the units with expected >= 4 known at issue time (pattern at t+h x trailing
7-day level), because the label is undefined (never low) elsewhere; for the NB label it is every unit. K = round(0.05 x number of eligible units), fixed in
advance: 19 of 374 cells (1 km), 6 of 129 blocks (2 km), 2 of 49 planning areas. Units whose label is undefined
(expected < 4) count as "not low". The same K applies to every model.

Lead time: a low-availability run is a sequence of consecutive low target times in a unit. A run counts as
WARNED only if some alert targeting a time inside the run was issued BEFORE the run started (lead > 0, lead =
run start - earliest such issue time, so 0 < lead <= h). Runs whose first alert was issued at or after the start
count as "detected at or after onset" (reported separately); the rest are missed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WORKLOAD = 0.05
K_BY_UNITS = {374: 19, 129: 6, 49: 2}


def k_for(n_units: int) -> int:
    return K_BY_UNITS.get(n_units, max(1, int(round(WORKLOAD * n_units))))


def topk_alerts(ts, score, k, eligible=None):
    """Boolean alert per row: the k highest scores at each issue time among eligible rows (ties broken by order).
    For the deficit label, eligible = expected >= 4 known at issue time (pattern at t+h x 7-day level), because
    the label is undefined (never low) elsewhere; for the NB label every unit is eligible."""
    s = np.nan_to_num(np.asarray(score, float), nan=-np.inf)
    if eligible is not None:
        s = np.where(np.asarray(eligible, bool), s, -np.inf)
    d = pd.DataFrame({"ts": ts, "s": s})
    r = d.groupby("ts").s.rank(method="first", ascending=False)
    return ((r <= k) & np.isfinite(d.s)).values


def topk_metrics(ts, score, y, k):
    """Precision and recall of the top-k alerts per issue time; y may contain NaN (undefined = not low)."""
    a = topk_alerts(ts, score, k)
    yy = np.nan_to_num(np.asarray(y, float), nan=0.0) > 0.5
    n_t = pd.Series(ts).nunique()
    return {"K": k, "alerts": int(a.sum()), "topk_precision": float(yy[a].sum() / max(1, k * n_t)),
            "topk_recall": float(yy[a].sum() / max(1, yy.sum())), "low_rate_all_units": float(yy.mean())}


def lead_times(ts, unit, alert, y, h):
    """Per-run warning summary with the corrected definition (see module docstring)."""
    d = pd.DataFrame({"tt": pd.to_datetime(ts) + pd.Timedelta(minutes=h), "unit": unit, "a": np.asarray(alert, bool),
                      "y": np.nan_to_num(np.asarray(y, float), nan=0.0) > 0.5}).sort_values(["unit", "tt"])
    gap = (d.tt.diff() != pd.Timedelta(minutes=30)) | (d.unit != d.unit.shift())
    start = d.y & (~d.y.shift(fill_value=False) | gap)
    d["run"] = np.where(d.y, start.cumsum(), -1)
    r = d[d.run >= 0]
    runs = r.groupby("run").agg(s=("tt", "min"), n=("tt", "size"))
    al = r[r.a].copy()
    al["issue"] = al.tt - pd.Timedelta(minutes=h)
    first_issue = al.groupby("run").issue.min()
    runs["first_issue"] = first_issue
    runs["lead_min"] = (runs.s - runs.first_issue).dt.total_seconds() / 60
    return runs


def lead_summary(runs):
    warned = runs.lead_min > 0
    after = runs.lead_min.notna() & (runs.lead_min <= 0)
    return {"runs": int(len(runs)), "share_warned_before_onset": float(warned.mean()),
            "share_warned_ge30min": float((runs.lead_min >= 30).mean()),
            "median_lead_min_if_warned": float(runs.lead_min[warned].median()) if warned.any() else np.nan,
            "share_detected_at_or_after_onset_only": float(after.mean()),
            "share_missed": float(runs.lead_min.isna().mean())}
