"""Conservation and feasibility tests for the simulation engines (decisions 127, 139).

Run: .venv/bin/python -m pytest tests/test_sim_conservation.py -q
`check_step8_engine(module)` is written so it can also be pointed at the pre-fix engine (commit 37081c1), where it
fails: there, taxi cells in overlapping rings all took the same requests.
"""
import json

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import maximum_flow

from analysis.sim_alloc import allocate


def _maxflow(A, d, q):
    """Exact max flow of source -> taxi cell i (cap d_i) -> request cell j (A_ij = 1) -> sink (cap q_j)."""
    C = len(d)
    n = 2 * C + 2
    ii, jj = A.nonzero()
    r = np.r_[np.zeros(C, int), 1 + np.arange(C) + C, 1 + ii]
    c = np.r_[1 + np.arange(C), np.full(C, n - 1), 1 + C + jj]
    w = np.r_[d, q, np.full(len(ii), 10 ** 6)].astype(np.int32)
    return maximum_flow(sparse.csr_matrix((w, (r, c)), shape=(n, n)), 0, n - 1).flow_value


def test_allocation_feasible_against_exact_max_flow():
    rng = np.random.default_rng(2702)
    for _ in range(3000):
        C = int(rng.integers(3, 14))
        A = sparse.csr_matrix((rng.random((C, C)) < rng.uniform(0.15, 0.6)).astype(float))   # asymmetric ring
        Q = rng.integers(0, 5, (1, C))
        V = rng.integers(0, 5, (1, C))
        d, q = allocate(A, Q, V, rng)
        assert (d >= 0).all() and (q >= 0).all() and (d <= V).all() and (q <= Q).all()
        assert d.sum() == q.sum()
        assert _maxflow(A, d[0], q[0]) == d.sum(), "totals that no matching within the ring can achieve"


def test_every_dispatch_has_a_permitted_partner():
    rng = np.random.default_rng(7)
    for _ in range(500):
        C, S = int(rng.integers(3, 30)), 3
        A = sparse.csr_matrix((rng.random((C, C)) < 0.3).astype(float))
        Q = rng.poisson(rng.random((S, C)) * 3)
        V = rng.poisson(rng.random((S, C)) * 5)
        d, q, F, rows, cols = allocate(A, Q, V, rng, return_edges=True)
        assert (F >= 0).all()
        assert (A.toarray()[rows, cols] == 1).all(), "flow on an edge outside the ring"
        for s in range(S):
            assert (np.bincount(rows, F[s], C) == d[s]).all(), "dispatch without a permitted request partner"
            assert (np.bincount(cols, F[s], C) == q[s]).all(), "served request without a permitted taxi partner"


def test_overlapping_rings_do_not_double_serve():
    C = 20
    A = sparse.csr_matrix(np.ones((C, C)) - np.eye(C))
    Q = np.zeros((1, C), np.int64)
    Q[0, 0] = 3
    V = np.full((1, C), 5, np.int64)
    V[0, 0] = 0
    d, q = allocate(A, Q, V, np.random.default_rng(0))
    assert d.sum() == 3 and q.sum() == 3


def check_step8_engine(engine):
    """Five cells: requests almost only at the centre, taxis only at the four neighbours 1 km away, all inside
    the first dispatch ring of each other. Trips must never exceed requests."""
    cells = {"cell": [0, 1, 2, 3, 4], "x_km": [0.0, 1.0, -1.0, 0.0, 0.0], "y_km": [0.0, 0.0, 0.0, 1.0, -1.0],
             "mrt_exits": [200, 0, 0, 0, 0], "stands": [1, 1, 1, 1, 1], "centre": [0, 0, 0, 0, 0]}
    w = engine.World(cells)
    storm = {"minutes": 60, "rain": [[0.0] * 5] * 3, "base": [[1.0] * 5] * 3, "v0": [0, 30, 30, 30, 30],
             "snap_minutes": [0, 30, 59], "share": 0.6}
    scen = {"mechanism": "demand", "dest": "mrt", "travel": "dry", "dispatch": "nearest"}
    out = engine.simulate(w, storm, scen, {"occ0": 0.2, "kappa": 1.3, "beta_dem": 0.0, "beta_off": 0.0}, S=3, seed=1,
                          record_cells=False)
    assert (out["served"] <= out["requests"]).all(), (out["requests"], out["served"])


def test_step8_engine_constructed_world():
    from analysis import sim_engine
    check_step8_engine(sim_engine)


def test_v2_engine_trips_never_exceed_requests():
    from analysis.sim_engine_v2 import World, simulate
    d = json.load(open("sim/v2/data.json"))
    w = World(d["cells"], d["T"], d["weights"], d["off_scale"])
    for mech in ("demand", "supply", "mix"):
        scen = {"mechanism": mech, "dest": "observed", "travel": "rain", "dispatch": "widening"}
        out = simulate(w, d["storms"][0], scen, {"occ0": 0.3, "kappa": 1.3, "beta_dem": 2.0, "beta_off": 0.05}, S=3,
                       seed=7, record_cells=False, policy=True)
        assert (out["served"] <= out["requests"]).all(), (out["served"], out["requests"])


def test_javascript_allocator_matches_rules():
    """The browser port: edge flows only on ring edges, totals are their row / column sums, within capacities."""
    import shutil
    import subprocess
    if shutil.which("node") is None:
        return
    js = r"""
const {allocateRing, RNG} = require('./sim/v2/engine_v2.js'); const r = new RNG(1); let bad = 0;
for (let t = 0; t < 3000; t++) { const C = 3 + Math.floor(r.random() * 9); const adj = [];
  for (let i = 0; i < C; i++) { const row = []; for (let j = 0; j < C; j++) if (r.random() < 0.35) row.push(j); adj.push(row); }
  const Q = Float64Array.from({length: C}, () => Math.floor(r.random() * 4));
  const V = Int32Array.from({length: C}, () => Math.floor(r.random() * 4)); const a = allocateRing(adj, Q, V, r);
  const rs = new Int32Array(C), cs = new Int32Array(C);
  for (let e = 0; e < a.F.length; e++) { if (a.F[e] < 0 || !adj[a.ei[e]].includes(a.ej[e])) bad++; rs[a.ei[e]] += a.F[e]; cs[a.ej[e]] += a.F[e]; }
  for (let i = 0; i < C; i++) if (rs[i] !== a.d[i] || cs[i] !== a.q[i] || a.d[i] > V[i] || a.q[i] > Q[i]) bad++; }
console.log(bad);"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "0", out
