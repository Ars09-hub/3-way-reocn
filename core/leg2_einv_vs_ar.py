"""Leg 2: E-invoice (Set 3) compared to customer GL / AR (Set 2).

Matching ladder (spec 3.2), a document leaves the pipeline once matched:
  1 document number (all three families)   -> Matched on document number
  2 customer VAT + doc date + gross equal   -> Matched on customer and amount
  3 customer VAT + gross within tolerance    -> Matched on amount, date differs
  4 combination search                       -> Suggested combination / Needs review
  5 nothing                                  -> Missing in AR / Missing in e-invoice

Status precedes matching: a FAILED or NOT_SUBMITTED row is "Submitted but not
accepted" and never counts as reported (spec 1.5). Test rows are quarantined
upstream. Everything outside the window is "Out of period".
"""
from __future__ import annotations

import pandas as pd

from core import matchutil, combination


def _eligible_ar(set2: pd.DataFrame, frm, to) -> pd.DataFrame:
    """In-window AR vouchers that are genuine taxable supplies (spec 4)."""
    m = (
        set2["voucher_date"].map(lambda d: matchutil.in_window(d, frm, to))
        & set2["has_receivable"]
        & ~set2["only_excluded_offsets"]
        & set2["document_type"].isin(["INV", "CRN"])
    )
    return set2[m].copy()


def _tax_family(tax_code) -> str:
    s = str(tax_code).strip().upper()
    return s[:1] if s and s != "NAN" else "?"


def run(ei: pd.DataFrame, set2: pd.DataFrame, engine: dict, ksa: dict, frm, to) -> dict:
    elig = _eligible_ar(set2, frm, to)
    ar_by_doc: dict[str, list] = {}
    for _, r in elig.iterrows():
        ar_by_doc.setdefault(r["doc_number_n"], []).append(r)

    consumed: set[str] = set()  # grain_keys of AR vouchers already matched
    rows = []
    ambiguous = []
    suggested = []

    ei_ns = ei[~ei["is_test"]].copy()
    ei_ns["in_window"] = ei_ns["issue_date_d"].map(lambda d: matchutil.in_window(d, frm, to))

    # deterministic order: in-window first, then by value desc, then doc number
    ei_ns = ei_ns.sort_values(
        ["in_window", "total_h", "doc_number_n"], ascending=[False, False, True]
    )

    def ar_record(a):
        return {
            "ar_grain": a["grain_key"], "ar_voucher": a["voucher_number"],
            "ar_document": a["document_number"], "ar_taxable_h": int(a["ar_taxable_h"]),
            "ar_vat_h": int(a["ar_vat_h"]), "ar_gross_h": int(a["ar_gross_h"]),
            "ar_date": a["voucher_date"], "ar_doc_date": a["document_date"],
        }

    for _, e in ei_ns.iterrows():
        base = {
            "einv_no": e["document_number"], "einv_doc_n": e["doc_number_n"],
            "issue_date": e["issue_date_d"], "doc_type": e["document_type"],
            "txn_type": e["document_transaction_type"], "status": e["invoice_status"],
            "buyer_name": e["buyer_name_en"], "buyer_vat": e["buyer_vat_n"],
            "einv_taxable_h": int(e["taxable_h"]), "einv_vat_h": int(e["vat_h"]),
            "einv_total_h": int(e["total_h"]), "errors": list(e["errors_list"]),
            "row_id": e["row_id"],
        }

        if not e["in_window"]:
            rows.append({**base, "category": "Out of period", "matched_how": "",
                         "ar_grain": None})
            continue

        if not e["is_reported"]:
            # status trumps matching; still show an AR doc-number hit if present
            hit = _first_unconsumed(ar_by_doc.get(e["doc_number_n"], []), consumed)
            rec = ar_record(hit) if hit is not None else {}
            rows.append({**base, "category": "Submitted but not accepted",
                         "matched_how": "Status FAILED/NOT_SUBMITTED", **rec})
            continue

        matched, how, rec = _ladder(e, ar_by_doc, elig, consumed, engine)
        if matched is not None:
            consumed.add(rec["ar_grain"])
            diff_tax = rec["ar_taxable_h"] - base["einv_taxable_h"]
            diff_vat = rec["ar_vat_h"] - base["einv_vat_h"]
            agree = matchutil.within_tolerance(rec["ar_taxable_h"], base["einv_taxable_h"], engine) \
                and matchutil.within_tolerance(rec["ar_vat_h"], base["einv_vat_h"], engine)
            rows.append({**base, "category": "Exact match" if agree else "Amount mismatch",
                         "matched_how": how, "diff_taxable_h": diff_tax,
                         "diff_vat_h": diff_vat, **rec})
            continue

        # step 4: combination search
        combo = _combination(e, elig, consumed, engine)
        if combo and combo["found"]:
            word = combination.confidence_word(combo["agreement"], combo["n_alternatives"])
            grp = combo["indices"]
            if combo["n_alternatives"] > 1:
                rows.append({**base, "category": "Needs review",
                             "matched_how": f"{combo['n_alternatives']} combinations fit",
                             "combo": combo})
                ambiguous.append({**base, "combo": combo})
            else:
                for gk in grp:
                    consumed.add(gk)
                rows.append({**base, "category": "Suggested combination",
                             "matched_how": f"Combination of {combo['n_docs']} vouchers ({word})",
                             "combo": combo})
                suggested.append({**base, "combo": combo})
            continue

        # step 5: nothing
        rows.append({**base, "category": "Missing in AR", "matched_how": "No match",
                     "ar_grain": None})

    # AR side: eligible supplies never consumed by any e-invoice
    missing_einv = []
    for _, a in elig.iterrows():
        if a["grain_key"] not in consumed:
            missing_einv.append({
                "category": "Missing in e-invoice", "ar_grain": a["grain_key"],
                "ar_voucher": a["voucher_number"], "ar_document": a["document_number"],
                "buyer_name": a["customer_name"], "buyer_vat": a["customer_vat"],
                "ar_taxable_h": int(a["ar_taxable_h"]), "ar_vat_h": int(a["ar_vat_h"]),
                "ar_gross_h": int(a["ar_gross_h"]), "issue_date": a["voucher_date"],
                "doc_type": a["document_type"], "matched_how": "No e-invoice",
            })

    einv_rows = pd.DataFrame(rows)
    missing_rows = pd.DataFrame(missing_einv)

    order = ["Exact match", "Amount mismatch", "Missing in e-invoice", "Missing in AR",
             "Submitted but not accepted", "Suggested combination", "Needs review", "Out of period"]
    counts = {}
    for c in order:
        n = 0
        if len(einv_rows):
            n += int((einv_rows["category"] == c).sum())
        if c == "Missing in e-invoice":
            n = len(missing_rows)
        counts[c] = n

    return {
        "einv_rows": einv_rows, "missing_rows": missing_rows,
        "counts": counts, "order": order,
        "ambiguous": ambiguous, "suggested": suggested,
        "eligible_ar": elig, "consumed": consumed,
    }


