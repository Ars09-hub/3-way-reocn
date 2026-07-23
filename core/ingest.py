"""Ingest: raw ERP extracts -> canonical documents.

This is the only ERP-aware layer. It uses the client profile's field_mapping
to translate native columns into the canonical model, classifies each row, and
aggregates GL lines into GL documents. Rows that fail normalisation are
quarantined with a reason and counted, never silently dropped (spec §4, §21).
"""
from __future__ import annotations

import csv
import hashlib
from collections import defaultdict

from .config import LoadedConfig
from . import classify, normalize


def _hash_id(*parts) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _map_row(raw: dict, mapping: dict) -> dict:
    """Translate a native raw row into canonical field names."""
    out = {}
    for canon, native in mapping.items():
        out[canon] = raw.get(native)
    return out


def _period(dstr: str | None) -> str:
    if not dstr:
        return ""
    return str(dstr)[:7]


class IngestResult:
    def __init__(self):
        self.gl_lines: list[dict] = []
        self.docs: list[dict] = []          # unified doc-level: GL/AR/EINV
        self.quarantine: list[dict] = []
        self.stats: dict = {}
        self.awkey_coverage: float = 0.0


def ingest(cfg: LoadedConfig, gl_path: str, ar_path: str, einv_path: str) -> IngestResult:
    res = IngestResult()
    minor_exp = cfg.minor_exp
    norm_ops = cfg.client.get("doc_number_normalization", [])
    fm = cfg.client["field_mapping"]

    raw_counts = {}

    # ---- GL lines -------------------------------------------------------
    gl_raw = _read_csv(gl_path)
    raw_counts["gl"] = len(gl_raw)
    for i, raw in enumerate(gl_raw):
        m = _map_row(raw, fm["gl"])
        try:
            gl_account = (m.get("gl_account") or "").strip()
            acct_class = cfg.account_class_for(gl_account)
            dtn = (m.get("doc_type_native") or "").strip()
            dc = classify.doc_class_for(cfg, dtn)
            amt = normalize.to_minor(m.get("amount_signed"), minor_exp)
            line = {
                "source": "GL",
                "row_id": _hash_id("GL", m.get("entity_id"), m.get("fiscal_year"),
                                   m.get("accounting_doc_id"), m.get("line_no"), i),
                "source_row_ref": f"{gl_path}:{i+2}",
                "entity_id": (m.get("entity_id") or "").strip(),
                "accounting_doc_id": (m.get("accounting_doc_id") or "").strip(),
                "fiscal_year": (m.get("fiscal_year") or "").strip(),
                "line_no": m.get("line_no"),
                "gl_account": gl_account,
                "account_class": acct_class,
                "doc_type_native": dtn,
                "doc_class": dc["doc_class"],
                "is_reversal": dc["is_reversal"],
                "doc_date": (m.get("doc_date") or "").strip(),
                "posting_date": (m.get("posting_date") or "").strip(),
                "currency": (m.get("currency") or cfg.country.get("currency")).strip(),
                "amount_minor": amt,
                "tax_code": (m.get("tax_code") or "").strip() or None,
                "counterparty_id": (m.get("counterparty_id") or "").strip() or None,
                "counterparty_tin": (m.get("counterparty_tin") or "").strip() or None,
                "counterparty_name": (m.get("counterparty_name") or "").strip() or None,
                "profit_center": (m.get("profit_center") or "").strip() or None,
                "einv_relevant": dc["einv_relevant"],
                "settlement_hint": dc.get("settlement_type"),
            }
            res.gl_lines.append(line)
        except Exception as exc:  # noqa: BLE001 - quarantine, never drop
            res.quarantine.append({"source": "GL", "row_ref": f"{gl_path}:{i+2}",
                                   "reason": f"parse_error: {exc}"})

    res.docs.extend(_aggregate_gl_docs(cfg, res.gl_lines, norm_ops))

    # ---- AR docs --------------------------------------------------------
    ar_raw = _read_csv(ar_path)
    raw_counts["ar"] = len(ar_raw)
    awkey_present = 0
    for i, raw in enumerate(ar_raw):
        m = _map_row(raw, fm["ar"])
        dtn = (m.get("doc_type_native") or "").strip()
        dc = classify.doc_class_for(cfg, dtn)
        # PROFORMA must be excluded from matching, not dropped: quarantine w/ reason
        rec = _build_amount_doc(cfg, "AR", m, dc, i, ar_path, norm_ops)
        if dc["doc_class"] == "PROFORMA":
            res.quarantine.append({"source": "AR", "row_ref": rec["source_row_ref"],
                                   "reason": "excluded_doc_class:PROFORMA",
                                   "doc_id": rec["doc_id_native"]})
            continue
        if m.get("accounting_doc_id"):
            awkey_present += 1
        res.docs.append(rec)
    res.awkey_coverage = (awkey_present / raw_counts["ar"]) if raw_counts["ar"] else 0.0

    # ---- E-invoice docs -------------------------------------------------
    einv_raw = _read_csv(einv_path)
    raw_counts["einv"] = len(einv_raw)
    for i, raw in enumerate(einv_raw):
        m = _map_row(raw, fm["einv"])
        dtn = (m.get("doc_type_native") or "").strip()
        dc = classify.doc_class_for(cfg, dtn)
        rec = _build_amount_doc(cfg, "EINV", m, dc, i, einv_path, norm_ops)
        status = (m.get("einv_status") or "CLEARED").strip().upper()
        # Only a CLEARED e-invoice counts toward the E axis. Cancelled / rejected
        # / pending submissions are quarantined with a reason and counted, never
        # matched, so a booking behind a cancelled e-invoice reads as E2, not E1.
        if status != "CLEARED":
            res.quarantine.append({"source": "EINV", "row_ref": rec["source_row_ref"],
                                   "reason": f"einv_status:{status}",
                                   "doc_id": rec.get("billing_doc_id") or rec["doc_id_native"]})
            continue
        rec["einv_status"] = (m.get("einv_status") or "").strip() or None
        rec["einv_uuid"] = (m.get("einv_uuid") or "").strip() or None
        rec["einv_clearance_date"] = (m.get("einv_clearance_date") or "").strip() or None
        rec["einv_is_consolidated"] = str(m.get("einv_is_consolidated")).lower() in ("true", "1", "yes")
        rec["tax_registration_id"] = (m.get("tax_registration_id") or "").strip() or None
        res.docs.append(rec)

    res.stats = {
        "raw_counts": raw_counts,
        "gl_lines": len(res.gl_lines),
        "docs_gl": sum(1 for d in res.docs if d["plane"] == "GL"),
        "docs_ar": sum(1 for d in res.docs if d["plane"] == "AR"),
        "docs_einv": sum(1 for d in res.docs if d["plane"] == "EINV"),
        "quarantined": len(res.quarantine),
        "awkey_coverage": round(res.awkey_coverage, 4),
    }
    return res


