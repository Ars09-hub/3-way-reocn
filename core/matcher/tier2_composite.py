"""Tier 2 - deterministic composite key (spec §9).

Auto-accept. Key = entity + counterparty_tin + tax_point_date + gross_minor +
tax_minor. When document numbers do not join at all, an identical composite of
who / when / how-much is still a deterministic correspondence.
"""
from __future__ import annotations

from collections import defaultdict

from .. import planes
from . import scoring
from .common import make_link, plane_values

_NO_AMBIG = {"alternatives_count": 1, "alternatives_top3": [], "is_ambiguous": False,
             "alternatives_capped": False, "degeneracy_reason": None}


def _composite(d):
    return (
        d["entity_id"],
        d.get("counterparty_tin") or "NA",
        (d.get("tax_point_date") or d.get("doc_date") or "")[:10],
        d["gross_minor"],
        d["tax_minor"],
        d["sign"],
    )


def generate(cfg, docs: list[dict], consumed_pairs: set) -> list[dict]:
    buckets = defaultdict(list)
    for d in docs:
        buckets[_composite(d)].append(d)

    links = []
    for _, group in buckets.items():
        planes_present = {d["plane"] for d in group}
        if len(planes_present) < 2:
            continue
        # pair up documents across distinct planes
        by_plane = defaultdict(list)
        for d in group:
            by_plane[d["plane"]].append(d)
        pl = sorted(by_plane)
        for i in range(len(pl)):
            for j in range(i + 1, len(pl)):
                for a in by_plane[pl[i]]:
                    for b in by_plane[pl[j]]:
                        if frozenset((a["row_id"], b["row_id"])) in consumed_pairs:
                            continue
                        sc = scoring.score_match(cfg, [a], [b],
                                                 a.get("segment") == "B2C" or b.get("segment") == "B2C")
                        if sc.rejected:
                            continue
                        pv = plane_values([a], pl[i], [b], pl[j])
                        ps = planes.plane_status(cfg, pv, 1)
                        links.append(make_link((pl[i], pl[j]), [a], [b], "T2", 1.0,
                                               "HIGH", ps, _NO_AMBIG, "exact",
                                               ["T2:composite_key"], confidence=1.0))
    return links
