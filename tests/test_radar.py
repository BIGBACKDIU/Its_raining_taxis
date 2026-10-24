"""Step-21 time-window and missing-pixel safeguards; no large local data required."""
import numpy as np
import pandas as pd
from scipy import sparse

from analysis.prep_radar import Agreement, mean_pixels, snapshot_windows


def test_snapshot_windows_include_end_and_exclude_left_boundary_across_midnight():
    index = pd.date_range('2022-03-31 22:00', '2022-04-01 00:30', freq='5min')
    d = pd.DataFrame({123: np.arange(len(index), dtype='float32')}, index=index)
    current, lag1, lag2 = snapshot_windows(d)
    t = pd.Timestamp('2022-04-01 00:00')
    for got, end in [(current, t), (lag1, t - pd.Timedelta(minutes=30)), (lag2, t - pd.Timedelta(minutes=60))]:
        expected = d[(d.index > end - pd.Timedelta(minutes=30)) & (d.index <= end)].sum().iloc[0] * 2
        assert got.loc[t, 123] == expected
    incomplete = d.drop(pd.Timestamp('2022-03-31 23:40'))
    assert np.isnan(snapshot_windows(incomplete)[0].loc[t, 123])


def test_spatial_mean_requires_all_selected_land_pixels():
    values = np.array([[1, 3, 100], [1, np.nan, 100]], dtype='float32')
    weights = sparse.csr_matrix([[1, 1, 0], [0, 0, 0]], dtype='float32')
    out = mean_pixels(values, weights)
    assert out[0, 0] == 2  # a high-valued sea pixel is not part of this land-cell mean
    assert np.isnan(out[1, 0])
    assert np.isnan(out[:, 1]).all()


def test_agreement_confusion_labels_and_missing_pairs():
    a = Agreement()
    a.add(np.array([0., 1., 0., 11., np.nan]), np.array([0., 0., 1., 12., 4.]))
    wet, _, heavy = a.rows('test')
    assert wet['n'] == 4
    assert wet['both_dry'] == wet['both_wet'] == wet['gauge_only_wet'] == wet['radar_only_wet'] == 1
    assert heavy['agreement'] == 1