def _build_amount_doc(cfg, plane, m, dc, i, path, norm_ops) -> dict:
    minor_exp = cfg.minor_exp
    doc_class = dc["doc_class"]
    sign = classify.sign_for(doc_class)
    net = abs(normalize.to_minor(m.get("net_amount"), minor_exp))
    tax = abs(normalize.to_minor(m.get("tax_amount"), minor_exp))
    gross = abs(normalize.to_minor(m.get("gross_amount"), minor_exp))
    if gross == 0:
        gross = net + tax
    tax_code = (m.get("tax_code") or "").strip() or None
    rate, category = cfg.tax_rate_for(tax_code)
    doc_date = (m.get("doc_date") or "").strip()
    rec = {
        "plane": plane,
        "source": plane,
        "row_id": _hash_id(plane, m.get("entity_id"),
                           m.get("official_doc_id") or m.get("billing_doc_id")
                           or m.get("doc_id_native"), i),
        "source_row_ref": f"{path}:{i+2}",
        "entity_id": (m.get("entity_id") or "").strip(),
        "doc_id_native": (m.get("doc_id_native") or m.get("billing_doc_id")
                          or m.get("official_doc_id") or "").strip(),
        "accounting_doc_id": (m.get("accounting_doc_id") or "").strip() or None,
        "billing_doc_id": (m.get("billing_doc_id") or "").strip() or None,
        "official_doc_id": (m.get("official_doc_id") or "").strip() or None,
        "fiscal_year": (m.get("fiscal_year") or doc_date[:4]).strip(),
        "doc_type_native": (m.get("doc_type_native") or "").strip(),
        "doc_class": doc_class,
        "sign": sign,
        "is_reversal": dc["is_reversal"],
        "doc_date": doc_date,
        "posting_date": (m.get("posting_date") or doc_date).strip(),
        "period": _period(doc_date),
        "currency": (m.get("currency") or cfg.country.get("currency")).strip(),
        "counterparty_tin": (m.get("counterparty_tin") or "").strip() or None,
        "counterparty_name": (m.get("counterparty_name") or "").strip() or None,
        "net_minor": net,
        "tax_minor": tax,
        "gross_minor": gross,
        "tax_code": tax_code,
        "tax_rate": str(rate) if rate is not None else None,
        "tax_category": category or "STANDARD",
        "einv_relevant": dc["einv_relevant"],
        # R axis (revenue/tax GL lines) is a GL-only property. AR is a customer
        # (C) document; EINV is the E axis. Neither sets R, so E7 can fire.
        "has_revenue": False,
        "has_customer": (plane == "AR"),
        "settlement_type": dc.get("settlement_type") or ("CREDIT" if plane == "AR" else "UNKNOWN"),
    }
    rec["norm_numbers"] = normalize.normalized_families(rec, norm_ops)
    rec["segment"] = classify.segment_for(rec["counterparty_tin"], rec["settlement_type"], None)
    return rec


