"""Write the CSV outputs and the run manifest (spec 6).

Deterministic: rows are sorted on stable keys and amounts are rendered from
integer halalas, so two runs produce byte-identical CSV output (spec test 15).
No wall-clock value is written.
"""
from __future__ import annotations

import json
import os

import pandas as pd


def _amt(h):
    if h is None or (isinstance(h, float) and pd.isna(h)):
        return ""
    return f"{int(h) / 100:.2f}"


def _date(d):
    if d is None or pd.isna(d):
        return ""
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def write_all(R: dict, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    written = {}

    # leg 1
    l1 = R["leg1"]["rows"].copy()
    if len(l1):
        l1 = l1.sort_values(["category", "grain_key"])
        rec = pd.DataFrame({
            "voucher_number": l1["voucher_number"], "document_number": l1["document_number"],
            "document_type": l1["document_type"], "voucher_date": l1["voucher_date"].map(_date),
            "customer_name": l1["customer_name"], "customer_vat": l1["customer_vat"],
            "gl_taxable": l1["gl_taxable_h"].map(_amt), "gl_tax": l1["gl_tax_h"].map(_amt),
            "ar_taxable": l1["ar_taxable_h"].map(_amt), "ar_vat": l1["ar_vat_h"].map(_amt),
            "ar_gross": l1["ar_gross_h"].map(_amt), "diff_taxable": l1["diff_taxable_h"].map(_amt),
            "diff_tax": l1["diff_tax_h"].map(_amt), "tax_code": l1["tax_code"], "status": l1["category"],
        })
        written["leg1"] = _csv(rec, out_dir, "leg1_gl_vs_ar.csv")

    # leg 2
    l2 = R["leg2"]["einv_rows"].copy()
    if len(l2):
        l2 = l2.sort_values(["category", "einv_no"])
        rec = pd.DataFrame({
            "einvoice_no": l2["einv_no"], "issue_date": l2["issue_date"].map(_date),
            "doc_type": l2["doc_type"], "transaction_type": l2["txn_type"], "invoice_status": l2["status"],
            "buyer_name": l2["buyer_name"], "buyer_vat": l2["buyer_vat"],
            "einv_taxable": l2["einv_taxable_h"].map(_amt), "einv_vat": l2["einv_vat_h"].map(_amt),
            "einv_total": l2["einv_total_h"].map(_amt),
            "ar_voucher": l2.get("ar_voucher"), "ar_taxable": l2.get("ar_taxable_h"),
            "ar_vat": l2.get("ar_vat_h"), "ar_gross": l2.get("ar_gross_h"),
            "how_matched": l2["matched_how"], "status": l2["category"],
        })
        for c in ["ar_taxable", "ar_vat", "ar_gross"]:
            rec[c] = rec[c].map(_amt) if c in rec else ""
        written["leg2"] = _csv(rec, out_dir, "leg2_einv_vs_ar.csv")

    # three way
    tw = R["threeway"]["events"].copy()
    if len(tw):
        tw = tw.sort_values(["status", "grain_key", "document_number"], na_position="last")
        rec = pd.DataFrame({
            "voucher_number": tw["voucher_number"], "document_number": tw["document_number"],
            "date": tw["date"].map(_date), "customer_name": tw["customer_name"],
            "customer_vat": tw["customer_vat"], "in_revenue_tax_gl": tw["in_gl"],
            "in_customer_gl": tw["in_ar"], "in_einvoice": tw["einvoice"],
            "taxable": tw["taxable_h"].map(_amt), "vat": tw["vat_h"].map(_amt),
            "three_way_status": tw["status"], "what_to_do_next": tw["action"],
        })
        written["threeway"] = _csv(rec, out_dir, "three_way.csv")

    # customers
    cv = R["customers"].copy()
    if len(cv):
        rec = cv.copy()
        for c in [c for c in rec.columns if c.endswith(("_v", "taxable_h", "vat_h"))]:
            rec[c] = rec[c].map(_amt)
        written["customers"] = _csv(rec, out_dir, "customer_summary.csv")

    # suggested combinations
    combos = _combinations_frame(R)
    written["combinations"] = _csv(combos, out_dir, "suggested_combinations.csv")

    # suggested account additions
    sa = R["quality"]["suggested_accounts"].copy()
    if len(sa):
        sa["value"] = sa["value_h"].map(_amt)
        sa = sa.drop(columns=["value_h"])
    written["account_additions"] = _csv(sa, out_dir, "suggested_account_additions.csv")

    # quarantine
    q = _quarantine_frame(R)
    written["quarantine"] = _csv(q, out_dir, "quarantine.csv")

    # manifest
    manifest = _manifest(R)
    with open(os.path.join(out_dir, "run_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, default=str)
    written["manifest"] = manifest
    return written


def _csv(df: pd.DataFrame, out_dir: str, name: str) -> str:
    path = os.path.join(out_dir, name)
    df.to_csv(path, index=False, lineterminator="\n")
    return path


def _combinations_frame(R):
    rows = []
    for item in R["leg2"]["suggested"] + R["leg2"]["ambiguous"]:
        combo = item["combo"]
        rows.append({
            "einvoice_no": item["einv_no"], "type": ("suggested" if combo["n_alternatives"] == 1 else "needs_review"),
            "n_vouchers": combo["n_docs"], "n_alternatives": combo["n_alternatives"],
            "ar_vouchers": ";".join(str(x) for x in combo["indices"]),
            "einv_vat": _amt(item["einv_vat_h"]), "group_vat": _amt(combo["group_vat_h"]),
        })
    return pd.DataFrame(rows, columns=["einvoice_no", "type", "n_vouchers", "n_alternatives",
                                       "ar_vouchers", "einv_vat", "group_vat"]).sort_values(
        ["type", "einvoice_no"]).reset_index(drop=True) if rows else pd.DataFrame(
        columns=["einvoice_no", "type", "n_vouchers", "n_alternatives", "ar_vouchers", "einv_vat", "group_vat"])


def _quarantine_frame(R):
    rows = []
    test = R["quality"]["test_rows"]
    for _, r in test.iterrows():
        rows.append({"source": "e-invoice", "reason": "test data", "document": r["document_number"],
                     "customer": r["buyer_name_en"], "value": _amt(r["taxable_h"])})
    hist = R["ei_hist"]
    for _, r in hist.iterrows():
        rows.append({"source": "e-invoice", "reason": "duplicate submission attempt",
                     "document": r["document_number_raw"], "customer": r["buyer_name_en"],
                     "value": _amt(r["taxable_h"])})
    return pd.DataFrame(rows, columns=["source", "reason", "document", "customer", "value"]).sort_values(
        ["reason", "document"]).reset_index(drop=True) if rows else pd.DataFrame(
        columns=["source", "reason", "document", "customer", "value"])


def _manifest(R):
    per = R["period"]
    return {
        "reconciled_window": {"from": _date(per["from"]), "to": _date(per["to"])},
        "row_counts": {"gl": int(len(R["gl"])), "ar": int(len(R["ar"])),
                       "einvoice_raw": 39, "einvoice_deduped": int(len(R["ei"]))},
        "set_sizes": {"set1": int(len(R["set1"])), "set2": int(len(R["set2"])),
                      "set3_non_test": int((~R["ei"]["is_test"]).sum())},
        "leg1_counts": R["leg1"]["counts"],
        "leg2_counts": R["leg2"]["counts"],
        "threeway_counts": R["threeway"]["counts"],
        "open_decisions": R["quality"]["open_decisions"],
        "config": {"tolerance": R["cfg"]["engine"]["tolerance"],
                   "period_basis": R["cfg"]["engine"]["period"]["erp_date_field"]},
    }
