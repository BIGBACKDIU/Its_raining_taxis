import numpy as np

from analysis.s23_matching import assign, cancel_flicker, conservation, dense_points


def test_assignment_cardinality_precedes_distance():
    # Greedily taking the zero-distance edge loses the second possible match.
    a = np.array([[0., 0.], [-.9, 0.]])
    b = np.array([[0., 0.], [.9, 0.]])
    ia, ib, distance = assign(a, b, 1.)
    assert len(ia) == 2
    assert np.isclose(distance.sum(), 1.8)
    assert conservation(2, 2, ia, ib) == (0, 0)


def test_assignment_never_reuses_points_or_exceeds_radius():
    a = np.array([[0., 0.], [0., 0.], [100., 0.]])
    b = np.array([[0., 0.], [1., 0.], [500., 0.]])
    ia, ib, d = assign(a, b, 2.)
    assert len(ia) == 2 and np.max(d) <= 2.
    assert conservation(3, 3, ia, ib) == (1, 1)
    assert len(assign(a[:0], b, 2.)[0]) == 0


def test_flicker_is_one_to_one_and_time_limited():
    events = [dict(kind="D", time=0., xy=np.array([0., 0.])),
              dict(kind="A", time=60., xy=np.array([100., 0.])),
              dict(kind="A", time=90., xy=np.array([100., 0.])),
              dict(kind="D", time=120., xy=np.array([2000., 0.])),
              dict(kind="A", time=241., xy=np.array([2000., 0.]))]
    bridges = cancel_flicker(events)
    assert bridges == [(0, 1)]
    assert events[0]["removed"] and events[1]["removed"]
    assert not events[2].get("removed", False)
    assert not events[4].get("removed", False)


def test_dense_zones_use_count_and_500m_grid():
    xy = np.r_[np.zeros((31, 2)), [[500., 500.]]]
    assert dense_points(xy).sum() == 31


def test_zero_pairs_never_opens_minute_data(tmp_path, monkeypatch):
    import importlib
    flow = importlib.import_module("analysis.23_flows")
    (tmp_path / "s23_sample.csv").write_text("pair,storm_day,dry_day,onset,regime,onset_share,gauges\n")
    monkeypatch.setattr(flow, "TABLES", tmp_path)
    monkeypatch.setattr(flow, "LOCAL", tmp_path / "local")
    def forbidden(*args, **kwargs):
        raise AssertionError("Empty design must not open or analyse minute positions")
    monkeypatch.setattr(flow, "unpack", forbidden)
    flow.run()
    assert (tmp_path / "s23_flow_audit.csv").read_text().count("\n") == 1
