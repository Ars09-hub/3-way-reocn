"""Drill-through registry (addendum sections 5, 6).

Precomputes, for every clickable figure, the exact document keys behind it so the
browser never re-derives filter logic. Each entry:

    {label, origin, grain, count, glKeys, arKeys, eiKeys[, glLids, arLids, eiLids]}

count is the figure as shown on the origin page (at its stated grain). Voucher and
e-invoice figures filter by document key; row-level data-quality figures filter by
line id (glLids/arLids/eiLids) so the drill hits exactly the flagged lines.

verify() recomputes the count the Document detail page would show at the entry's
grain and flags any entry where it disagrees with the origin figure (test 20).
Sub-bucket sums are asserted against their parent (test 21).
"""
from __future__ import annotations

import re

import pandas as pd

from core import normalize as nz

_CANON = re.compile(r"^(CM|DM)-", re.IGNORECASE)


def canon(key: str) -> str:
    p = str(key).split("|")
    if len(p) >= 3:
        p[2] = _CANON.sub("", p[2])
    return "|".join(p)


def _ev_keys(events: pd.DataFrame):
    gl, ar, ei = set(), set(), set()
    for _, e in events.iterrows():
        gl |= set(e.get("gl_keys") or [])
        ar |= set(e.get("ar_keys") or [])
        ei |= set(str(x) for x in (e.get("ei_keys") or []))
    return sorted(gl), sorted(ar), sorted(ei)


def _entry(label, origin, grain, count, gl=None, ar=None, ei=None,
           glLids=None, arLids=None, eiLids=None):
    e = {"label": label, "origin": origin, "grain": grain, "count": int(count),
         "glKeys": sorted(gl or []), "arKeys": sorted(ar or []),
         "eiKeys": sorted(str(x) for x in (ei or []))}
    if grain == "rows":
        e["glLids"] = sorted(str(x) for x in (glLids or []))
        e["arLids"] = sorted(str(x) for x in (arLids or []))
        e["eiLids"] = sorted(str(x) for x in (eiLids or []))
    return e


def _voucher_entry(label, origin, events, grain="vouchers", count=None):
    gl, ar, ei = _ev_keys(events)
    return _entry(label, origin, grain, len(events) if count is None else count, gl, ar, ei)


