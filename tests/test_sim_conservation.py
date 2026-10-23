"""Conservation tests for the simulation v2 engine (review item 1: 11,534 requests produced 20,915 trips).

Run: .venv/bin/python -m pytest tests/test_sim_conservation.py -q
"""
import json

import numpy as np
from scipy import sparse

from analysis.sim_engine_v2 import World, allocate, simulate


def test_allocate_never_serves_more_than_requests_or_uses_more_taxis():
    rng = np.random.default_rng(1)
    C, S = 60, 5
    for _ in range(200):
        A = sparse.csr_matrix((rng.random((C, C)) < 0.3).astype(float))      # asymmetric adjacency
        Q = rng.poisson(rng.random((S, C)) * 3)
        V = rng.poisson(rng.random((S, C)) * 6)
        d, q = allocate(A, Q, V, rng.random(S))
        assert (d >= 0).all() and (q >= 0).all()
        assert (d <= V).all(), "a taxi cell dispatched more taxis than it had"
        assert (q <= Q).all(), "a request cell had more requests served than it held"
        assert (d.sum(1) == q.sum(1)).all(), "taxis dispatched differ from requests served"
        assert (d.sum(1) <= Q.sum(1)).all()


def test_overlapping_rings_do_not_double_serve():
    # many taxi cells all reach the same single request cell: the old rule let each of them take it
    C, S = 20, 1
    A = sparse.csr_matrix(np.ones((C, C)) - np.eye(C))
    Q = np.zeros((S, C), np.int64)
    Q[0, 0] = 3
    V = np.full((S, C), 5, np.int64)
    V[0, 0] = 0
    d, q = allocate(A, Q, V, np.array([0.5]))
    assert d.sum() == 3 and q.sum() == 3


def test_simulation_trips_never_exceed_requests():
    d = json.load(open("sim/v2/data.json"))
    w = World(d["cells"], d["T"], d["weights"], d["off_scale"])
    st = d["storms"][0]
    for mech in ("demand", "supply", "mix"):
        scen = {"mechanism": mech, "dest": "observed", "travel": "rain", "dispatch": "widening"}
        out = simulate(w, st, scen, {"occ0": 0.3, "kappa": 1.3, "beta_dem": 2.0, "beta_off": 0.05}, S=3, seed=7,
                       record_cells=False, policy=True)
        assert (out["served"] <= out["requests"]).all(), (out["served"], out["requests"])


def test_step8_engine_trips_never_exceed_requests():
    from analysis import sim_engine as v1
    d = json.load(open("sim/data.json"))
    w = v1.World(d["cells"])
    for mech in ("demand", "mix"):
        scen = {"mechanism": mech, "dest": "mrt", "travel": "rain", "dispatch": "widening"}
        out = v1.simulate(w, d["storms"][0], scen, {"occ0": 0.3, "kappa": 1.3, "beta_dem": 2.0, "beta_off": 0.05}, S=3,
                          seed=7, record_cells=False, policy=True)
        assert (out["served"] <= out["requests"]).all()
