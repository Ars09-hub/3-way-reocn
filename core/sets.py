"""Build Set 1 (revenue/tax GL), Set 2 (customer GL / AR) and Set 3 (e-invoice).

Grain reduction to one record per voucher happens here (spec 1.1). Signs are
applied per family (spec 1.2): GL magnitudes get direction from debit/credit,
AR document-level amounts are already signed.
"""
from __future__ import annotations

import pandas as pd

from core import scope as scope_mod

REVENUE_TAX_CLASSES = ("REVENUE", "TAX_OUTPUT")


def annotate_gl(gl: pd.DataFrame, account_scope: dict, excluded_index: dict) -> pd.DataFrame:
    gl = gl.copy()
    gl["account_class"] = gl["gl_code_n"].map(lambda c: scope_mod.classify_account(c, account_scope))
    gl["excluded_reason"] = gl["gl_code_n"].map(lambda c: scope_mod.excluded_reason(c, excluded_index))
    deb = pd.to_numeric(gl["debit_amount"], errors="coerce").fillna(0)
    cred = pd.to_numeric(gl["credit_amount"], errors="coerce").fillna(0)
    # revenue and tax are credit-normal: invoices positive, credit notes negative
    gl["signed_local"] = ((cred - deb) * 100).round().astype("int64")
    return gl


def annotate_ar(ar: pd.DataFrame, account_scope: dict, excluded_index: dict) -> pd.DataFrame:
    ar = ar.copy()
    ar["account_class"] = ar["gl_code_n"].map(lambda c: scope_mod.classify_account(c, account_scope))
    ar["excluded_reason"] = ar["gl_code_n"].map(lambda c: scope_mod.excluded_reason(c, excluded_index))
    deb = pd.to_numeric(ar["debit_amount"], errors="coerce").fillna(0)
    cred = pd.to_numeric(ar["credit_amount"], errors="coerce").fillna(0)
    # receivable is an asset (debit-normal): invoices positive, credit notes negative
    ar["signed_receivable"] = ((deb - cred) * 100).round().astype("int64")
    return ar


def build_set1_vouchers(gl_annotated: pd.DataFrame) -> pd.DataFrame:
    """One record per grain_key from the GL side: revenue taxable + VAT output."""
    inscope = gl_annotated[
        gl_annotated["account_class"].isin(REVENUE_TAX_CLASSES)
        & gl_annotated["excluded_reason"].isna()
    ]
    rows = []
    for gk, g in inscope.groupby("grain_key", sort=True):
        rev = g[g["account_class"] == "REVENUE"]
        tax = g[g["account_class"] == "TAX_OUTPUT"]
        first = g.iloc[0]
        rows.append({
            "grain_key": gk,
            "company_code": first["company_code"],
            "fiscal_year": first["fiscal_year"],
            "voucher_number": first["voucher_number_s"],
            "voucher_date": first["voucher_date_d"],
            "document_date": first["document_date_d"],
            "document_reference": first.get("document_reference"),
            "customer_vat": first.get("customer_vat_n", ""),
            "gl_taxable_h": int(rev["signed_local"].sum()),
            "gl_tax_h": int(tax["signed_local"].sum()),
            "has_revenue": len(rev) > 0,
            "has_tax": len(tax) > 0,
            "line_ids": list(g["line_id"]),
        })
    return pd.DataFrame(rows)


def build_set2_vouchers(ar_annotated: pd.DataFrame) -> pd.DataFrame:
    """One record per grain_key from the AR side. doc_taxable is deduplicated (spec 1.1)."""
    rows = []
    for gk, g in ar_annotated.groupby("grain_key", sort=True):
        recv = g[g["account_class"] == "CUSTOMER_CONTROL"]
        rev = g[g["account_class"] == "REVENUE"]
        # doc-level values are stamped on every line: take one, assert constant
        dt = g["doc_taxable_h"].unique()
        dv = g["doc_vat_h"].unique()
        first = g.iloc[0]
        non_recv = g[g["account_class"] != "CUSTOMER_CONTROL"]
        offsets = set(non_recv["account_class"])
        excl = g["excluded_reason"].dropna().unique()
        # a receivable that offsets only to excluded accounts is out of scope,
        # never "missing in GL" (spec 2.3)
        only_excluded = len(non_recv) > 0 and non_recv["excluded_reason"].notna().all()
        rows.append({
            "grain_key": gk,
            "company_code": first["company_code"],
            "fiscal_year": first["fiscal_year"],
            "voucher_number": first["voucher_number_s"],
            "voucher_date": first["voucher_date_d"],
            "document_date": first["document_date_d"],
            "document_number": first.get("document_number"),
            "doc_number_n": first.get("doc_number_n", ""),
            "document_type": first.get("document_type"),
            "customer_name": first.get("customer_name"),
            "customer_vat": first.get("customer_vat_n", ""),
            "tax_code": first.get("tax_code"),
            "tax_rate": first.get("tax_rate"),
            "ar_taxable_h": int(dt[0]) if len(dt) else 0,
            "ar_vat_h": int(dv[0]) if len(dv) else 0,
            "ar_gross_h": int(recv["signed_receivable"].sum()),
            "has_receivable": len(recv) > 0,
            "has_revenue": len(rev) > 0,
            "offset_classes": sorted(offsets),
            "only_excluded_offsets": bool(only_excluded),
            "excluded_reasons": list(excl),
            "line_ids": list(g["line_id"]),
        })
    return pd.DataFrame(rows)


def excluded_bucket(annotated: pd.DataFrame, value_col: str) -> dict:
    ex = annotated[annotated["excluded_reason"].notna()]
    val = pd.to_numeric(ex[value_col], errors="coerce").abs().fillna(0).sum()
    by_reason = (
        ex.assign(_v=pd.to_numeric(ex[value_col], errors="coerce").abs().fillna(0))
        .groupby("excluded_reason")
        .agg(rows=("excluded_reason", "size"), value=("_v", "sum"))
        .to_dict("index")
    )
    return {"rows": int(len(ex)), "value": float(val), "by_reason": by_reason}
