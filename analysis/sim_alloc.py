"""Taxi-request allocation within one dispatch ring, shared by both simulation engines (decision 139).

Integer edge flows: the proportional fluid flow on every permitted edge (taxi cell i -> request cell j) is floored,
which is feasible by construction, and the remaining units are placed one at a time along permitted edges in a
seeded random order (weighted by the fractional parts), never exceeding the taxis left at i or the requests left
at j. Taxis dispatched and requests served are the row and column sums of the integer edge flows, so every
dispatch has a permitted partner. sim/engine.js and sim/v2/engine_v2.js implement the same algorithm.
"""
from __future__ import annotations

import numpy as np
from numba import njit

_EDGES = {}


def ring_edges(A):
    """(rows, cols) of a sparse ring matrix A (A[i, j] = 1: request cell j is in the ring of taxi cell i)."""
    key = id(A)
    hit = _EDGES.get(key)
    if hit is None or hit[0] is not A:                  # ids can be reused after garbage collection
        B = A.tocsr()
        rows = np.repeat(np.arange(B.shape[0]), np.diff(B.indptr)).astype(np.int64)
        hit = _EDGES[key] = (A, rows, B.indices.astype(np.int64))
    return hit[1], hit[2]


@njit(cache=True)
def _alloc(rows, cols, C, Q, V, seeds, uk):
    S = Q.shape[0]
    E = rows.size
    d = np.zeros((S, C), np.int64)
    q = np.zeros((S, C), np.int64)
    F = np.zeros((S, E), np.int64)
    for s in range(S):
        if Q[s].sum() == 0 or V[s].sum() == 0:
            continue
        P = np.zeros(C)
        for e in range(E):
            P[rows[e]] += Q[s, cols[e]]
        g = np.zeros(C)
        for i in range(C):
            if P[i] > 0:
                g[i] = min(V[s, i], P[i]) / P[i]
        inc = np.zeros(C)
        for e in range(E):
            inc[cols[e]] += g[rows[e]]
        sj = np.zeros(C)
        for j in range(C):
            R = Q[s, j] * inc[j]
            if R > 0:
                sj[j] = min(Q[s, j], R) / R
        ri = V[s].copy()
        rj = Q[s].copy()
        fr = np.zeros(E)
        tot = 0.0
        npos = 0
        for e in range(E):
            i, j = rows[e], cols[e]
            f = g[i] * Q[s, j] * sj[j]
            if f <= 0:
                continue
            fl = np.floor(f)
            if fl > ri[i]:
                fl = ri[i]
            if fl > rj[j]:
                fl = rj[j]
            F[s, e] = fl
            ri[i] -= fl
            rj[j] -= fl
            fr[e] = max(0.0, f - fl)
            tot += fr[e]
            if fr[e] > 1e-12:
                npos += 1
        K = int(np.floor(tot + uk[s]))
        if K <= 0 or npos == 0:
            for i in range(C):
                d[s, i] = V[s, i] - ri[i]
                q[s, i] = Q[s, i] - rj[i]
            continue
        # weighted random order over edges with a fractional part (larger fractions tend to come first)
        np.random.seed(seeds[s])
        idx = np.empty(npos, np.int64)
        keys = np.empty(npos)
        k = 0
        for e in range(E):
            if fr[e] > 1e-12:
                idx[k] = e
                keys[k] = np.random.random() ** (1.0 / fr[e])
                k += 1
        order = np.argsort(-keys)
        for k in range(npos):
            if K <= 0:
                break
            e = idx[order[k]]
            i, j = rows[e], cols[e]
            if ri[i] > 0 and rj[j] > 0:
                F[s, e] += 1
                ri[i] -= 1
                rj[j] -= 1
                K -= 1
        for i in range(C):
            d[s, i] = V[s, i] - ri[i]
            q[s, i] = Q[s, i] - rj[i]
    return d, q, F


def allocate(A, Q, V, rng, return_edges=False):
    """Allocate integer requests Q (S x C) to vacant taxis V (S x C) within ring A. Returns (taxis dispatched per
    taxi cell, requests served per request cell[, integer edge flows S x E with the ring's (rows, cols)]).
    Randomness comes from `rng` only (one seed and one uniform per simulated seed and call)."""
    rows, cols = ring_edges(A)
    S, C = Q.shape
    seeds = rng.integers(0, 2 ** 31 - 1, S)
    uk = rng.random(S)
    d, q, F = _alloc(rows, cols, C, np.ascontiguousarray(Q, np.int64), np.ascontiguousarray(V, np.int64), seeds, uk)
    return (d, q, F, rows, cols) if return_edges else (d, q)
