"""A simple metric grid over Singapore.

Coordinates are projected with a local equirectangular projection centred on
Singapore (distortion well under 0.1% across the island), so a 500 m cell is
500 m on the ground. 1 km cells nest exactly: cell_1km = cell_500m // 2.
"""
from __future__ import annotations

import numpy as np

LON0, LAT0 = 103.55, 1.15          # south-west of Singapore, so x and y are positive
_PHI = np.deg2rad(1.35)            # reference latitude for the metre conversion
M_PER_DEG_LAT = 111132.92 - 559.82 * np.cos(2 * _PHI) + 1.175 * np.cos(4 * _PHI)
M_PER_DEG_LON = 111412.84 * np.cos(_PHI) - 93.5 * np.cos(3 * _PHI)
ENC = 1000                         # cell id = cx * ENC + cy


def to_xy(lon, lat):
    lon, lat = np.asarray(lon, dtype="float64"), np.asarray(lat, dtype="float64")
    return (lon - LON0) * M_PER_DEG_LON, (lat - LAT0) * M_PER_DEG_LAT


def to_lonlat(x, y):
    return np.asarray(x) / M_PER_DEG_LON + LON0, np.asarray(y) / M_PER_DEG_LAT + LAT0


def cell_ids(lon, lat, size: int = 500) -> np.ndarray:
    x, y = to_xy(lon, lat)
    cx, cy = np.floor(x / size).astype("int64"), np.floor(y / size).astype("int64")
    return (cx * ENC + cy).astype("int32")


def split_id(cell):
    cell = np.asarray(cell, dtype="int64")
    return cell // ENC, cell % ENC


def coarsen(cell500, factor: int = 2) -> np.ndarray:
    """500 m cell ids -> (500 * factor) m cell ids."""
    cx, cy = split_id(cell500)
    return ((cx // factor) * ENC + (cy // factor)).astype("int32")


def cell_centre(cell, size: int = 500):
    cx, cy = split_id(cell)
    return to_lonlat((cx + 0.5) * size, (cy + 0.5) * size)
