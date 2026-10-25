"""One-to-one assignment and flicker accounting for anonymous taxi coordinates."""
from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def assign(a, b, radius):
    """Maximum-cardinality, then minimum-distance matching on the KD-tree graph.

    Dense assignment is confined to connected components. Dummy costs dominate the
    maximum possible sum of real distances, so real-edge cardinality comes first.
    Coordinate multiplicities are retained. No greedy exact-match shortcut is used.
    """
    a, b = np.asarray(a), np.asarray(b)
    if not len(a) or not len(b):
        return np.empty(0, int), np.empty(0, int), np.empty(0)
    graph = cKDTree(a).sparse_distance_matrix(cKDTree(b), radius, output_type="coo_matrix")
    if not graph.nnz:
        return np.empty(0, int), np.empty(0, int), np.empty(0)
    edges = coo_matrix((np.ones(graph.nnz), (graph.row, len(a)+graph.col)),
                       shape=(len(a)+len(b), len(a)+len(b)))
    _, labels = connected_components(edges, directed=False)
    edge_labels = labels[graph.row]
    order = np.argsort(edge_labels, kind="stable")
    groups = np.split(order, np.flatnonzero(np.diff(edge_labels[order]))+1)
    aa, bb, dd = [], [], []
    for group in groups:
        ia, ra = np.unique(graph.row[group], return_inverse=True)
        ib, rb = np.unique(graph.col[group], return_inverse=True)
        n, m = len(ia), len(ib)
        penalty = (min(n, m)+1)*(radius+1)
        # Each origin can choose any dummy; invalid real edges cost more than a dummy.
        cost = np.full((n, m+n), 2*penalty)
        cost[:, m:] = penalty
        cost[ra, rb] = graph.data[group]
        i, j = linear_sum_assignment(cost)
        keep = (j < m) & (cost[i, j] < penalty)
        aa.extend(ia[i[keep]])
        bb.extend(ib[j[keep]])
        dd.extend(cost[i[keep], j[keep]])
    return np.asarray(aa, int), np.asarray(bb, int), np.asarray(dd)


def dense_points(xy, limit=30):
    cells = np.floor(xy/500).astype("int64")
    _, inv, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    return counts[inv] > limit


def cancel_flicker(events):
    """Cancel appearance/disappearance pairs <=120 seconds and <=200 m, one to one.

    events: list of dictionaries with kind ('D'/'A'), time (seconds), xy, cell,
    dense, removed. This is an offline observation filter, not a forecast feature.
    Returns bridge records for spatial stock-flow accounting across the gap.
    """
    pending, bridges, by_time = [], [], {}
    for i, event in enumerate(events):
        by_time.setdefault(event["time"], []).append(i)
    for time, new in sorted(by_time.items()):
        pending = [i for i in pending if 0 < time-events[i]["time"] <= 120 and not events[i].get("removed", False)]
        appearances = [i for i in new if events[i]["kind"] == "A"]
        if pending and appearances:
            ia, ib, _ = assign(np.array([events[i]["xy"] for i in pending]),
                               np.array([events[i]["xy"] for i in appearances]), 200)
            for a, b in zip(ia, ib):
                left, right = pending[a], appearances[b]
                events[left]["removed"] = events[right]["removed"] = True
                bridges.append((left, right))
        pending.extend(i for i in new if events[i]["kind"] == "D")
    return bridges


def conservation(n_a, n_b, ia, ib):
    assert len(np.unique(ia)) == len(ia)
    assert len(np.unique(ib)) == len(ib)
    D, A = n_a-len(ia), n_b-len(ib)
    assert n_b-n_a == A-D
    return D, A
