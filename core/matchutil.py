"""Shared matching helpers: tolerance and window flags."""
from __future__ import annotations

import pandas as pd


def tolerance_halalas(value_h: int, engine: dict) -> int:
    """Per-document tolerance: max(abs_halalas, rel_fraction * value) (spec 3.2)."""
    tol = engine["tolerance"]
    return max(tol["abs_halalas"], int(round(abs(value_h) * tol["rel_fraction"])))


def within_tolerance(a_h: int, b_h: int, engine: dict) -> bool:
    ref = max(abs(a_h), abs(b_h))
    return abs(a_h - b_h) <= tolerance_halalas(ref, engine)


def in_window(date, frm: pd.Timestamp, to: pd.Timestamp) -> bool:
    if pd.isna(date):
        return False
    return frm <= date <= to
