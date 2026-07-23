"""Ambiguity and degeneracy (spec §13).

The most important correctness property in the build. After finding the
best-scoring group, enumerate alternatives scoring within alternative_epsilon
of the best (capped). If more than one equivalent combination exists the unit
is ambiguous, must never auto-accept, and its confidence is capped at Medium.
"""
from __future__ import annotations


def analyze(scored_alternatives: list[dict], cfg) -> dict:
    """scored_alternatives: list of {'ids':[...], 'score':float, 'deltas':{...},
    'anchor_amount':int, 'is_round':bool}, best first. Returns ambiguity fields."""
    m = cfg.engine["matching"]
    eps = m["alternative_epsilon"]
    cap = m["enumerate_alternatives_cap"]

    if not scored_alternatives:
        return {"alternatives_count": 0, "alternatives_top3": [], "is_ambiguous": False,
                "alternatives_capped": False, "degeneracy_reason": None}

    best = scored_alternatives[0]["score"]
    within = [a for a in scored_alternatives if best - a["score"] <= eps]
    count = len(within)
    capped = count >= cap

    reason = None
    if count > 1:
        # identical amounts -> IDENTICAL_AMOUNTS; round numbers -> collision
        sums = {a.get("subset_tax") for a in within}
        if scored_alternatives[0].get("is_round"):
            reason = "ROUND_NUMBER_COLLISION"
        elif len(sums) == 1:
            reason = "IDENTICAL_AMOUNTS"
        else:
            reason = "MULTIPLE_VALID_PARTITIONS"

    return {
        "alternatives_count": count,
        "alternatives_top3": [
            {"member_ids": a["ids"], "score": round(a["score"], 4), "deltas": a.get("deltas")}
            for a in within[:3]
        ],
        "is_ambiguous": count > 1,
        "alternatives_capped": capped,
        "degeneracy_reason": reason,
    }


def is_round_number(target: int) -> bool:
    """Round-number heuristic: amount ends in many zeros in minor units."""
    if target == 0:
        return False
    s = str(abs(target))
    return s.endswith("0000") or (len(s) >= 4 and s.endswith("000"))
