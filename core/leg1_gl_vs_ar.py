"""Leg 1: Revenue and tax GL (Set 1) compared to customer GL / AR (Set 2).

Join on grain key (company_code + fiscal_year + voucher_number + voucher_date).
Categories (spec 4): Exact match, Amount mismatch, Missing in AR, Missing in GL,
Out of scope by design. Runs on in-window vouchers; out-of-window is separate.
"""
from __future__ import annotations

import pandas as pd

from core import matchutil


def run(set1: pd.DataFrame, set2: pd.DataFrame, engine: dict, frm: pd.Timestamp, to: pd.Timestamp) -> dict:
    s1 = set1.copy()
    s2 = set2.copy()
    s1["in_window"] = s1["voucher_date"].map(lambda d: matchutil.in_window(d, frm, to))
    s2["in_window"] = s2["voucher_date"].map(lambda d: matchutil.in_window(d, frm, to))

    s1_in = s1[s1["in_window"]].set_index("grain_key", drop=False)
    s2_in = s2[s2["in_window"]].set_index("grain_key", drop=False)

    keys = sorted(set(s1_in["grain_key"]) | set(s2_in["grain_key"]))
    rows = []
    for gk in keys:
        g = s1_in.loc[[gk]].iloc[0] if gk in s1_in.index else None
        a = s2_in.loc[[gk]].iloc[0] if gk in s2_in.index else None

        gl_tax = int(g["gl_taxable_h"]) if g is not None else None
        gl_vat = int(g["gl_tax_h"]) if g is not None else None
        ar_tax = int(a["ar_taxable_h"]) if a is not None else None
        ar_vat = int(a["ar_vat_h"]) if a is not None else None
        ar_gross = int(a["ar_gross_h"]) if a is not None else None

        # A voucher whose non-receivable offsets are all excluded accounts
        # (interest, forex, intercompany, deferred) is out of scope by design,
        # even if a stray zero-value VAT output line pulls it into Set 1 (spec 2.3).
        ar_out_of_scope = a is not None and bool(a["only_excluded_offsets"])

        if ar_out_of_scope:
            category = "Out of scope by design"
        elif g is not None and a is not None:
            tax_ok = matchutil.within_tolerance(gl_tax, ar_tax, engine)
            vat_ok = matchutil.within_tolerance(gl_vat, ar_vat, engine)
            category = "Exact match" if (tax_ok and vat_ok) else "Amount mismatch"
        elif g is not None:
            category = "Missing in AR"
        else:  # AR only
            category = "Missing in GL"

        base = a if a is not None else g
        rows.append({
            "grain_key": gk,
            "voucher_number": base["voucher_number"],
            "document_number": (a["document_number"] if a is not None else base.get("document_reference")),
            "document_type": (a["document_type"] if a is not None else None),
            "voucher_date": base["voucher_date"],
            "document_date": base["document_date"],
            "customer_name": (a["customer_name"] if a is not None else None),
            "customer_vat": (a["customer_vat"] if a is not None else g["customer_vat"]),
            "tax_code": (a["tax_code"] if a is not None else None),
            "tax_rate": (a["tax_rate"] if a is not None else None),
            "gl_taxable_h": gl_tax, "gl_tax_h": gl_vat,
            "ar_taxable_h": ar_tax, "ar_vat_h": ar_vat, "ar_gross_h": ar_gross,
            "diff_taxable_h": (None if (gl_tax is None or ar_tax is None) else ar_tax - gl_tax),
            "diff_tax_h": (None if (gl_vat is None or ar_vat is None) else ar_vat - gl_vat),
            "in_gl": g is not None,
            "in_ar": a is not None,
            "category": category,
            "gl_line_ids": (list(g["line_ids"]) if g is not None else []),
            "ar_line_ids": (list(a["line_ids"]) if a is not None else []),
        })
    result = pd.DataFrame(rows)

    order = ["Exact match", "Amount mismatch", "Missing in AR", "Missing in GL", "Out of scope by design"]
    counts = {c: int((result["category"] == c).sum()) if len(result) else 0 for c in order}
    values = {}
    for c in order:
        sub = result[result["category"] == c] if len(result) else result
        val_col = sub["ar_taxable_h"].fillna(sub["gl_taxable_h"]) if len(sub) else pd.Series([], dtype="float64")
        values[c] = int(val_col.fillna(0).abs().sum()) if len(sub) else 0

    out_of_window = pd.concat([
        s1[~s1["in_window"]].assign(side="gl"),
        s2[~s2["in_window"]].assign(side="ar"),
    ], ignore_index=True)

    return {"rows": result, "counts": counts, "values": values, "order": order,
            "out_of_window": out_of_window}
