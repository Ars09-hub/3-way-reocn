"""Tier 1 - cross-family normalised join (spec §6, §9).

Auto-accept. The single most productive real-world link: e-invoice
official_doc_id against AR billing_doc_id, where the client never told you
which column is which. The engine indexes all four normalised families and
joins on any pairing. Only fires where Tier 0 (same-family) did not.
"""
from __future__ import annotations

from itertools import combinations

from .. import planes
from . import scoring
from .common import make_link, plane_values

_NO_AMBIG = {"alternatives_count": 1, "alternatives_top3": [], "is_ambiguous": False,
             "alternatives_capped": False, "degeneracy_reason": None}


def generate(cfg, docs: list[dict], consumed_pairs: set) -> list[dict]:
    links = []
    by_plane = {}
    for d in docs:
        by_plane.setdefault(d["plane"], []).append(d)

    for pa, pb in combinations(sorted(by_plane), 2):
        for a in by_plane[pa]:
            for b in by_plane[pb]:
                if frozenset((a["row_id"], b["row_id"])) in consumed_pairs:
                    continue
                fams = _shared_cross_family(a, b)
                if not fams:
                    continue
                sc = scoring.score_match(cfg, [a], [b], _is_b2c(a, b))
                if sc.rejected:
                    continue
                pv = plane_values([a], pa, [b], pb)
                ps = planes.plane_status(cfg, pv, 1)
                links.append(make_link((pa, pb), [a], [b], "T1", 1.0, "HIGH",
                                       ps, _NO_AMBIG, "exact",
                                       [f"T1:cross_family:{fams[0]}~{fams[1]}"], confidence=1.0))
    return links


def _shared_cross_family(a, b):
    na, nb = a.get("norm_numbers", {}), b.get("norm_numbers", {})
    for fa, va in na.items():
        for fb, vb in nb.items():
            if fa == fb:
                continue
            if va == vb:
                return (fa, fb)
    return None


def _is_b2c(a, b):
    return a.get("segment") == "B2C" or b.get("segment") == "B2C"
