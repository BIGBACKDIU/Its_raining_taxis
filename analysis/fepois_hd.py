"""Low-memory Poisson regression with high-dimensional fixed effects and day-clustered errors.

pyfixest needs about 550 bytes per row; the fit-period panel has ~18 million rows, which would need ~10 GB.
This module implements the same estimator (pseudo-maximum likelihood, IRLS with fixed effects partialled out
by weighted alternating projections, as in ppmlhdfe / fixest) with plain numpy arrays, warm-started fixed-effect
components and no design-matrix copies. Standard errors are cluster-robust (CRV1) with pyfixest's default
small-sample correction G/(G-1) * (N-1)/(N-K). It is validated against pyfixest on one year
(analysis/03_effects.py --validate) before use.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _drop_separated(y, fes):
    """Drop rows in fixed-effect groups whose outcome is always zero (their effect is -inf), repeatedly."""
    keep = np.ones(len(y), bool)
    while True:
        bad = np.zeros(len(y), bool)
        for g in fes:
            s = np.bincount(g[keep], y[keep], g.max() + 1)
            bad |= keep & (s[g] <= 0)
        if not bad.any():
            return keep
        keep &= ~bad


class Demeaner:
    """Weighted alternating projections with fixed-effect components kept between calls (warm start)."""

    def __init__(self, fes, n_cols):
        self.fes = fes
        self.sizes = [int(g.max()) + 1 for g in fes]
        self.alpha = [[np.zeros(s) for s in self.sizes] for _ in range(n_cols)]

    def demean_col(self, j, v, w, wsum, tol, maxit=10000):
        """Weighted residual of column v (copied) on the fixed effects, warm-started from stored components."""
        r = np.array(v, dtype="float64")
        for g, a in zip(self.fes, self.alpha[j]):
            r -= a[g]
        for it in range(maxit):
            step = 0.0
            for k, (g, s) in enumerate(zip(self.fes, self.sizes)):
                d = np.bincount(g, w * r, s) / wsum[k]
                r -= d[g]
                self.alpha[j][k] += d
                step = max(step, np.abs(d).max())
            if step < tol:
                break
        return r

    def wsums(self, w):
        return [np.bincount(g, w, s) for g, s in zip(self.fes, self.sizes)]


def fepois(y, X, names, fes, cluster, offset=None, tol=1e-8, maxit=50, verbose=False):
    """Poisson PML with fixed effects. y (n,), X (n, k), fes: list of int arrays, cluster: int array.

    Returns a DataFrame with coef, se, z, p and attributes n, n_dropped, iterations, clusters.
    """
    y = np.asarray(y, "float64")
    X = np.asarray(X)
    fes = [pd.factorize(np.asarray(g))[0] for g in fes]
    keep = _drop_separated(y, fes)
    if not keep.all():
        y, X = y[keep], X[keep]
        fes = [pd.factorize(g[keep])[0] for g in fes]
        cluster = np.asarray(cluster)[keep]
        offset = None if offset is None else np.asarray(offset)[keep]
    off = np.zeros(len(y)) if offset is None else np.asarray(offset, "float64")
    n, k = X.shape
    dm = Demeaner(fes, k + 1)
    mu = (y + y.mean()) / 2
    eta = np.log(mu)
    beta = np.zeros(k)
    dev_old = np.inf
    Xt = np.empty((n, k))
    for it in range(1, maxit + 1):
        tol_it = max(1e-10, min(1e-4, 1e-3 * 10 ** -it))
        ws = dm.wsums(mu)
        z = eta - off + (y - mu) / mu
        zt = dm.demean_col(0, z, mu, ws, tol_it)
        for j in range(k):
            Xt[:, j] = dm.demean_col(j + 1, X[:, j], mu, ws, tol_it)
        XtWX = np.empty((k, k))
        XtWz = np.empty(k)
        for j in range(k):
            wx = Xt[:, j] * mu
            XtWX[j] = wx @ Xt
            XtWz[j] = wx @ zt
        beta = np.linalg.solve(XtWX, XtWz)
        eta = z - (zt - Xt @ beta) + off            # fitted linear predictor incl. fixed effects
        del z, zt
        mu = np.exp(eta)
        with np.errstate(divide="ignore", invalid="ignore"):
            dev = 2 * np.sum(np.where(y > 0, y * np.log(y / mu), 0) - (y - mu))
        if verbose:
            print(f"  IRLS {it}: deviance {dev:.6f}", flush=True)
        if abs(dev - dev_old) / max(1.0, abs(dev)) < tol:
            break
        dev_old = dev
    # final partialled X at the converged weights, for the sandwich
    ws = dm.wsums(mu)
    for j in range(k):
        Xt[:, j] = dm.demean_col(j + 1, X[:, j], mu, ws, 1e-10)
    XtWX = np.empty((k, k))
    for j in range(k):
        XtWX[j] = (Xt[:, j] * mu) @ Xt
    bread = np.linalg.inv(XtWX)
    e = y - mu
    cl = pd.factorize(np.asarray(cluster))[0]
    G = cl.max() + 1
    S = np.zeros((G, k))
    for j in range(k):
        S[:, j] = np.bincount(cl, Xt[:, j] * e, G)
    meat = S.T @ S
    adj = G / (G - 1) * (n - 1) / (n - k)
    vcov = adj * bread @ meat @ bread
    se = np.sqrt(np.diag(vcov))
    out = pd.DataFrame({"coef": beta, "se": se}, index=names)
    out["z"] = out.coef / out.se
    from scipy.stats import norm
    out["p"] = 2 * norm.sf(np.abs(out.z))
    out.attrs.update(n=int(n), n_dropped=int((~keep).sum()), iterations=it, clusters=int(G),
                     vcov=pd.DataFrame(vcov, index=names, columns=names))
    return out


def pct(tab: pd.DataFrame) -> pd.DataFrame:
    """100 * (exp(b) - 1) with 95% CI."""
    t = tab.copy()
    t["pct"] = 100 * (np.exp(t.coef) - 1)
    t["pct_lo"] = 100 * (np.exp(t.coef - 1.96 * t.se) - 1)
    t["pct_hi"] = 100 * (np.exp(t.coef + 1.96 * t.se) - 1)
    return t