def build_registry(R: dict) -> dict:
    reg = {}
    tw = R["threeway"]["events"]
    l1 = R["leg1"]["rows"]
    l2 = R["leg2"]["einv_rows"]
    l2miss = R["leg2"]["missing_rows"]
    gla, ara = R["gla"], R["ara"]
    ei_raw = R["ei_raw"]
    ksa = R["cfg"]["ksa"]
    frm, to = R["period"]["from"], R["period"]["to"]

    supplies = tw[~tw["status"].isin(["Out of scope by design", "Not a supply"])]

    # ---- Executive summary --------------------------------------------------
    reg["exec.sales_in_scope"] = _voucher_entry("Sales value in scope", "Executive summary", supplies)
    reg["exec.vat_in_scope"] = _voucher_entry(
        "VAT in scope", "Executive summary", supplies[supplies["vat_h"] != 0])
    reg["exec.fully_reconciled"] = _voucher_entry(
        "Fully reconciled", "Executive summary", tw[tw["status"] == "Fully reconciled"])
    reg["exec.not_einvoiced"] = _voucher_entry(
        "Not e-invoiced", "Executive summary", tw[tw["status"] == "Not e-invoiced"])
    reg["exec.not_booked"] = _voucher_entry(
        "Not booked", "Executive summary", tw[tw["status"] == "Not booked"],
        grain="e-invoice documents")
    reg["exec.differences"] = _voucher_entry(
        "Differences to review", "Executive summary",
        tw[tw["status"] == "Reconciled with differences"])
    reg["exec.out_of_scope"] = _voucher_entry(
        "Out of scope by design", "Executive summary",
        tw[tw["status"] == "Out of scope by design"])
    na = l2[l2["category"] == "Submitted but not accepted"] if len(l2) else l2
    reg["exec.submitted_not_accepted"] = _entry(
        "Submitted, not accepted", "Executive summary", "e-invoice documents",
        len(na), ei=list(na["ei_key"]) if len(na) else [])

    # ---- GL vs AR strip (leg 1) --------------------------------------------
    reg["leg1.all"] = _voucher_entry("All", "GL vs AR", l1)
    _l1 = {"Exact match": "leg1.exact_match", "Amount mismatch": "leg1.amount_mismatch",
           "Missing in AR": "leg1.missing_in_ar", "Missing in GL": "leg1.missing_in_gl",
           "Out of scope by design": "leg1.out_of_scope"}
    for cat, rid in _l1.items():
        reg[rid] = _voucher_entry(cat, "GL vs AR", l1[l1["category"] == cat])

    # leg1 amount-mismatch sub-buckets (diagnosis)
    mm = l1[l1["category"] == "Amount mismatch"].copy()
    tax_only = mm[(mm["diff_tax_h"].fillna(0) != 0) & (mm["diff_taxable_h"].fillna(0) == 0)]
    tv_only = mm[(mm["diff_tax_h"].fillna(0) == 0) & (mm["diff_taxable_h"].fillna(0) != 0)]
    both = mm[(mm["diff_tax_h"].fillna(0) != 0) & (mm["diff_taxable_h"].fillna(0) != 0)]
    reg["leg1.amount_mismatch.tax_only"] = _voucher_entry("Tax differs only", "GL vs AR", tax_only)
    reg["leg1.amount_mismatch.taxable_only"] = _voucher_entry("Taxable value differs only", "GL vs AR", tv_only)
    reg["leg1.amount_mismatch.both"] = _voucher_entry("Both differ", "GL vs AR", both)

    # leg1 out-of-scope sub-buckets (exclusion reason)
    reason_of = _grain_reason(ara)
    oos = l1[l1["category"] == "Out of scope by design"]
    by_reason: dict[str, list] = {}
    for _, r in oos.iterrows():
        by_reason.setdefault(reason_of.get(r["grain_key"], "other"), []).append(r)
    _reason_label = {"interest": "Interest", "forex": "Forex", "intercompany": "Intercompany",
                     "deferred revenue, not a supply until recognised": "Deferred revenue",
                     "purchase side": "Purchase-side VAT", "other": "Other"}
    for reason, rows in by_reason.items():
        rid = "leg1.out_of_scope." + re.sub(r"[^a-z]+", "_", reason.split(",")[0].lower()).strip("_")
        reg[rid] = _voucher_entry(_reason_label.get(reason, reason), "GL vs AR",
                                  pd.DataFrame(rows))

    # ---- E-invoice vs AR strip (leg 2) -------------------------------------
    reg["leg2.all"] = _entry("All", "E-invoice vs AR", "e-invoice documents",
                             len(l2), ei=list(l2["ei_key"]) if len(l2) else [])
    _l2 = {"Exact match": "leg2.exact_match", "Amount mismatch": "leg2.amount_mismatch",
           "Missing in AR": "leg2.missing_in_ar", "Submitted but not accepted": "leg2.not_accepted",
           "Suggested combination": "leg2.suggested", "Out of period": "leg2.out_of_period"}
    for cat, rid in _l2.items():
        sub = l2[l2["category"] == cat] if len(l2) else l2
        reg[rid] = _entry(cat, "E-invoice vs AR", "e-invoice documents",
                          len(sub), ei=list(sub["ei_key"]) if len(sub) else [])
    # Missing in e-invoice is AR-voucher grained
    reg["leg2.missing_in_einvoice"] = _entry(
        "Missing in e-invoice", "E-invoice vs AR", "vouchers", len(l2miss),
        ar=list(_explode(l2miss, "ar_keys")) if len(l2miss) else [])

    # leg2 not-accepted sub-buckets (FAILED / NOT_SUBMITTED)
    if len(na):
        for st, rid in [("FAILED", "leg2.not_accepted.failed"),
                        ("NOT_SUBMITTED", "leg2.not_accepted.not_submitted")]:
            sub = na[na["status"] == st]
            reg[rid] = _entry(st, "E-invoice vs AR", "e-invoice documents",
                              len(sub), ei=list(sub["ei_key"]) if len(sub) else [])

    # leg2 missing-in-einvoice sub-buckets (failed row exists vs no row at all)
    if len(l2miss):
        failed_docs = set(ei_raw[~ei_raw["is_reported"]]["doc_number_n"])
        na_rows, no_rows = [], []
        for _, r in l2miss.iterrows():
            arn = _first_doc_norm(r)
            (na_rows if arn in failed_docs else no_rows).append(r)
        reg["leg2.missing_in_einvoice.not_accepted"] = _entry(
            "E-invoice exists but not accepted", "E-invoice vs AR", "vouchers", len(na_rows),
            ar=list(_explode(pd.DataFrame(na_rows), "ar_keys")) if na_rows else [])
        reg["leg2.missing_in_einvoice.no_row"] = _entry(
            "No e-invoice at all", "E-invoice vs AR", "vouchers", len(no_rows),
            ar=list(_explode(pd.DataFrame(no_rows), "ar_keys")) if no_rows else [])

    # ---- Three-way assessment ----------------------------------------------
    flow = R["threeway"]["flow"]
    reg["threeway.flow_gl"] = _voucher_entry("Revenue and tax GL", "Three-way assessment",
                                             tw[tw["in_gl"]], count=flow["gl"]["n"])
    reg["threeway.flow_ar"] = _voucher_entry("Customer GL", "Three-way assessment",
                                             tw[tw["in_ar"]], count=flow["ar"]["n"])
    reg["threeway.flow_einv"] = _entry("E-invoice reported", "Three-way assessment",
                                       "e-invoice documents", flow["einv"]["n"],
                                       ei=list(_explode(tw[tw["einvoice"] == "Yes"], "ei_keys")))
    _tw_grain = {"Not booked": "e-invoice documents"}
    for status in R["threeway"]["order"]:
        n = R["threeway"]["counts"][status]
        if n == 0:
            continue
        rid = "threeway.status." + re.sub(r"[^a-z]+", "_", status.lower()).strip("_")
        reg[rid] = _voucher_entry(status, "Three-way assessment",
                                  tw[tw["status"] == status], grain=_tw_grain.get(status, "vouchers"))

    # ---- Customer view ------------------------------------------------------
    cust = R["customers"]
    tw_c = tw.copy()
    tw_c["cust_key"] = tw_c.apply(lambda r: _cust_key(r, ksa), axis=1)
    for i, cr in cust.iterrows():
        key = cr["customer_key"]
        evs = tw_c[tw_c["cust_key"] == key]
        base = f"customer.{i}"
        reg[base + ".all"] = _voucher_entry(cr["customer_name"] + " (all)", "Customer view",
                                            evs, count=cr["vouchers"])
        reg[base + ".fully_reconciled"] = _voucher_entry(
            "Fully reconciled", "Customer view", evs[evs["status"] == "Fully reconciled"],
            count=cr["fully_reconciled_n"])
        reg[base + ".not_einvoiced"] = _voucher_entry(
            "Not e-invoiced", "Customer view", evs[evs["status"] == "Not e-invoiced"],
            count=cr["not_einvoiced_n"])
        reg[base + ".not_booked"] = _voucher_entry(
            "Not booked", "Customer view", evs[evs["status"] == "Not booked"],
            grain="e-invoice documents", count=cr["not_booked_n"])
        reg[base + ".differences"] = _voucher_entry(
            "Differences", "Customer view", evs[evs["status"] == "Reconciled with differences"],
            count=cr["differences_n"])

    # ---- Data quality (row/line grained) -----------------------------------
    _dq(reg, R, gla, ara, ei_raw, ksa, frm, to)

    return reg


