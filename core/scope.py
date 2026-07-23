"""Period window and account exclusions (spec 1.6, 2.3, 2.4).

The reconciled window is the intersection of the three per-file date ranges.
Everything outside it is reported separately and excluded from exposure figures.
"""
from __future__ import annotations

import pandas as pd

from core import normalize as nz


def build_account_index(account_scope: dict) -> dict:
    """Map every configured code/prefix to (class, excluded_reason)."""
    excluded = {e["gl_code"]: e for e in account_scope["excluded_accounts"]}
    return {"excluded": excluded, "classification": account_scope["classification"]}


def classify_account(code: str, account_scope: dict) -> str:
    code = nz.clean_gl_code(code)
    cls = account_scope["classification"]
    for name, rule in cls.items():
        if code in rule.get("codes", []):
            return name
    for name, rule in cls.items():
        for pfx in rule.get("prefixes", []):
            if code.startswith(pfx):
                return name
    return "UNCLASSIFIED"


def excluded_reason(code: str, excluded_index: dict) -> str | None:
    code = nz.clean_gl_code(code)
    e = excluded_index.get(code)
    return e["reason"] if e else None


def _range(series: pd.Series) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    s = series.dropna()
    if s.empty:
        return None, None
    return s.min(), s.max()


def detect_period(gl: pd.DataFrame, ar: pd.DataFrame, ei: pd.DataFrame, engine: dict,
                  ei_in_scope: pd.Series | None = None) -> dict:
    """Intersection of the three date ranges. Returns detail for the data quality page.

    ei_in_scope optionally restricts the e-invoice range to non-quarantined rows.
    """
    erp_field = engine["period"]["erp_date_field"] + "_d"
    ei_field = engine["period"]["einvoice_date_field"].replace("document_issue_date", "issue_date") + "_d"

    ei_dates = ei[ei_field]
    if ei_in_scope is not None:
        ei_dates = ei_dates[ei_in_scope]

    ranges = {
        "gl": _range(gl[erp_field]),
        "ar": _range(ar[erp_field]),
        "einvoice": _range(ei_dates),
    }
    mins = [r[0] for r in ranges.values() if r[0] is not None]
    maxs = [r[1] for r in ranges.values() if r[1] is not None]
    frm = max(mins)
    to = min(maxs)
    return {
        "from": frm,
        "to": to,
        "ranges": ranges,
        "erp_field": engine["period"]["erp_date_field"],
        "einvoice_field": engine["period"]["einvoice_date_field"],
    }


def in_window(date: pd.Timestamp, frm: pd.Timestamp, to: pd.Timestamp) -> bool:
    if pd.isna(date):
        return False
    return frm <= date <= to
