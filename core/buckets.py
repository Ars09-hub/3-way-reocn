"""Bucket + severity assignment and the E5 self-correction loop (spec §8).

Existence cells set the base bucket/severity. This module adds integrity
buckets and produces the suggested-account-class-additions output: GL accounts
that recur in E5 (receivable + reported, no recognised revenue) are proposed as
profile amendments, turning an exception list into a configuration improvement.
"""
from __future__ import annotations

from collections import defaultdict


def integrity_bucket(integrity_status: str, rate_flag: str | None) -> tuple[str, str] | None:
    if integrity_status == "UNEXPLAINED":
        return ("UNEXPLAINED_RESIDUAL", "HIGH")
    if rate_flag == "IMPLIED_RATE_DEVIATION":
        return ("IMPLIED_RATE_DEVIATION", "REVIEW")
    return None


def suggested_account_additions(units: list[dict], gl_docs_by_id: dict) -> list[dict]:
    """Rank GL accounts appearing repeatedly in E5 units by frequency and value."""
    acc = defaultdict(lambda: {"count": 0, "value_minor": 0, "sample_docs": []})
    for u in units:
        if u.get("existence_cell") != "E5":
            continue
        for rid in u.get("gl_rev_tax_rows", []) + u.get("gl_customer_rows", []):
            doc = gl_docs_by_id.get(rid)
            if not doc:
                continue
            for line in doc.get("_lines", []):
                if line["account_class"] == "OTHER" and line["account_class"] != "TAX_OUTPUT":
                    a = acc[line["gl_account"]]
                    a["count"] += 1
                    a["value_minor"] += abs(line["amount_minor"])
                    if len(a["sample_docs"]) < 5:
                        a["sample_docs"].append(doc["accounting_doc_id"])
    rows = [{"gl_account": k, **v, "sample_docs": ";".join(v["sample_docs"])}
            for k, v in acc.items()]
    rows.sort(key=lambda r: (-r["count"], -r["value_minor"], r["gl_account"]))
    return rows
