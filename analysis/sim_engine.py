"""Cell-based agent simulation of vacant taxis during a storm (step 8). Scenario-based operational model.

The same rules are ported to JavaScript in sim/engine.js (the web page); keep the two in step.
State per seed: vacant and offline taxi counts per cell; occupied / repositioning taxis are stored by arrival
minute and destination cell (fleet conserved exactly). See outputs/decisions.md items 72-79.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse

RING_EDGES = [0.0, 1.5, 2.5, 3.2, 5.0, 8.0]          # km; rings 1-3 = 3.2 km dispatch, 4-5 = widening
PATIENCE_MIN = 6.0
DETOUR = 1.3
SPEED = {"dry": 30.0, "rain": 20.0}                     # km/h
HORIZON_PAD = 150


class World:
    def __init__(self, cells: dict):
        self.C = len(cells["cell"])
        self.x = np.asarray(cells["x_km"], float)
        self.y = np.asarray(cells["y_km"], float)
        self.D = np.hypot(self.x[:, None] - self.x[None, :], self.y[:, None] - self.y[None, :])
        self.rings = []
        for a, b in zip(RING_EDGES[:-1], RING_EDGES[1:]):
            A = ((self.D > a) & (self.D <= b)).astype(float)
            self.rings.append((sparse.csr_matrix(A), (a + b) / 2))
        self.mrt = np.asarray(cells["mrt_exits"], float)
        self.stands = np.asarray(cells["stands"], float)
        self.centre = np.asarray(cells["centre"], float)
        attr_mrt = 0.5 + self.mrt
        attr_lu = (1 + self.centre) * (1 + self.stands)
        self.attr = {"mrt": attr_mrt / attr_mrt.sum(), "landuse": attr_lu / attr_lu.sum()}
        self.P = {"mrt": self._gravity(attr_mrt, 10.0), "landuse": self._gravity(attr_lu, 4.0)}
        self.cum = {k: self._cum(v) for k, v in self.P.items()}

    def _gravity(self, a, scale):
        P = a[None, :] * np.exp(-self.D / scale)
        return P / P.sum(1, keepdims=True)

    def _cum(self, P):
        c = np.cumsum(P, 1)
        c[:, -1] = 1.0
        return (c + np.arange(self.C)[:, None]).ravel()          # row r occupies (r, r + 1]

    def mean_trip_minutes(self, dest, speed):
        P = self.P[dest]
        t = DETOUR * self.D / speed * 60 + 2
        return float((self.attr[dest][:, None] * P * t).sum() + 1)


def sample_dest(world, dest, origins, rng):
    u = rng.random(len(origins))
    idx = np.searchsorted(world.cum[dest], origins + u, side="left")
    return np.clip(idx - origins * world.C, 0, world.C - 1)


def systematic_round(x, u):
    """Integer vector per row with each entry floor(x) or ceil(x), row total floor(sum + u) - floor(u) (u in [0, 1)
    per row): unbiased, keeps every entry within its bounds and gives two vectors with equal sums equal totals."""
    c = np.cumsum(x, 1)
    k = np.floor(c + u[:, None])
    return np.diff(np.concatenate([np.floor(u)[:, None], k], 1), axis=1).astype(np.int64)


def allocate(A, Q, V, u):
    """Match waiting requests Q (integers, S x C) to vacant taxis V (S x C) within one ring.
    A[i, j] = 1 when request cell j is in the ring of taxi cell i (outgoing adjacency of i; incoming of j).
    Proportional fluid flows: taxi cell i offers min(V_i, P_i) over its reachable requests P_i = sum_j A_ij Q_j;
    request cell j accepts at most Q_j of what it receives (incoming sum over i). Both sides are rounded with the
    same systematic offset, so taxis dispatched = requests served exactly, no request is served twice and no
    taxi leaves twice. Returns (taxis dispatched per taxi cell, requests served per request cell)."""
    P = (A @ Q.T).T
    o = np.minimum(V, P)
    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.where(P > 0, o / P, 0.0)
    R = Q * (A.T @ g.T).T                                       # offers received by request cell j (incoming)
    served = np.minimum(Q, R)
    with np.errstate(divide="ignore", invalid="ignore"):
        sj = np.where(R > 0, served / R, 0.0)
    used = g * (A @ (Q * sj).T).T                               # taxis used per taxi cell; sums equal served
    used = np.minimum(used, V)
    d = systematic_round(used, u)
    q = systematic_round(served, u)
    gap = d.sum(1) - q.sum(1)                                   # floating-point ties only
    for s in np.flatnonzero(gap):
        k = int(abs(gap[s]))
        if gap[s] > 0:
            idx = np.flatnonzero(d[s] > 0)[:k]
            d[s, idx] -= 1
        else:
            idx = np.flatnonzero(q[s] > 0)[:k]
            q[s, idx] -= 1
    return d, q


def stochastic_round(a, rng):
    f = np.floor(a)
    return (f + (rng.random(a.shape) < (a - f))).astype(np.int64)


def greedy_plan(world, vac, base_now, base_next, mu, rain, share, N=200, lam=0.005, lead=60, travel="rain",
                weights=None, kmax=20, s0_min=0.05):
    """Step-7 objective solved greedily by marginal value (same objective as the PuLP model; see decision 79)."""
    from scipy.stats import poisson
    C = world.C
    movable = np.floor(share * np.maximum(0, vac - base_now)).astype(int)
    ys = np.arange(0, int(np.ceil(base_next.max())) + kmax + 2)
    pmf = poisson.pmf(ys[None, :], np.maximum(mu, 1e-6)[:, None])
    S = np.zeros((C, kmax + 1))
    for m in range(kmax + 1):
        S[:, m] = (np.maximum(0, base_next[:, None] - (ys[None, :] + m)) * pmf).sum(1) / np.maximum(1, base_next)
    r = S[:, :-1] - S[:, 1:]
    w = np.ones(C) if weights is None else weights
    dest_ok = (base_next >= 4) & (world.stands > 0) & (S[:, 0] >= s0_min)
    speed = np.where((rain > 0) & (travel == "rain"), SPEED["rain"], SPEED["dry"])
    T = DETOUR * world.D / speed[:, None] * 60                              # minutes, by origin speed
    origins = np.flatnonzero(movable > 0)
    dests = np.flatnonzero(dest_ok)
    moves = {}
    if len(origins) == 0 or len(dests) == 0:
        return moves
    got = np.zeros(C, int)
    left = movable.copy()
    budget = N
    Tod = T[np.ix_(origins, dests)]
    feasible = (Tod <= lead) & (origins[:, None] != dests[None, :])
    while budget > 0:
        k = np.minimum(got[dests], kmax - 1)
        gain = w[dests] * r[dests, k] * (got[dests] < kmax)
        val = gain[None, :] - lam * Tod
        val = np.where(feasible & (left[origins][:, None] > 0), val, -np.inf)
        a, b = np.unravel_index(np.argmax(val), val.shape)
        if not np.isfinite(val[a, b]) or val[a, b] <= 0:
            break
        i, j = origins[a], dests[b]
        moves[(i, j)] = moves.get((i, j), 0) + 1
        got[j] += 1
        left[i] -= 1
        budget -= 1
    return {k: (v, T[k[0], k[1]]) for k, v in moves.items()}


def simulate(world, storm, scen, params, S=10, seed=2702, policy=False, rain_mult=1.0, record_cells=True):
    """Run one storm. storm: dict with minutes, rain (slots x C, mm/h, 30-min slots), base (slots x C),
    v0 (C,), snap_minutes, share. scen: mechanism, dest, travel, dispatch, demand_level.
    params: occ0, kappa, beta_dem, beta_off. Returns a dict of arrays."""
    rng = np.random.default_rng(seed)
    C, M = world.C, int(storm["minutes"])
    rain = np.asarray(storm["rain"], float) * rain_mult
    base = np.asarray(storm["base"], float)
    v0 = np.asarray(storm["v0"], int)
    dest = scen["dest"]
    mech = scen["mechanism"]
    dl = scen.get("demand_level", 1.0)
    occ0 = params["occ0"]
    O0 = int(round(v0.sum() * occ0 / (1 - occ0)))
    tau = world.mean_trip_minutes(dest, SPEED["dry"])
    lam_total = O0 / tau * params["kappa"]
    attr = world.attr[dest]
    V = np.tile(v0, (S, 1)).astype(np.int64)
    OFF = np.zeros((S, C), np.int64)
    ARR = np.zeros((S, M + HORIZON_PAD, C), np.int32)
    # initial occupied taxis finish their trips over the first 30 minutes at attraction-weighted cells
    for s in range(S):
        o = rng.choice(C, size=O0, p=attr)
        t = rng.integers(1, 31, size=O0)
        np.add.at(ARR[s], (t, o), 1)
    Qw = np.zeros((S, C), np.int64)                     # waiting requests (integers)
    B_city0 = base[0].sum()
    stats = {"requests": np.zeros(S), "served": np.zeros(S), "abandoned": np.zeros(S), "wait_minutes": np.zeros(S),
             "requests_rain": np.zeros(S), "abandoned_rain": np.zeros(S)}
    snaps = list(storm["snap_minutes"])
    city = np.zeros((S, len(snaps)))
    cells_mean = np.zeros((len(snaps), C)) if record_cells else None
    moves_log = []
    seed_rows = np.repeat(np.arange(S), C)

    inflight = ARR.sum((1, 2)).astype(np.int64)          # taxis occupied or repositioning, per seed
    fleet = V.sum(1) + inflight                          # changes only through the time-of-day path

    def start_trips(cnt, approach, m, speed):
        nonlocal inflight
        inflight += cnt.sum(1)
        flat = cnt.ravel()
        nz = np.flatnonzero(flat)
        if len(nz) == 0:
            return
        rep = flat[nz]
        s_idx = np.repeat(seed_rows[nz], rep)
        o_idx = np.repeat(nz % C, rep)
        d_idx = sample_dest(world, dest, o_idx, rng)
        dur = approach + DETOUR * world.D[o_idx, d_idx] / speed[o_idx] * 60 + 2
        ta = np.minimum(m + np.ceil(dur).astype(int), M + HORIZON_PAD - 1)
        np.add.at(ARR, (s_idx, ta, d_idx), 1)

    def match(Q, rings, m, speed):
        """Requests Q are integers; returns requests served (= trips started) per seed (decision 127)."""
        served_total = np.zeros(S, np.int64)
        own = np.minimum(V, Q).astype(np.int64)
        V[:] -= own
        Q -= own
        served_total += own.sum(1)
        start_trips(own, 1.0, m, speed)
        for A, mid in rings:
            if not Q.any() or not V.any():
                break
            d, q = allocate(A, Q, V, rng.random(S))
            V[:] -= d
            Q -= q
            served_total += d.sum(1)
            start_trips(q, mid / speed.mean() * 60, m, speed)                   # trips start at the request cells (decision 138)
        assert (V >= 0).all() and (Q >= 0).all(), "negative taxis or requests after matching"
        return served_total

    for m in range(M):
        slot = min(m // 30, rain.shape[0] - 1)
        r = rain[slot]
        raining = r > 0
        speed = np.where(raining & (scen["travel"] == "rain"), SPEED["rain"], SPEED["dry"])
        V += ARR[:, m]
        inflight -= ARR[:, m].sum(1)
        # normal time-of-day path: taxis on the road follow the citywide baseline
        if m % 30 == 0 and m > 0:
            onroad = V.sum(1) + OFF.sum(1) + inflight                          # offline taxis are still on shift
            target = (v0.sum() + O0) * base[slot].sum() / B_city0
            diff = np.round(target - onroad).astype(int)
            for s in range(S):
                if diff[s] > 0:
                    add = rng.multinomial(diff[s], base[slot] / base[slot].sum())
                    V[s] += add
                    fleet[s] += add.sum()
                elif diff[s] < 0 and V[s].sum() > 0:
                    rem = np.minimum(rng.multinomial(min(-diff[s], V[s].sum()), V[s] / V[s].sum()), V[s])
                    V[s] -= rem
                    fleet[s] -= rem.sum()
        # supply drop
        if mech in ("supply", "mix"):
            p_off = params["beta_off"] * np.minimum(r, 30) / 30
            off = rng.binomial(V, np.broadcast_to(p_off, V.shape))
            V -= off
            OFF += off
        back = rng.binomial(OFF, np.broadcast_to(np.where(raining, 0.0, 1 / 30), OFF.shape))
        OFF -= back
        V += back
        # policy decisions every 30 minutes (seed-mean state, persistence forecast)
        if policy and m % 30 == 0 and m > 0:
            nxt = min(slot + 2, base.shape[0] - 1)
            vm = V.mean(0)
            plan = greedy_plan(world, vm, base[slot], base[nxt], vm, r, storm["share"], travel=scen["travel"])
            for (i, j), (n, tt) in plan.items():
                mv = np.minimum(n, V[:, i])
                V[:, i] -= mv
                ARR[:, min(m + int(np.ceil(tt)), M + HORIZON_PAD - 1), j] += mv.astype(np.int32)
                inflight += mv
            moves_log.append({"minute": m, "moves": [(int(i), int(j), int(n)) for (i, j), (n, _) in plan.items()]})
        # waiting requests: abandon, then match (wider rings if widening dispatch)
        rain_city = r.mean() > 0.5
        ab = rng.binomial(Qw, 1 / PATIENCE_MIN)          # geometric patience, mean 6 minutes
        Qw -= ab
        stats["abandoned"] += ab.sum(1)
        if rain_city:
            stats["abandoned_rain"] += ab.sum(1)
        rings_w = world.rings[:5] if scen["dispatch"] == "widening" else world.rings[:3]
        n_wait = Qw.sum(1)
        served_w = match(Qw, rings_w, m, speed)
        stats["served"] += served_w
        stats["wait_minutes"] += Qw.sum(1)
        # new requests
        lam = lam_total * attr * dl
        if mech in ("demand", "mix"):
            lam = lam * (1 + params["beta_dem"] * np.minimum(r, 30) / 10)
        new = rng.poisson(np.broadcast_to(lam, (S, C))).astype(np.int64)
        n_new = new.sum(1)
        stats["requests"] += new.sum(1)
        if rain_city:
            stats["requests_rain"] += new.sum(1)
        served_new = match(new, world.rings[:3], m, speed)
        stats["served"] += served_new
        Qw += new
        # conservation: taxis (vacant + offline + in flight) equal the fleet; trips never exceed requests
        assert (V.sum(1) + OFF.sum(1) + inflight == fleet).all(), f"taxis not conserved at minute {m}"
        assert (served_w <= n_wait).all() and (served_new <= n_new).all(), f"more trips than requests at minute {m}"
        assert (stats["served"] <= stats["requests"]).all(), f"more trips than requests by minute {m}"
        if m in snaps:
            k = snaps.index(m)
            city[:, k] = V.sum(1)
            if record_cells:
                cells_mean[k] = V.mean(0)
    out = {"city": city, "cells_mean": cells_mean, "moves": moves_log, **stats}
    out["final_V"] = V
    return out
