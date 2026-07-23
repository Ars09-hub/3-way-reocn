"""Combination search for leg 2 (spec 3.3).

One e-invoice against several AR vouchers (or several against one). Search on VAT
amount as the primary key, then verify taxable value and gross. A group agreeing
on all three planes ranks above one agreeing on VAT alone. After the best group is
found, count equally good alternatives; more than one means "Needs review".
"""
from __future__ import annotations

import itertools

from core import matchutil


def _planes_agreement(group_vat, group_taxable, group_gross,
                      tgt_vat, tgt_taxable, tgt_gross, engine) -> int:
    score = 0
    if matchutil.within_tolerance(group_vat, tgt_vat, engine):
        score += 1
    if matchutil.within_tolerance(group_taxable, tgt_taxable, engine):
        score += 1
    if matchutil.within_tolerance(group_gross, tgt_gross, engine):
        score += 1
    return score


def search(target: dict, candidates: list[dict], engine: dict) -> dict:
    """Find the best-fit subset of candidates for one target document.

    target/candidates carry integer-halalas 'vat_h', 'taxable_h', 'gross_h', plus
    a 'sign' and 'tax_family'. Returns the best group, its plane agreement, and the
    number of equally good alternatives (for ambiguity).
    """
    max_n = engine["combination"]["max_docs_per_side"]
    tgt_vat = target["vat_h"]
    tgt_tax = target["taxable_h"]
    tgt_gross = target["gross_h"]
    tgt_sign = target["sign"]
    tgt_family = target["tax_family"]

    # constraints: same sign, same tax treatment, conflicting VAT disqualifies
    pool = [c for c in candidates
            if c["sign"] == tgt_sign and c["tax_family"] == tgt_family]

    approximate = len(pool) > engine["combination"]["exhaustive_max_block"]

    scored = []  # (agreement, n_docs, indices)
    upper = min(max_n, len(pool))
    for n in range(1, upper + 1):
        for combo in itertools.combinations(range(len(pool)), n):
            gv = sum(pool[i]["vat_h"] for i in combo)
            # VAT is the primary key: prune anything that does not agree on VAT
            if not matchutil.within_tolerance(gv, tgt_vat, engine):
                continue
            gt = sum(pool[i]["taxable_h"] for i in combo)
            gg = sum(pool[i]["gross_h"] for i in combo)
            agreement = _planes_agreement(gv, gt, gg, tgt_vat, tgt_tax, tgt_gross, engine)
            scored.append((agreement, len(combo), combo))

    if not scored:
        return {"found": False, "approximate": approximate}

    # best: highest plane agreement, then fewest documents, then stable order
    best_agreement = max(s[0] for s in scored)
    best_tier = [s for s in scored if s[0] == best_agreement]
    min_docs = min(s[1] for s in best_tier)
    equally_good = [s for s in best_tier if s[1] == min_docs]
    equally_good.sort(key=lambda s: s[2])
    best = equally_good[0]

    return {
        "found": True,
        "approximate": approximate,
        "indices": [pool[i]["ref"] for i in best[2]],
        "agreement": best_agreement,
        "n_docs": best[1],
        "n_alternatives": len(equally_good),
        "alternatives": [[pool[i]["ref"] for i in s[2]] for s in equally_good[:3]],
        "group_vat_h": sum(pool[i]["vat_h"] for i in best[2]),
        "group_taxable_h": sum(pool[i]["taxable_h"] for i in best[2]),
        "group_gross_h": sum(pool[i]["gross_h"] for i in best[2]),
    }


def confidence_word(agreement: int, n_alternatives: int) -> str:
    """Three words only, never a decimal (spec 3.3)."""
    if n_alternatives > 1:
        return "Needs review"
    if agreement == 3:
        return "Strong"
    return "Possible"
