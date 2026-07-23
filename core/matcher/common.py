"""Shared helpers for the matching ladder: Link construction and plane values."""
from __future__ import annotations

import hashlib


def plane_values(side_a: list[dict], plane_a: str, side_b: list[dict], plane_b: str) -> dict:
    """Build the per-plane {gl,ar,einv} signed-sum structure for a link."""
    def key(p):
        return {"GL": "gl", "AR": "ar", "EINV": "einv"}[p]

    out = {}
    for plane in ("gross", "net", "tax"):
        v = {}
        v[key(plane_a)] = sum(d["sign"] * d[f"{plane}_minor"] for d in side_a)
        v[key(plane_b)] = sum(d["sign"] * d[f"{plane}_minor"] for d in side_b)
        out[plane] = v
    return out


def make_link(pair, side_a, side_b, tier, score, band, planes_status,
              ambiguity, search_mode, rules, confidence=None) -> dict:
    a_ids = sorted(d["row_id"] for d in side_a)
    b_ids = sorted(d["row_id"] for d in side_b)
    lid = hashlib.sha256(("|".join(sorted(a_ids + b_ids)) + tier).encode()).hexdigest()[:16]
    conf = score if confidence is None else confidence
    return {
        "link_id": lid,
        "pair": pair,
        "plane_a": pair[0],
        "plane_b": pair[1],
        "a_ids": a_ids,
        "b_ids": b_ids,
        "all_ids": sorted(a_ids + b_ids),
        "tier": tier,
        "score": round(float(score), 4),
        "confidence": round(float(conf), 4),
        "confidence_band": band,
        "planes": planes_status,
        "search_mode": search_mode,
        "rules_fired": rules,
        "cardinality": len(side_a) + len(side_b),
        **ambiguity,
    }


TIER_RANK = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5, "T6": 6}
BAND_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
