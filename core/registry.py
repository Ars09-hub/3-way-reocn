"""Drill-through registry (addendum section 5).

Precomputes, for each clickable figure, the exact document keys behind it so the
browser never re-derives filter logic. Each entry:

    {label, origin, grain, glKeys, arKeys, eiKeys, count}

count is the figure as shown on the origin page (at its stated grain); the key
lists are what the Document detail page filters to. Built server-side only.
"""
from __future__ import annotations

import pandas as pd


def _keys_from_events(events: pd.DataFrame):
    gl, ar, ei = set(), set(), set()
    for _, e in events.iterrows():
        gl |= set(e.get("gl_keys") or [])
        ar |= set(e.get("ar_keys") or [])
        ei |= set(e.get("ei_keys") or [])
    return sorted(gl), sorted(ar), sorted(str(x) for x in ei)


def _entry(label, origin, grain, gl, ar, ei, count):
    return {"label": label, "origin": origin, "grain": grain,
            "glKeys": gl, "arKeys": ar, "eiKeys": [str(x) for x in ei], "count": int(count)}


def build_registry(R: dict) -> dict:
    """Step 3 scope: only the Executive summary 'Not e-invoiced' figure.

    The remaining registry entries (addendum section 5) are added in step 4.
    """
    reg = {}
    tw = R["threeway"]["events"]

    ne = tw[tw["status"] == "Not e-invoiced"]
    gl, ar, ei = _keys_from_events(ne)
    reg["exec.not_einvoiced"] = _entry(
        "Not e-invoiced", "Executive summary", "vouchers", gl, ar, ei, len(ne))

    return reg