def _aggregate_gl_docs(cfg, gl_lines, norm_ops) -> list[dict]:
    """Group GL lines by (entity, fiscal_year, accounting_doc_id) -> GL docs.

    Derives net/tax/gross planes from account classes so a GL voucher can be
    matched against AR and e-invoice documents.
    """
    groups = defaultdict(list)
    for ln in gl_lines:
        key = (ln["entity_id"], ln["fiscal_year"], ln["accounting_doc_id"])
        groups[key].append(ln)

    docs = []
    for (entity, fy, acc_doc), lines in groups.items():
        classes_present = {ln["account_class"] for ln in lines}
        customer_side = sum(ln["amount_minor"] for ln in lines if ln["account_class"] == "CUSTOMER_CONTROL")
        bank_side = sum(ln["amount_minor"] for ln in lines if ln["account_class"] == "BANK")
        revenue_side = sum(ln["amount_minor"] for ln in lines if ln["account_class"] in classify.REVENUE_CLASSES)
        tax_side = sum(ln["amount_minor"] for ln in lines if ln["account_class"] == "TAX_OUTPUT")

        has_revenue = any(ln["account_class"] in classify.REVENUE_CLASSES for ln in lines)
        has_customer = "CUSTOMER_CONTROL" in classes_present
        settlement = classify.settlement_for(classes_present, None)

        # representative line for doc-level attributes (prefer a revenue line)
        rep = next((ln for ln in lines if ln["account_class"] in classify.REVENUE_CLASSES), lines[0])
        cp = next((ln for ln in lines if ln["counterparty_tin"]), rep)
        doc_date = rep["doc_date"]
        einv_relevant = any(ln["einv_relevant"] for ln in lines)

        rec = {
            "plane": "GL",
            "source": "GL_REV_TAX",
            "row_id": _hash_id("GLDOC", entity, fy, acc_doc),
            "source_row_ref": ";".join(ln["source_row_ref"] for ln in lines),
            "entity_id": entity,
            "doc_id_native": acc_doc,
            "accounting_doc_id": acc_doc,
            "billing_doc_id": None,
            "official_doc_id": None,
            "fiscal_year": fy,
            "doc_type_native": rep["doc_type_native"],
            "doc_class": rep["doc_class"],
            "sign": classify.sign_for(rep["doc_class"]),
            "is_reversal": rep["is_reversal"],
            "doc_date": doc_date,
            "posting_date": rep["posting_date"],
            "period": _period(rep["posting_date"] or doc_date),
            "currency": rep["currency"],
            "counterparty_tin": cp["counterparty_tin"],
            "counterparty_name": cp["counterparty_name"],
            "profit_center": rep.get("profit_center"),
            "net_minor": abs(revenue_side),
            "tax_minor": abs(tax_side),
            "gross_minor": abs(customer_side + bank_side),
            "tax_code": rep["tax_code"],
            "tax_category": (cfg.tax_rate_for(rep["tax_code"])[1] or "STANDARD"),
            "einv_relevant": einv_relevant,
            "has_revenue": has_revenue,
            "has_customer": has_customer,
            "settlement_type": settlement,
            # Leg A raw sides for integrity
            "_customer_side": customer_side,
            "_bank_side": bank_side,
            "_revenue_side": revenue_side,
            "_tax_side": tax_side,
            "_line_count": len(lines),
            "_member_line_ids": [ln["row_id"] for ln in lines],
        }
        rec["norm_numbers"] = normalize.normalized_families(rec, norm_ops)
        rec["segment"] = classify.segment_for(rec["counterparty_tin"], settlement, None)
        docs.append(rec)
    return docs
