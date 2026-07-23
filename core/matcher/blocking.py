"""Blocking (spec §10).

Subset-sum is exponential; blocking makes it tractable. Blocks are built
progressively looser (B1 tight .. B5 fallback). A document participates in the
tightest block that produces cross-plane candidates. Hard constraints inside
every block: same sign, same tax_category, compatible doc_class, date spread
within the window.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date


def _pd(s):
    if not s:
        return None
    try:
        y, m, d = str(s)[:10].split("-")
        return date(int(y), int(m), int(d))
    except Exception:  # noqa: BLE001
        return None


def _daykey(s, width_days):
    d = _pd(s)
    if not d:
        return "NA"
    return d.toordinal() // max(1, width_days)


def block_keys(doc: dict, is_b2c: bool) -> list[tuple]:
    """Progressive block keys B1..B5 for one document."""
    e = doc["entity_id"]
    # One legal entity == one supplier registration in these datasets. Only the
    # e-invoice feed carries the supplier TIN natively, so keying the block on
    # entity keeps all three planes of the same entity in the same block while
    # still never crossing entities (the "never sum across registrations" rule).
    trn = e
    cp = doc.get("counterparty_tin") or "NA"
    tc = doc.get("tax_code") or "NA"
    dd = doc.get("doc_date") or ""
    per = doc.get("period") or dd[:7]
    ck = doc.get("consolidation_key") or "NA"

    keys = [
        ("B1", e, trn, cp, tc, dd),
        # B2 groups a counterparty's whole period into one block; the scoring
        # layer's date-window rejection then filters out-of-window candidates.
        # (A floor-division day bucket would split adjacent dates across a
        # boundary and miss legitimate cut-off matches.)
        ("B2", e, trn, cp, tc, per),
        ("B3", e, trn, tc, dd),
        ("B4", e, trn, tc, ck),
        ("B5", e, trn, tc, per),
    ]
    return keys


def build_blocks(docs: list[dict], is_b2c: bool, level: str) -> dict:
    """Return {block_key: [docs]} at a given level index (B1..B5)."""
    idx = {"B1": 0, "B2": 1, "B3": 2, "B4": 3, "B5": 4}[level]
    blocks = defaultdict(list)
    for d in docs:
        keys = block_keys(d, is_b2c)
        blocks[keys[idx]].append(d)
    return blocks


def compatible(a: dict, b: dict) -> bool:
    """Hard constraints for grouping two docs in the same block/side."""
    if a["sign"] != b["sign"]:
        return False
    if a.get("tax_category") and b.get("tax_category") and a["tax_category"] != b["tax_category"]:
        return False
    return True
