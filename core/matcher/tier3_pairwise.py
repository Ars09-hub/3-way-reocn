"""Tier 3 - 1:1 amount + date within tolerance, unique within block (spec §9).

Suggest (High). Matches on the tax plane primarily; net and gross verify and
feed the score. Uniqueness within the block drives the ambiguity flag.
"""
from __future__ import annotations

from itertools import combinations

from .. import planes
from . import scoring, ambiguity
from .common import make_link, plane_values


def _tol(cfg, target):
    return max(cfg.rounding_abs_minor_per_doc,
               int(round(cfg.relative_tol * abs(target))))


def generate_block(cfg, block_docs: list[dict], is_b2c: bool,
                   used: set) -> list[dict]:
    links = []
    by_plane = {}
    for d in block_docs:
        if d["row_id"] in used:
            continue
        by_plane.setdefault(d["plane"], []).append(d)

    for pa, pb in combinations(sorted(by_plane), 2):
        for a in by_plane[pa]:
            target = a["tax_minor"]
            cands = [b for b in by_plane[pb]
                     if abs(b["tax_minor"] - target) <= _tol(cfg, target)]
            if not cands:
                continue
            scored = []
            for b in cands:
                sc = scoring.score_match(cfg, [a], [b], is_b2c, alternatives_count=len(cands))
                if sc.rejected:
                    continue
                scored.append((b, sc))
            if not scored:
                continue
            scored.sort(key=lambda t: (-t[1].score, t[0]["row_id"]))
            best_b, best_sc = scored[0]

            alts = [{"ids": sorted([a["row_id"], b["row_id"]]), "score": sc.score,
                     "subset_tax": b["tax_minor"], "is_round": ambiguity.is_round_number(target),
                     "deltas": {"tax": b["tax_minor"] - target}} for b, sc in scored]
            amb = ambiguity.analyze(alts, cfg)

            band = scoring.band_for(cfg, best_sc.score)
            conf = best_sc.score
            if amb["is_ambiguous"] and band == "HIGH":
                band = "MEDIUM"
                conf = min(conf, cfg.engine["confidence_bands"]["high"] - 1e-6)

            pv = plane_values([a], pa, [best_b], pb)
            ps = planes.plane_status(cfg, pv, 2)
            links.append(make_link((pa, pb), [a], [best_b], "T3", best_sc.score,
                                   band, ps, amb, "exact", ["T3:pairwise_unique"],
                                   confidence=conf))
    return links
