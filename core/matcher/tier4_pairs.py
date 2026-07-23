"""Tier 4 orchestration - 1:N / N:1 subset-sum within a block (spec §11).

Runs both directions and takes the union (spec §11.4):
  - E-anchored: one e-invoice, find the AR/GL subset (B2B split billing)
  - GL/AR-anchored: one accounting doc, find the e-invoice subset (B2C
    consolidated posting - one daily summary against many e-invoices)

Uses the meet-in-the-middle exact search for small blocks and the heuristic
search for large ones (confidence then capped at Medium).
"""
from __future__ import annotations

from itertools import combinations

from .. import planes
from . import scoring, ambiguity, tier4_subsetsum as ss
from .common import make_link, plane_values


def generate_block(cfg, block_docs: list[dict], is_b2c: bool, used: set) -> list[dict]:
    m = cfg.engine["matching"]
    max_card = m["max_group_cardinality"]
    cap = m["enumerate_alternatives_cap"]
    exact_cap = m["max_block_size_for_exact_search"]

    by_plane = {}
    for d in block_docs:
        if d["row_id"] in used:
            continue
        by_plane.setdefault(d["plane"], []).append(d)

    links = []
    for pa, pb in combinations(sorted(by_plane), 2):
        # anchor on each side, search subsets on the other
        for anchor_plane, cand_plane in ((pa, pb), (pb, pa)):
            anchors = by_plane.get(anchor_plane, [])
            cands = by_plane.get(cand_plane, [])
            if len(cands) < 2:
                continue  # 1:1 handled by T3
            heuristic = len(cands) > exact_cap
            for anchor in anchors:
                target = anchor["tax_minor"]
                if target == 0:
                    continue
                if heuristic:
                    subset = ss.heuristic_search(cands, target, cfg, max_card)
                    subsets = [subset] if subset else []
                    search_mode = "heuristic"
                else:
                    subsets = ss.enumerate_subsets_exact(cands, target, cfg, max_card, cap)
                    search_mode = "exact"
                subsets = [s for s in subsets if s and len(s) >= 2]
                if not subsets:
                    continue

                scored = []
                for sub in subsets:
                    sc = scoring.score_match(cfg, [anchor], sub, is_b2c,
                                             alternatives_count=len(subsets))
                    if sc.rejected:
                        continue
                    subtax = sum(d["tax_minor"] for d in sub)
                    scored.append({
                        "sub": sub, "sc": sc,
                        "ids": sorted([anchor["row_id"]] + [d["row_id"] for d in sub]),
                        "score": sc.score, "subset_tax": subtax,
                        "is_round": ambiguity.is_round_number(target),
                        "deltas": {"tax": subtax - target},
                    })
                if not scored:
                    continue
                scored.sort(key=lambda x: (-x["score"], len(x["sub"]), x["ids"]))
                best = scored[0]
                amb = ambiguity.analyze(scored, cfg)

                band = scoring.band_for(cfg, best["score"])
                conf = best["score"]
                if search_mode == "heuristic" and band == "HIGH":
                    band, conf = "MEDIUM", min(conf, cfg.engine["confidence_bands"]["high"] - 1e-6)
                if amb["is_ambiguous"] and band == "HIGH":
                    band, conf = "MEDIUM", min(conf, cfg.engine["confidence_bands"]["high"] - 1e-6)

                pv = plane_values([anchor], anchor_plane, best["sub"], cand_plane)
                ps = planes.plane_status(cfg, pv, 1 + len(best["sub"]))
                links.append(make_link((anchor_plane, cand_plane), [anchor], best["sub"],
                                       "T4", best["score"], band, ps, amb,
                                       search_mode,
                                       [f"T4:subsetsum:{search_mode}"], confidence=conf))
    return links
