"""Pipeline orchestration - wires the deterministic stages together (spec §22).

Order: ingest/normalise/quarantine -> Leg A integrity -> derive tax-point and
consolidation keys -> matching ladder T0..T5 -> global assignment -> three-way
unit assembly -> conservation check. No LLM anywhere in this path.
"""
from __future__ import annotations

from collections import defaultdict

from . import ingest as ingest_mod, leg_a_integrity, units as units_mod
from .config import LoadedConfig
from .matcher import (blocking, tier0_exact, tier1_normalized, tier2_composite,
                      tier3_pairwise, tier4_pairs, tier5_cluster, assignment)


def is_b2c_dataset(cfg: LoadedConfig) -> bool:
    cp = cfg.client.get("consolidation_profile", {})
    return (cp.get("expected_ratio_einv_to_gl") == "MANY_TO_ONE"
            or cp.get("b2c_gl_posting_grain", "PER_INVOICE") != "PER_INVOICE")


def _tax_point(cfg, doc):
    rule = cfg.country.get("tax_point_rule", "DOC_DATE")
    if rule == "POSTING_DATE":
        return doc.get("posting_date") or doc.get("doc_date")
    if rule == "CLEARANCE_DATE":
        return doc.get("einv_clearance_date") or doc.get("doc_date")
    # DOC_DATE and EARLIER_OF_* fall back to doc_date without payment data
    return doc.get("doc_date")


def _consolidation_key(cfg, doc):
    fields = cfg.client.get("consolidation_profile", {}).get("consolidation_key_fields", [])
    return "|".join(str(doc.get(f) or "NA") for f in fields)


def run(cfg: LoadedConfig, gl_path, ar_path, einv_path, period_filter=None) -> dict:
    ing = ingest_mod.ingest(cfg, gl_path, ar_path, einv_path)

    # Leg A integrity (pure GROUP BY over GL lines)
    integ = leg_a_integrity.run(cfg, ing.gl_lines)
    leg_a_integrity.check_implied_rate(cfg, integ)

    docs = ing.docs
    if period_filter:
        docs = [d for d in docs if d.get("period") == period_filter]

    for d in docs:
        d["tax_point_date"] = _tax_point(cfg, d)
        d["consolidation_key"] = _consolidation_key(cfg, d)

    b2c = is_b2c_dataset(cfg)

    # ---- matching ladder ------------------------------------------------
    links = []
    det_pairs = set()

    t0 = tier0_exact.generate(cfg, docs)
    links += t0
    for l in t0:
        for a in l["a_ids"]:
            for b in l["b_ids"]:
                det_pairs.add(frozenset((a, b)))

    t1 = tier1_normalized.generate(cfg, docs, det_pairs)
    links += t1
    for l in t1:
        for a in l["a_ids"]:
            for b in l["b_ids"]:
                det_pairs.add(frozenset((a, b)))

    t2 = tier2_composite.generate(cfg, docs, det_pairs)
    links += t2

    # T3/T4/T5 run within blocks at progressively looser levels
    levels = ["B3", "B4", "B2"] if b2c else ["B1", "B2"]
    seen_links = set()

    def add(new_links):
        for l in new_links:
            if l["link_id"] in seen_links:
                continue
            seen_links.add(l["link_id"])
            links.append(l)

    used = set()  # docs deterministically matched are excluded from fuzzy search
    for l in links:
        used.update(l["all_ids"])

    for level in levels:
        blocks = blocking.build_blocks(docs, b2c, level)
        for _, block_docs in blocks.items():
            if len({d["plane"] for d in block_docs}) < 2:
                continue
            add(tier3_pairwise.generate_block(cfg, block_docs, b2c, used))
            add(tier4_pairs.generate_block(cfg, block_docs, b2c, used))
            add(tier5_cluster.generate_block(cfg, block_docs, b2c, used))

    # ---- global assignment + unit assembly ------------------------------
    assign_result = assignment.assign(links)

    # attach GL lines for E5 self-correction
    gl_lines_by_doc = defaultdict(list)
    for ln in ing.gl_lines:
        gl_lines_by_doc[ln["accounting_doc_id"]].append(ln)
    gl_docs_by_id = {}
    for d in docs:
        if d["plane"] == "GL":
            d["_lines"] = gl_lines_by_doc.get(d["accounting_doc_id"], [])
            gl_docs_by_id[d["row_id"]] = d

    units = units_mod.assemble(cfg, docs, assign_result, integ, gl_lines_by_doc)
    conservation = units_mod.conservation_check(cfg, docs, units)

    return {
        "cfg": cfg,
        "ingest": ing,
        "integrity": integ,
        "docs": docs,
        "links": links,
        "assign": assign_result,
        "units": units,
        "conservation": conservation,
        "gl_docs_by_id": gl_docs_by_id,
        "b2c": b2c,
    }
