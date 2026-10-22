"""Low-memory Poisson (and logit) regression with high-dimensional fixed effects and day-clustered errors.

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


def _drop_separated(y, fes, family="poisson"):
    """Drop rows in fixed-effect groups with no outcome variation that the model can fit (Poisson: all zero;
    logit: all zero or all one), repeatedly. Their effects are infinite and they carry no information."""
    keep = np.ones(len(y), bool)
    while True:
        bad = np.zeros(len(y), bool)
        for g in fes:
            s = np.bincount(g[keep], y[keep], g.max() + 1)
            if family == "poisson":
                bad |= keep & (s[g] <= 0)
            else:
                c = np.bincount(g[keep], minlength=g.max() + 1)
                bad |= keep & ((s[g] <= 0) | (s[g] >= c[g]))
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


def fepois(y, X, names, fes, cluster, offset=None, **kw):
    """Poisson PML with fixed effects (see feglm)."""
    return feglm(y, X, names, fes, cluster, offset=offset, family="poisson", **kw)


def felogit(y, X, names, fes, cluster, **kw):
    """Logit with fixed effects (see feglm)."""
    return feglm(y, X, names, fes, cluster, family="logit", **kw)


def _dot(a, B, w=None):
    """a' diag(w) B column by column (B may be float32), accumulated in float64."""
    aw = a if w is None else a * w
    return np.array([aw @ B[:, i].astype("float64") for i in range(B.shape[1])])


def feglm(y, X, names, fes, cluster, offset=None, family="poisson", tol=1e-8, maxit=50, xt_dtype="float64",
          verbose=False):
    """GLM with canonical link (Poisson log / binomial logit) and fixed effects, CRV1 errors by cluster.

    y (n,), X (n, k), fes: list of int-like arrays, cluster: array. xt_dtype="float32" halves the memory of the
    partialled regressors (each column is demeaned in float64 and stored in float32).
    Returns a DataFrame with coef, se, z, p and attributes n, n_dropped, iterations, clusters, vcov.
    """
    y = np.asarray(y, "float64")
    X = np.asarray(X)
    fes = [pd.factorize(np.asarray(g))[0] for g in fes]
    keep = _drop_separated(y, fes, family)
    if not keep.all():
        y, X = y[keep], X[keep]
        fes = [pd.factorize(g[keep])[0] for g in fes]
        cluster = np.asarray(cluster)[keep]
        offset = None if offset is None else np.asarray(offset)[keep]
    off = np.zeros(len(y)) if offset is None else np.asarray(offset, "float64")
    n, k = X.shape
    dm = Demeaner(fes, k + 1)
    if family == "poisson":
        mu = (y + y.mean()) / 2
        eta = np.log(mu)
    else:
        mu = (y + y.mean()) / 2
        eta = np.log(mu / (1 - mu))

    def weights(mu):
        return mu if family == "poisson" else mu * (1 - mu)

    def deviance(y, mu):
        with np.errstate(divide="ignore", invalid="ignore"):
            if family == "poisson":
                return 2 * np.sum(np.where(y > 0, y * np.log(y / mu), 0) - (y - mu))
            return -2 * np.sum(y * np.log(mu) + (1 - y) * np.log(1 - mu))

    beta = np.zeros(k)
    dev_old = np.inf
    Xt = np.empty((n, k), dtype=xt_dtype)
    for it in range(1, maxit + 1):
        tol_it = max(1e-10, min(1e-4, 1e-3 * 10 ** -it))
        w = weights(mu)
        ws = dm.wsums(w)
        z = eta - off + (y - mu) / w
        zt = dm.demean_col(0, z, w, ws, tol_it)
        for j in range(k):
            Xt[:, j] = dm.demean_col(j + 1, X[:, j], w, ws, tol_it)
        XtWX = np.array([_dot(Xt[:, j].astype("float64"), Xt, w) for j in range(k)])
        XtWz = _dot(zt, Xt, w)
        beta = np.linalg.solve(XtWX, XtWz)
        fitted_x = np.zeros(n)
        for j in range(k):
            fitted_x += Xt[:, j] * beta[j]
        eta = z - (zt - fitted_x) + off             # fitted linear predictor incl. fixed effects
        del z, zt, fitted_x
        mu = np.exp(eta) if family == "poisson" else 1 / (1 + np.exp(-eta))
        if family == "logit":
            mu = np.clip(mu, 1e-12, 1 - 1e-12)
        dev = deviance(y, mu)
        if verbose:
            print(f"  IRLS {it}: deviance {dev:.6f}", flush=True)
        if abs(dev - dev_old) / max(1.0, abs(dev)) < tol:
            break
        dev_old = dev
    # final partialled X at the converged weights, for the sandwich
    w = weights(mu)
    ws = dm.wsums(w)
    for j in range(k):
        Xt[:, j] = dm.demean_col(j + 1, X[:, j], w, ws, 1e-10)
    XtWX = np.array([_dot(Xt[:, j].astype("float64"), Xt, w) for j in range(k)])
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
                     vcov=pd.DataFrame(vcov, index=names, columns=names), family=family)
    return out


def odds(tab: pd.DataFrame) -> pd.DataFrame:
    """Odds ratios exp(b) with 95% CI (logit)."""
    t = tab.copy()
    t["or"] = np.exp(t.coef)
    t["or_lo"] = np.exp(t.coef - 1.96 * t.se)
    t["or_hi"] = np.exp(t.coef + 1.96 * t.se)
    return t


def pct(tab: pd.DataFrame) -> pd.DataFrame:
    """100 * (exp(b) - 1) with 95% CI."""
    t = tab.copy()
    t["pct"] = 100 * (np.exp(t.coef) - 1)
    t["pct_lo"] = 100 * (np.exp(t.coef - 1.96 * t.se) - 1)
    t["pct_hi"] = 100 * (np.exp(t.coef + 1.96 * t.se) - 1)
    return t
