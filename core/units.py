"""Three-way unit assembly (spec §15).

A recon unit is the atomic output object. Accepted links are merged (via the
assignment union-find) into connected components spanning up to three planes;
unmatched documents become singleton units. Each unit carries its existence
cell, plane diagnosis, integrity, confidence, ambiguity, evidence and the rules
that produced it - auditor-defensible or it does not ship.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from . import existence, planes as planes_mod, buckets
from .config import LoadedConfig
from .matcher.common import TIER_RANK

_SEV_RANK = {"SUPPRESSED": 0, "INFO": 1, "REVIEW": 2, "HIGH": 3, "CRITICAL": 4}


def _period(dstr):
    return (dstr or "")[:7]


def assemble(cfg: LoadedConfig, docs: list[dict], assign_result: dict,
             integrity: dict, gl_lines_by_doc: dict) -> list[dict]:
    doc_by_id = {d["row_id"]: d for d in docs}
    uf = assign_result["uf"]
    accepted = assign_result["accepted"]

    # group accepted links into components
    comp_links = defaultdict(list)
    comp_members = defaultdict(set)
    for link in accepted:
        root = uf.find(link["all_ids"][0])
        comp_links[root].append(link)
        comp_members[root].update(link["all_ids"])

    assigned_ids = set()
    for ids in comp_members.values():
        assigned_ids.update(ids)

    units = []
    for root, member_ids in comp_members.items():
        members = [doc_by_id[i] for i in sorted(member_ids)]
        units.append(_build_unit(cfg, members, comp_links[root], integrity, gl_lines_by_doc))

    # singletons - never silently dropped
    for d in docs:
        if d["row_id"] in assigned_ids:
            continue
        units.append(_build_unit(cfg, [d], [], integrity, gl_lines_by_doc))

    return units


def _build_unit(cfg, members, links, integrity, gl_lines_by_doc) -> dict:
    gl = [d for d in members if d["plane"] == "GL"]
    ar = [d for d in members if d["plane"] == "AR"]
    einv = [d for d in members if d["plane"] == "EINV"]

    gl_rev_rows = [d["row_id"] for d in gl if d["has_revenue"]]
    gl_cust_rows = [d["row_id"] for d in gl if d["has_customer"]]
    ar_rows = [d["row_id"] for d in ar]
    einv_rows = [d["row_id"] for d in einv]

    has_R = any(d["has_revenue"] for d in gl)
    has_C = any(d["has_customer"] for d in gl) or bool(ar)
    has_E = bool(einv)

    settlement = "UNKNOWN"
    if any(d.get("settlement_type") == "CASH" for d in gl):
        settlement = "CASH"
    elif has_C:
        settlement = "CREDIT"

    cell_info = existence.classify_cell(has_R, has_C, has_E, settlement)

    # plane aggregate sums (signed minor)
    def psum(side, plane):
        return sum(d["sign"] * d[f"{plane}_minor"] for d in side)

    values = {}
    for plane in ("gross", "net", "tax"):
        v = {}
        if gl:
            v["gl"] = psum(gl, plane)
        if ar:
            v["ar"] = psum(ar, plane)
        if einv:
            v["einv"] = psum(einv, plane)
        values[plane] = v

    cardinality_n = max(len(members), 1)
    plane_status = planes_mod.plane_status(cfg, values, cardinality_n)

    # integrity across GL docs in the unit
    residual = 0
    integ_status = "OK"
    rate_flag = None
    explained_by = []
    for d in gl:
        key = (d["entity_id"], d["fiscal_year"], d["accounting_doc_id"])
        rec = integrity.get(key)
        if rec:
            residual += rec["residual_minor"]
            if rec["status"] == "UNEXPLAINED":
                integ_status = "UNEXPLAINED"
            if rec.get("rate_flag"):
                rate_flag = rec["rate_flag"]
            explained_by.append({"accounting_doc_id": d["accounting_doc_id"],
                                 "residual_minor": rec["residual_minor"],
                                 "status": rec["status"]})

    # diagnosis flags
    sign_inverted = bool(gl and einv and (max(d["sign"] for d in gl) != max(d["sign"] for d in einv)))
    cutoff = False
    for d in gl:
        for e in einv:
            if _period(d["posting_date"]) and _period(e["doc_date"]) and \
               _period(d["posting_date"]) != _period(e["doc_date"]):
                cutoff = True
    tins_gl = {d.get("counterparty_tin") for d in gl + ar if d.get("counterparty_tin")}
    tins_e = {d.get("counterparty_tin") for d in einv if d.get("counterparty_tin")}
    tin_mismatch = bool(tins_gl and tins_e and tins_gl.isdisjoint(tins_e))

    diagnosis = "SINGLE_PLANE"
    if cell_info["existence_cell"] == "E1" or (has_R and has_E):
        diagnosis = planes_mod.diagnose(plane_status, integ_status == "OK",
                                        sign_inverted, cutoff, tin_mismatch,
                                        rate_flag == "IMPLIED_RATE_DEVIATION")

    # tier / status / confidence
    if not links:
        tier = "T6" if len(members) == 1 and False else "UNMATCHED"
        match_tier = "UNMATCHED"
        match_status = "UNMATCHED"
        confidence = 0.0
        band = "LOW"
        is_ambiguous = False
        alternatives_count = 0
        search_mode = "exact"
    else:
        max_tier = max(links, key=lambda l: TIER_RANK[l["tier"]])["tier"]
        match_tier = max_tier
        is_ambiguous = any(l.get("is_ambiguous") for l in links)
        alternatives_count = max((l.get("alternatives_count", 1) for l in links), default=1)
        search_mode = "heuristic" if any(l["search_mode"] == "heuristic" for l in links) else "exact"
        det = all(TIER_RANK[l["tier"]] <= 2 for l in links)
        confidence = min(l["confidence"] for l in links)
        if det:
            match_status = "MATCHED"
            confidence = 1.0
        elif is_ambiguous:
            match_status = "AMBIGUOUS"
        else:
            match_status = "SUGGESTED"
        band = "HIGH" if confidence >= cfg.engine["confidence_bands"]["high"] else \
               ("MEDIUM" if confidence >= cfg.engine["confidence_bands"]["medium"] else "LOW")
        if is_ambiguous and band == "HIGH":
            band = "MEDIUM"

    # bucket + severity (existence first, integrity overlay)
    bucket = cell_info["bucket"]
    severity = cell_info["severity"]
    ib = buckets.integrity_bucket(integ_status, rate_flag)
    rules_fired = sorted({r for l in links for r in l["rules_fired"]})
    if ib and severity != "SUPPRESSED":
        # keep existence bucket but escalate severity and record integrity issue
        if _SEV_RANK[ib[1]] > _SEV_RANK[severity]:
            severity = ib[1]
        rules_fired.append(f"INTEGRITY:{ib[0]}")

    cardinality = f"{len(einv)}:{len(ar)}:{len(gl)}"

    unit_id = hashlib.sha256("|".join(sorted(d["row_id"] for d in members)).encode()).hexdigest()[:16]

    entity = members[0]["entity_id"]
    period = members[0].get("period") or _period(members[0].get("doc_date"))

    return {
        "unit_id": unit_id,
        "gl_rev_tax_rows": gl_rev_rows,
        "gl_customer_rows": gl_cust_rows,
        "ar_rows": ar_rows,
        "einv_rows": einv_rows,
        "member_ids": sorted(d["row_id"] for d in members),
        "cardinality": cardinality,
        "existence_cell": cell_info["existence_cell"],
        "bucket": bucket,
        "severity": severity,
        "disposition": cell_info["disposition"],
        "match_tier": match_tier,
        "match_status": match_status,
        "confidence": round(confidence, 4),
        "confidence_band": band,
        "search_mode": search_mode,
        "is_ambiguous": is_ambiguous,
        "alternatives_count": alternatives_count,
        "alternatives_top3": _first_alts(links),
        "degeneracy_reason": next((l.get("degeneracy_reason") for l in links
                                   if l.get("degeneracy_reason")), None),
        "planes": plane_status,
        "integrity": {"residual_minor": residual, "explained_by": explained_by,
                      "status": integ_status},
        "diagnosis": diagnosis,
        "value_at_risk_minor": _value_at_risk(values),
        "evidence": {"values": values, "settlement_type": settlement,
                     "counterparty_tins": sorted(tins_gl | tins_e)},
        "rules_fired": rules_fired,
        "period": period,
        "entity_id": entity,
    }


def _first_alts(links):
    for l in links:
        if l.get("alternatives_top3"):
            return l["alternatives_top3"]
    return []


def _value_at_risk(values):
    tax = values.get("tax", {})
    present = [abs(v) for v in tax.values() if v is not None]
    if len(present) <= 1:
        return present[0] if present else 0
    return max(present) - min(present) if (max(present) != min(present)) else max(present)


def conservation_check(cfg, docs, units) -> dict:
    """Every document in at most one unit; total value per plane preserved."""
    seen = defaultdict(int)
    for u in units:
        for rid in u["member_ids"]:
            seen[rid] += 1
    duplicates = {rid: c for rid, c in seen.items() if c > 1}
    missing = [d["row_id"] for d in docs if d["row_id"] not in seen]

    plane_in = defaultdict(int)
    plane_out = defaultdict(int)
    for d in docs:
        plane_in[d["plane"]] += d["tax_minor"]
    doc_by_id = {d["row_id"]: d for d in docs}
    for u in units:
        for rid in u["member_ids"]:
            d = doc_by_id[rid]
            plane_out[d["plane"]] += d["tax_minor"]

    ok = (not duplicates) and (not missing) and (plane_in == plane_out)
    return {"ok": ok, "duplicates": duplicates, "missing": missing,
            "plane_value_in": dict(plane_in), "plane_value_out": dict(plane_out)}