def _first_unconsumed(cands, consumed):
    for a in cands:
        if a["grain_key"] not in consumed:
            return a
    return None


def _ladder(e, ar_by_doc, elig, consumed, engine):
    # step 1: document number across all families (already normalised)
    hit = _first_unconsumed(ar_by_doc.get(e["doc_number_n"], []), consumed)
    if hit is not None:
        return hit, "Matched on document number", _rec(hit)

    # steps 2 and 3: customer VAT + gross (+/- date)
    if e["buyer_vat_n"]:
        cand = elig[(elig["customer_vat"] == e["buyer_vat_n"])
                    & (~elig["grain_key"].isin(consumed))]
        # step 2: gross equal and document date equal
        for _, a in cand.iterrows():
            if matchutil.within_tolerance(int(a["ar_gross_h"]), int(e["total_h"]), engine) \
               and _same_date(a["document_date"], e["issue_date_d"]):
                return a, "Matched on customer and amount", _rec(a)
        # step 3: gross within tolerance, date within window
        for _, a in cand.iterrows():
            if matchutil.within_tolerance(int(a["ar_gross_h"]), int(e["total_h"]), engine):
                return a, "Matched on amount, date differs", _rec(a)
    return None, None, None


def _combination(e, elig, consumed, engine):
    if not e["buyer_vat_n"]:
        return None
    window = engine["combination"]["date_window_days"]
    lo = e["issue_date_d"] - pd.Timedelta(days=window)
    hi = e["issue_date_d"] + pd.Timedelta(days=window)
    cand = elig[(elig["customer_vat"] == e["buyer_vat_n"])
                & (~elig["grain_key"].isin(consumed))
                & (elig["voucher_date"].between(lo, hi))]
    if len(cand) < 2:
        return None
    candidates = [{
        "ref": a["grain_key"], "vat_h": int(a["ar_vat_h"]), "taxable_h": int(a["ar_taxable_h"]),
        "gross_h": int(a["ar_gross_h"]), "sign": _sign(int(a["ar_taxable_h"])),
        "tax_family": _tax_family(a["tax_code"]),
    } for _, a in cand.iterrows()]
    target = {
        "vat_h": int(e["vat_h"]), "taxable_h": int(e["taxable_h"]), "gross_h": int(e["total_h"]),
        "sign": _sign(int(e["taxable_h"])), "tax_family": _tax_family_einv(e),
    }
    return combination.search(target, candidates, engine)


def _rec(a):
    return {
        "ar_grain": a["grain_key"], "ar_voucher": a["voucher_number"],
        "ar_document": a["document_number"], "ar_taxable_h": int(a["ar_taxable_h"]),
        "ar_vat_h": int(a["ar_vat_h"]), "ar_gross_h": int(a["ar_gross_h"]),
        "ar_date": a["voucher_date"], "ar_doc_date": a["document_date"],
    }


def _same_date(a, b):
    if pd.isna(a) or pd.isna(b):
        return False
    return pd.Timestamp(a).normalize() == pd.Timestamp(b).normalize()


def _sign(v):
    return 0 if v == 0 else (1 if v > 0 else -1)


def _tax_family_einv(e):
    """Infer the e-invoice tax treatment from its VAT breakdown columns."""
    def val(col):
        try:
            return float(e[col]) if pd.notna(e[col]) else 0.0
        except (KeyError, TypeError, ValueError):
            return 0.0
    if val("vat_standard_rated") > 0 or int(e["vat_h"]) != 0:
        return "S"
    if val("vat_zero_rated") > 0:
        return "Z"
    if val("vat_exempted") > 0:
        return "E"
    if val("vat_out_of_scope") > 0:
        return "O"
    return "S"