# --------------------------------------------------------------------------- helpers

def _dq(reg, R, gla, ara, ei_raw, ksa, frm, to):
    def oop(df, field):
        d = df[field]
        return df[(d < frm) | (d > to)]

    gl_oop = oop(gla, "voucher_date_d")
    ar_oop = oop(ara, "voucher_date_d")
    ei_oop = oop(ei_raw[~ei_raw["is_test"]], "issue_date_d")
    reg["dq.out_of_period"] = _entry(
        "Out of period", "Data quality", "rows",
        len(gl_oop) + len(ar_oop) + len(ei_oop),
        glLids=list(gl_oop["line_id"]), arLids=list(ar_oop["line_id"]), eiLids=list(ei_oop["row_id"]))

    test = ei_raw[ei_raw["is_test"]]
    reg["dq.test_data"] = _entry("Test data quarantined", "Data quality", "e-invoice documents",
                                 len(test), ei=list(test["ei_key"]))

    hist = R["ei_hist"]
    reg["dq.duplicate"] = _entry("Duplicate submissions", "Data quality", "e-invoice documents",
                                 hist["document_number_raw"].nunique() if len(hist) else 0,
                                 ei=list(hist["ei_key"]) if len(hist) else [])

    gex = gla[gla["excluded_reason"].notna()]
    aex = ara[ara["excluded_reason"].notna()]
    reg["dq.excluded"] = _entry("Excluded accounts", "Data quality", "rows", len(gex) + len(aex),
                                glLids=list(gex["line_id"]), arLids=list(aex["line_id"]))

    ar_inv = ara[(ara["customer_vat_n"] != "") & (~ara["customer_vat_n"].map(lambda v: nz.is_valid_tin(v, ksa["tin"])))]
    ei_inv = ei_raw[(ei_raw["buyer_vat_n"] != "") & (~ei_raw["buyer_vat_n"].map(lambda v: nz.is_valid_tin(v, ksa["tin"])))]
    reg["dq.invalid_vat"] = _entry("Invalid VAT numbers", "Data quality", "rows",
                                   len(ar_inv) + len(ei_inv),
                                   arLids=list(ar_inv["line_id"]), eiLids=list(ei_inv["row_id"]))

    ar_mv = ara[ara["customer_vat_n"] == ""]
    ei_mv = ei_raw[ei_raw["buyer_vat_n"] == ""]
    reg["dq.missing_vat"] = _entry("Missing VAT numbers", "Data quality", "rows",
                                   len(ar_mv) + len(ei_mv),
                                   arLids=list(ar_mv["line_id"]), eiLids=list(ei_mv["row_id"]))

    unc = ara[ara["gl_classification"].isna()]
    reg["dq.unclassified"] = _entry("Unclassified rows", "Data quality", "rows", len(unc),
                                    arLids=list(unc["line_id"]))

    vnr = R["quality"]["vat_no_revenue"]
    vnr_gla = gla[gla["voucher_number_n"].isin(set(vnr))]
    reg["dq.vat_no_revenue"] = _entry("Vouchers with VAT but no revenue line", "Data quality",
                                      "vouchers", len(vnr),
                                      gl=sorted(set(vnr_gla["gl_key"])))


