"""Shared constants, paths, chart style and panel loader for the analysis scripts."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2702
RAW = Path("data/raw")
STATIC = Path("data/static")
INTERIM = Path("data/interim")
TABLES = Path("outputs/tables")
FIGS = Path("outputs/figures")

FINE_START = pd.Timestamp("2024-10-01")
FIT = (pd.Timestamp("2022-04-01"), pd.Timestamp("2025-03-31 23:59:59"))
CALIB = (pd.Timestamp("2025-04-01"), pd.Timestamp("2025-09-30 23:59:59"))
TEST = (pd.Timestamp("2025-10-01"), pd.Timestamp("2026-09-30 23:59:59"))
YEARS = range(2021, 2027)

RAIN_BANDS = ["dry", "light", "moderate", "heavy"]          # 0, (0, 2.5], (2.5, 10], > 10 mm/h
BASELINE_MIN = 4                                            # low / zero only where baseline >= 4
LOW_D = 0.5

# URA Central Area planning areas
CENTRAL_AREA = {"DOWNTOWN CORE", "MUSEUM", "NEWTON", "ORCHARD", "OUTRAM", "RIVER VALLEY", "ROCHOR",
                "SINGAPORE RIVER", "STRAITS VIEW", "MARINA EAST", "MARINA SOUTH"}

# palette (validated reference palette, light mode); poster-style blues for sequential use
BLUE, BLUE_DARK, BLUE_LIGHT = "#2a78d6", "#1a4f91", "#a9c9ef"
ORANGE, AQUA, VIOLET, RED = "#eb6834", "#1baf7a", "#6250d6", "#e34948"
INK, MUTED, GRID, NOT_ANALYSED = "#0b0b0b", "#52514e", "#e5e5e2", "#d9d8d4"
BAND_COLORS = {"dry": "#b8b7b2", "light": "#a9c9ef", "moderate": "#2a78d6", "heavy": "#0d2f5c"}
SOURCE_TAXI_RAIN = "Sources: data.gov.sg taxi availability (LTA), NEA rainfall."


def rain_band(mmh) -> np.ndarray:
    """0 dry, 1 light, 2 moderate, 3 heavy; -1 where rain is missing."""
    mmh = np.asarray(mmh, dtype="float64")
    out = np.select([mmh == 0, mmh <= 2.5, mmh <= 10, mmh > 10], [0, 1, 2, 3], -1)
    return out.astype("int8")


def style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 9, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.titlesize": 10.5, "axes.titlelocation": "left", "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                         "legend.frameon": False, "figure.dpi": 150, "savefig.dpi": 150})


def save(fig, name: str, source: str = SOURCE_TAXI_RAIN):
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.text(0.01, 0.005, source, fontsize=7, color=MUTED, va="bottom")
    for ext in ("png", "svg"):
        fig.savefig(FIGS / f"{name}.{ext}", bbox_inches="tight")


def load_panel(years=YEARS, grid: int = 30, columns=None, filters=None) -> pd.DataFrame:
    """Read the per-year panel Parquet files (data/interim/panel{grid}_{year}.parquet)."""
    parts = []
    for y in years:
        f = INTERIM / f"panel{grid}_{y}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f, columns=columns, filters=filters))
    return pd.concat(parts, ignore_index=True)


def cells() -> pd.DataFrame:
    return pd.read_parquet(INTERIM / "cells.parquet")
