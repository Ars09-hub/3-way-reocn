"""Tier 5 - N:M cluster balancing (spec §11.5).

Only after T4 residue remains on both sides within a block. Build a bipartite
graph (edge where a pairwise amount ratio is plausible), extract connected
components, and where Σ side_A ≈ Σ side_B within tolerance propose the whole
component as one balanced N:M unit. Never decompose a component into
sub-pairings. Capped at Medium confidence, never auto-accepted.
"""
from __future__ import annotations

from itertools import combinations

from .. import planes
from . import scoring, ambiguity
from .common import make_link, plane_values


def _tol(cfg, k, target):
    return max(cfg.rounding_abs_minor_per_doc * max(k, 1),
               int(round(cfg.relative_tol * abs(target))))


def generate_block(cfg, block_docs: list[dict], is_b2c: bool, used: set) -> list[dict]:
    by_plane = {}
    for d in block_docs:
        if d["row_id"] in used:
            continue
        by_plane.setdefault(d["plane"], []).append(d)

    links = []
    for pa, pb in combinations(sorted(by_plane), 2):
        A = by_plane.get(pa, [])
        B = by_plane.get(pb, [])
        if len(A) < 2 or len(B) < 2:
            continue

        # bipartite edges where ratio is plausible (0.1 .. 10)
        adj = {d["row_id"]: set() for d in A + B}
        index = {d["row_id"]: d for d in A + B}
        for a in A:
            for b in B:
                ta, tb = a["tax_minor"], b["tax_minor"]
                if ta == 0 or tb == 0:
                    continue
                ratio = ta / tb
                if 0.1 <= ratio <= 10:
                    adj[a["row_id"]].add(b["row_id"])
                    adj[b["row_id"]].add(a["row_id"])

        for comp in _components(adj):
            side_a = [index[i] for i in comp if index[i]["plane"] == pa]
            side_b = [index[i] for i in comp if index[i]["plane"] == pb]
            if len(side_a) < 1 or len(side_b) < 1:
                continue
            if len(side_a) + len(side_b) < 3:
                continue  # 1:1 belongs to T3
            sum_a = sum(d["tax_minor"] for d in side_a)
            sum_b = sum(d["tax_minor"] for d in side_b)
            if abs(sum_a - sum_b) > _tol(cfg, len(comp), max(sum_a, sum_b)):
                continue
            sc = scoring.score_match(cfg, side_a, side_b, is_b2c)
            if sc.rejected:
                continue
            band = scoring.band_for(cfg, sc.score)
            conf = sc.score
            if band == "HIGH":
                band, conf = "MEDIUM", min(conf, cfg.engine["confidence_bands"]["high"] - 1e-6)
            amb = {"alternatives_count": 1, "alternatives_top3": [], "is_ambiguous": True,
                   "alternatives_capped": False, "degeneracy_reason": "MULTIPLE_VALID_PARTITIONS"}
            pv = plane_values(side_a, pa, side_b, pb)
            ps = planes.plane_status(cfg, pv, len(comp))
            links.append(make_link((pa, pb), side_a, side_b, "T5", sc.score, band,
                                   ps, amb, "exact", ["T5:nm_cluster"], confidence=conf))
    return links


def _components(adj):
    seen = set()
    comps = []
    for node in adj:
        if node in seen:
            continue
        stack = [node]
        comp = []
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.append(n)
            stack.extend(adj[n] - seen)
        comps.append(sorted(comp))
    return comps