def _grain_reason(ara: pd.DataFrame) -> dict:
    """grain_key -> dominant exclusion reason (by line count)."""
    out = {}
    ex = ara[ara["excluded_reason"].notna()]
    for gk, g in ex.groupby("grain_key"):
        out[gk] = g["excluded_reason"].value_counts().index[0]
    return out


def _cust_key(row, ksa):
    vat = str(row["customer_vat"]) if row["customer_vat"] else ""
    if nz.is_valid_tin(vat, ksa["tin"]):
        return vat
    name = row["customer_name"]
    return name if pd.notna(name) and str(name).strip() else "(no customer)"


def _explode(df, col):
    out = set()
    if df is None or not len(df):
        return out
    for v in df[col]:
        out |= set(v or [])
    return out


def _first_doc_norm(row):
    ks = row.get("ar_keys") or []
    return nz.normalize_doc_number(str(row.get("ar_document") or ""))


# --------------------------------------------------------------------------- verification

def verify(reg: dict) -> list:
    """Recompute the count Document detail shows at each entry's grain (test 20)."""
    out = []
    for rid, e in reg.items():
        grain = e["grain"]
        if grain == "rows":
            dc = len(e.get("glLids", [])) + len(e.get("arLids", [])) + len(e.get("eiLids", []))
        elif grain == "e-invoice documents":
            dc = len(set(e["eiKeys"]))
        else:  # vouchers / documents
            dc = len({canon(k) for k in e["glKeys"]} | {canon(k) for k in e["arKeys"]})
        out.append({"id": rid, "origin": e["origin"], "label": e["label"], "grain": grain,
                    "figure": e["count"], "filtered": dc, "match": e["count"] == dc})
    return out


def subbucket_check(reg: dict) -> list:
    """Assert each parent bucket equals the sum of its sub-buckets (test 21)."""
    parents = {
        "leg1.amount_mismatch": ["leg1.amount_mismatch.tax_only", "leg1.amount_mismatch.taxable_only",
                                 "leg1.amount_mismatch.both"],
        "leg2.not_accepted": ["leg2.not_accepted.failed", "leg2.not_accepted.not_submitted"],
        "leg2.missing_in_einvoice": ["leg2.missing_in_einvoice.not_accepted",
                                     "leg2.missing_in_einvoice.no_row"],
        "leg1.out_of_scope": [k for k in reg if k.startswith("leg1.out_of_scope.")],
    }
    rows = []
    for parent, subs in parents.items():
        if parent not in reg:
            continue
        got = sum(reg[s]["count"] for s in subs if s in reg)
        rows.append({"parent": parent, "parent_count": reg[parent]["count"],
                     "sub_sum": got, "match": reg[parent]["count"] == got, "subs": subs})
    return rows
