"""Three-way assessment, derived from leg 1 and leg 2 (spec 4, page 4).

One row per economic event. The AR voucher grain is the spine; e-invoice-only
documents (reported but never booked) are added as their own events. Statuses use
the report's own words, never internal codes.
"""
from __future__ import annotations

import pandas as pd

STATUS_ACTIONS = {
    "Fully reconciled": "No action needed",
    "Reconciled with differences": "Review the difference between the three sets",
    "Not e-invoiced": "Report to ZATCA",
    "Not booked": "No accounting entry found, investigate",
    "Billed but no revenue posted": "Confirm whether this is a taxable supply",
    "Revenue posted, not billed": "Confirm whether a customer invoice is missing",
    "Not a supply": "No action, journal or clearing entry",
    "Out of scope by design": "No action, out of scope",
}


def _ei_state_map(leg2: dict) -> dict:
    """grain_key -> dict(reported, agree, not_accepted, einv_no, taxable_h, vat_h)."""
    m = {}
    er = leg2["einv_rows"]
    if not len(er):
        return m
    for _, r in er.iterrows():
        gk = r.get("ar_grain")
        if gk is None or (isinstance(gk, float) and pd.isna(gk)):
            continue
        not_accepted = r["category"] == "Submitted but not accepted"
        m[gk] = {
            "reported": r["category"] in ("Exact match", "Amount mismatch"),
            "agree": r["category"] == "Exact match",
            "not_accepted": not_accepted,
            "einv_no": r["einv_no"], "einv_taxable_h": r["einv_taxable_h"],
            "einv_vat_h": r["einv_vat_h"], "status": r["status"],
        }
    return m


def derive(leg1: dict, leg2: dict) -> dict:
    ei_state = _ei_state_map(leg2)
    events = []

    for _, r in leg1["rows"].iterrows():
        gk = r["grain_key"]
        cat1 = r["category"]
        has_gl = bool(r["in_gl"])
        has_ar = bool(r["in_ar"])
        is_jv = str(r.get("document_type")) == "JV"
        ei = ei_state.get(gk)
        has_reported_ei = ei is not None and ei["reported"]
        failed_ei = ei is not None and ei["not_accepted"]

        if has_reported_ei:
            ei_col = "Yes"
        elif failed_ei:
            ei_col = "Not accepted"
        else:
            ei_col = "No"

        if cat1 == "Out of scope by design":
            status = "Out of scope by design"
        elif is_jv:
            status = "Not a supply"
        elif has_gl and has_ar:
            if has_reported_ei:
                status = "Fully reconciled" if (cat1 == "Exact match" and ei["agree"]) \
                    else "Reconciled with differences"
            else:
                status = "Not e-invoiced"
        elif has_gl and not has_ar:
            status = "Revenue posted, not billed"
        else:  # has_ar, no GL revenue/tax
            status = "Billed but no revenue posted"

        taxable = r["ar_taxable_h"] if pd.notna(r["ar_taxable_h"]) else r["gl_taxable_h"]
        vat = r["ar_vat_h"] if pd.notna(r["ar_vat_h"]) else r["gl_tax_h"]
        taxable = 0 if pd.isna(taxable) else taxable
        vat = 0 if pd.isna(vat) else vat
        action = STATUS_ACTIONS[status]
        if status in ("Not e-invoiced", "Not booked") and failed_ei:
            action = "Investigate failed submission and resubmit"

        events.append({
            "grain_key": gk, "voucher_number": r["voucher_number"],
            "document_number": r["document_number"], "document_type": r["document_type"],
            "date": r["voucher_date"], "customer_name": r["customer_name"],
            "customer_vat": r["customer_vat"],
            "in_gl": has_gl, "in_ar": has_ar, "einvoice": ei_col,
            "taxable_h": int(taxable),
            "vat_h": int(vat),
            "status": status, "action": action,
            "einv_no": (ei["einv_no"] if ei else None),
        })

    # e-invoice-only events: reported/failed e-invoices that consumed no AR grain
    er = leg2["einv_rows"]
    if len(er):
        for _, r in er.iterrows():
            gk = r.get("ar_grain")
            if not (gk is None or (isinstance(gk, float) and pd.isna(gk))):
                continue  # already represented through its AR grain
            if r["category"] == "Missing in AR":
                status, action = "Not booked", STATUS_ACTIONS["Not booked"]
                ei_col = "Yes"
            elif r["category"] == "Submitted but not accepted":
                status, action = "Not booked", "Investigate failed submission and resubmit"
                ei_col = "Not accepted"
            else:
                continue  # Out of period / others handled elsewhere
            events.append({
                "grain_key": None, "voucher_number": None,
                "document_number": r["einv_no"], "document_type": r["doc_type"],
                "date": r["issue_date"], "customer_name": r["buyer_name"],
                "customer_vat": r["buyer_vat"], "in_gl": False, "in_ar": False,
                "einvoice": ei_col, "taxable_h": int(r["einv_taxable_h"]),
                "vat_h": int(r["einv_vat_h"]), "status": status, "action": action,
                "einv_no": r["einv_no"],
            })

    df = pd.DataFrame(events)
    order = ["Fully reconciled", "Reconciled with differences", "Not e-invoiced",
             "Not booked", "Billed but no revenue posted", "Revenue posted, not billed",
             "Not a supply", "Out of scope by design"]
    counts = {c: (int((df["status"] == c).sum()) if len(df) else 0) for c in order}

    # flow figures: counts and value present in each set
    flow = {
        "gl": {"n": int(df["in_gl"].sum()) if len(df) else 0,
               "value_h": int(df[df["in_gl"]]["taxable_h"].sum()) if len(df) else 0},
        "ar": {"n": int(df["in_ar"].sum()) if len(df) else 0,
               "value_h": int(df[df["in_ar"]]["taxable_h"].sum()) if len(df) else 0},
        "einv": {"n": int((df["einvoice"] == "Yes").sum()) if len(df) else 0,
                 "value_h": int(df[df["einvoice"] == "Yes"]["taxable_h"].sum()) if len(df) else 0},
    }
    return {"events": df, "counts": counts, "order": order, "flow": flow}
