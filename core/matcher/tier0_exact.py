"""Tier 0 - exact join on identical normalised doc number, same family.

Auto-accept. The strongest deterministic link: two documents carry the same
normalised value in the same number family (e.g. both official_doc_id).
"""
from __future__ import annotations

from itertools import combinations

from .. import planes
from . import scoring
from .common import make_link, plane_values

_NO_AMBIG = {"alternatives_count": 1, "alternatives_top3": [], "is_ambiguous": False,
             "alternatives_capped": False, "degeneracy_reason": None}


def generate(cfg, docs: list[dict]) -> list[dict]:
    links = []
    by_plane = _group_by_plane(docs)
    for pa, pb in combinations(sorted(by_plane), 2):
        for a in by_plane[pa]:
            for b in by_plane[pb]:
                fam = _shared_family_same(a, b)
                if not fam:
                    continue
                sc = scoring.score_match(cfg, [a], [b], _is_b2c(a, b))
                if sc.rejected:
                    continue
                pv = plane_values([a], pa, [b], pb)
                ps = planes.plane_status(cfg, pv, 1)
                links.append(make_link((pa, pb), [a], [b], "T0", 1.0, "HIGH",
                                       ps, _NO_AMBIG, "exact",
                                       [f"T0:same_family:{fam}"], confidence=1.0))
    return links


def _shared_family_same(a, b):
    na, nb = a.get("norm_numbers", {}), b.get("norm_numbers", {})
    for fam, val in na.items():
        if nb.get(fam) and nb[fam] == val:
            return fam
    return None


def _group_by_plane(docs):
    out = {}
    for d in docs:
        out.setdefault(d["plane"], []).append(d)
    return out


def _is_b2c(a, b):
    return a.get("segment") == "B2C" or b.get("segment") == "B2C"
