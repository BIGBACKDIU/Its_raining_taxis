"""Check the low-memory Poisson fixed-effects estimator (analysis/fepois_hd.py) against pyfixest.

Synthetic panel with three fixed effects, rain-like dummies and a continuous regressor, clustered by day.
Run: .venv/bin/python tests/test_fepois_hd.py   (or with pytest)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.fepois_hd import felogit, fepois  # noqa: E402


def make_data(n_cells=60, n_days=120, slots=24, seed=2702):
    rng = np.random.default_rng(seed)
    cell = np.repeat(np.arange(n_cells), n_days * slots)
    day = np.tile(np.repeat(np.arange(n_days), slots), n_cells)
    slot = np.tile(np.arange(slots), n_cells * n_days)
    month = day // 30
    band = rng.choice(4, size=len(cell), p=[0.9, 0.05, 0.03, 0.02])
    lag = np.where(rng.random(len(cell)) < 0.1, rng.exponential(5, len(cell)), 0.0)
    eta = (0.5 + rng.normal(0, 0.8, n_cells)[cell] + 0.3 * np.sin(slot / 24 * 2 * np.pi) + 0.1 * month
           + np.array([0, -0.08, -0.12, -0.15])[band] - 0.002 * lag + rng.normal(0, 0.1, n_days)[day])
    y = rng.poisson(np.exp(eta))
    return pd.DataFrame({"y": y.astype(float), "light": (band == 1) * 1.0, "moderate": (band == 2) * 1.0,
                         "heavy": (band == 3) * 1.0, "lag": lag, "cell": cell, "hm": slot * 10 + month,
                         "month": month, "day": day})


def compare(d, fes, offset=None):
    import pyfixest as pf
    names = ["light", "moderate", "heavy", "lag"]
    ours = fepois(d.y.values, d[names].values.astype("float32"), names, [d[f].values for f in fes], d.day.values,
                  offset=None if offset is None else d[offset].values)
    m = pf.fepois("y ~ " + " + ".join(names) + " | " + " + ".join(fes), data=d, vcov={"CRV1": "day"},
                  offset=offset)
    coef_diff = np.max(np.abs(ours.coef.values - m.coef().values))
    se_ratio = ours.se.values / m.se().values
    return coef_diff, se_ratio


def test_against_pyfixest():
    d = make_data()
    coef_diff, se_ratio = compare(d, ["cell", "hm", "month"])
    assert coef_diff < 1e-6, coef_diff
    assert np.all(np.abs(se_ratio - 1) < 0.01), se_ratio       # small-sample corrections differ slightly


def test_offset_against_pyfixest():
    d = make_data(seed=7)
    d["log_exposure"] = np.log(np.random.default_rng(1).uniform(0.5, 2, len(d)))
    coef_diff, se_ratio = compare(d, ["cell", "hm"], offset="log_exposure")
    assert coef_diff < 1e-6, coef_diff
    assert np.all(np.abs(se_ratio - 1) < 0.01), se_ratio


def test_float32_storage():
    d = make_data(seed=11)
    names = ["light", "moderate", "heavy", "lag"]
    args = (d.y.values, d[names].values.astype("float32"), names, [d.cell.values, d.hm.values], d.day.values)
    a, b = fepois(*args), fepois(*args, xt_dtype="float32")
    assert np.max(np.abs(a.coef.values - b.coef.values)) < 1e-5
    assert np.max(np.abs(a.se.values / b.se.values - 1)) < 1e-3


def test_logit_against_pyfixest():
    import pyfixest as pf
    d = make_data(seed=3)
    d["low"] = (d.y <= 1) * 1.0
    names = ["light", "moderate", "heavy", "lag"]
    ours = felogit(d.low.values, d[names].values.astype("float32"), names, [d.cell.values, d.month.values],
                   d.day.values)
    m = pf.feglm("low ~ " + " + ".join(names) + " | cell + month", data=d, family="logit", vcov={"CRV1": "day"})
    assert np.max(np.abs(ours.coef.values - m.coef().values)) < 1e-4, (ours.coef.values, m.coef().values)
    assert np.all(np.abs(ours.se.values / m.se().values - 1) < 0.02), ours.se.values / m.se().values


if __name__ == "__main__":
    test_against_pyfixest()
    test_offset_against_pyfixest()
    test_float32_storage()
    test_logit_against_pyfixest()
    print("fepois_hd matches pyfixest")
