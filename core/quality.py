"""Data quality page (spec page 6) and the open decisions (spec 9).

Everything that would otherwise masquerade as a reconciliation break: period
coverage, out-of-period documents, test data, duplicate submissions, invalid and
missing VAT numbers, null classification, VAT-without-revenue vouchers, excluded
accounts, currency mix, and the GL-vs-sales-register revenue cross-check.
"""
from __future__ import annotations

import pandas as pd

from core import normalize as nz, sets as sets_mod


def build(R: dict) -> dict:
    gl, ar, ei, ei_hist = R["gl"], R["ar"], R["ei"], R["ei_hist"]
    gla, ara = R["gla"], R["ara"]
    ksa = R["cfg"]["ksa"]
    frm, to = R["period"]["from"], R["period"]["to"]

    checks = []

    def add(name, rows, value_h, effect, examples):
        checks.append({"check": name, "rows": int(rows), "value_h": int(value_h),
                       "effect": effect, "examples": examples})

    # out of period (by the configured erp/e-invoice date fields)
    def oop(df, field):
        d = df[field]
        return df[(d < frm) | (d > to)]
    gl_oop = oop(gl, "voucher_date_d")
    ar_oop = oop(ar, "voucher_date_d")
    ei_oop = oop(ei[~ei["is_test"]], "issue_date_d")
    add("Out of period", len(gl_oop) + len(ar_oop) + len(ei_oop),
        pd.to_numeric(ar_oop["doc_taxable_amount"], errors="coerce").abs().fillna(0).sum() * 100,
        "Excluded from all exposure figures, listed separately",
        f"{len(ei_oop)} e-invoices, {len(ar_oop)} AR rows, {len(gl_oop)} GL rows outside the window")

    # test data quarantined
    test = ei[ei["is_test"]]
    add("Test data quarantined", len(test), int(test["taxable_h"].sum()),
        "Never matched, appears only here",
        ", ".join(sorted(set(test["buyer_name_en"].dropna().astype(str)))[:1]) or "test-* document numbers")

    # duplicate submissions
    dup_docs = sorted(ei_hist["document_number_raw"].unique()) if len(ei_hist) else []
    add("Duplicate submissions", ei_hist["document_number_raw"].nunique() if len(ei_hist) else 0,
        0, "Deduplicated to the latest attempt, history retained",
        ", ".join(dup_docs))

    # invalid VAT numbers
    allv = pd.concat([ar["customer_vat_n"], ei["buyer_vat_n"]])
    allv = allv[allv != ""]
    invalid = sorted({v for v in allv if not nz.is_valid_tin(v, ksa["tin"])})
    inv_rows = int(allv.isin(invalid).sum())
    add("Invalid VAT numbers", inv_rows, 0, "Flagged as invalid master data, not used for matching",
        ", ".join(invalid))

    # missing VAT numbers
    miss_ar = int((ar["customer_vat_n"] == "").sum())
    miss_ei = int((ei["buyer_vat_n"] == "").sum())
    add("Missing VAT numbers", miss_ar + miss_ei, 0, "Blank on the customer record",
        f"{miss_ar} of {len(ar)} sales rows, {miss_ei} of {len(ei)} e-invoice rows")

    # null gl_classification
    null_cls = ar[ar["gl_classification"].isna()]
    add("Unclassified rows", len(null_cls), 0, "Null gl_classification, routed to review",
        f"{len(null_cls)} sales register rows")

    # VAT output but no revenue line (spec 9)
    vat_no_rev = _vat_without_revenue(gla)
    add("VAT output with no revenue line", len(vat_no_rev), 0,
        "Tax-only adjustments or incomplete postings, review",
        ", ".join(str(v) for v in vat_no_rev[:8]))

    # excluded accounts
    gex = sets_mod.excluded_bucket(gla, "amount_in_local_currency")
    aex = sets_mod.excluded_bucket(ara, "amount_in_local_currency")
    add("Excluded accounts", gex["rows"] + aex["rows"], int((gex["value"] + aex["value"]) * 100),
        "Out of scope by design, never a missing match",
        f"GL {gex['rows']} rows, AR {aex['rows']} rows (interest, forex, intercompany, deferred)")

    # currency mix
    usd = ar[ar["doc_currency"].astype(str).str.upper() == "USD"]
    rates = sorted(set(pd.to_numeric(usd["exchange_rate"], errors="coerce").dropna()))
    add("Currency mix", len(usd), 0, "USD converted at document rate before comparison",
        "rates " + ", ".join(str(r) for r in rates))

    # GL vs sales-register revenue cross-check (spec 0)
    crosscheck = _revenue_crosscheck(R["set1"], ara, R["engine"] if "engine" in R else R["cfg"]["engine"])
    add("GL vs sales-register revenue disagreement", len(crosscheck), 0,
        "Set 1 comes from the GL register; disagreements are surfaced not silently resolved",
        ", ".join(str(v) for v in crosscheck[:8]) if crosscheck else "none")

    # suggested account additions (self-correcting output, spec 4)
    suggested_accounts = _suggested_account_additions(R)

    return {
        "checks": checks,
        "window": {"from": frm, "to": to, "ranges": R["period"]["ranges"]},
        "duplicate_history": ei_hist,
        "test_rows": test,
        "vat_no_revenue": vat_no_rev,
        "invalid_vat": invalid,
        "suggested_accounts": suggested_accounts,
        "excluded": {"gl": gex, "ar": aex},
        "open_decisions": _open_decisions(ar),
    }


def _vat_without_revenue(gla: pd.DataFrame) -> list:
    out = []
    inscope = gla[gla["excluded_reason"].isna()]
    for gk, g in inscope.groupby("grain_key", sort=True):
        has_tax = (g["account_class"] == "TAX_OUTPUT").any()
        has_rev = (g["account_class"] == "REVENUE").any()
        tax_val = g[g["account_class"] == "TAX_OUTPUT"]["signed_local"].abs().sum()
        if has_tax and not has_rev and tax_val > 0:
            out.append(g.iloc[0]["voucher_number_n"])
    return out


def _revenue_crosscheck(set1: pd.DataFrame, ara: pd.DataFrame, engine: dict) -> list:
    """Compare GL-register revenue (Set 1) with sales-register REVENUE lines per grain."""
    from core import matchutil
    ar_rev = ara[ara["account_class"] == "REVENUE"].copy()
    ar_rev["signed"] = ((pd.to_numeric(ar_rev["credit_amount"], errors="coerce").fillna(0)
                         - pd.to_numeric(ar_rev["debit_amount"], errors="coerce").fillna(0)) * 100).round()
    ar_by_grain = ar_rev.groupby("grain_key")["signed"].sum().to_dict()
    out = []
    for _, r in set1.iterrows():
        gk = r["grain_key"]
        if gk in ar_by_grain:
            if not matchutil.within_tolerance(int(r["gl_taxable_h"]), int(ar_by_grain[gk]), engine):
                out.append(r["voucher_number"])
    return out


def _suggested_account_additions(R: dict) -> pd.DataFrame:
    """GL codes behind 'Billed but no revenue posted', ranked by value (spec 4)."""
    tw = R["threeway"]["events"]
    billed = tw[tw["status"] == "Billed but no revenue posted"]
    ara = R["ara"]
    grains = set(billed["grain_key"].dropna())
    lines = ara[ara["grain_key"].isin(grains) & (ara["account_class"] == "REVENUE")]
    if not len(lines):
        return pd.DataFrame(columns=["gl_code", "gl_description", "value_h", "vouchers"])
    lines = lines.assign(_v=(pd.to_numeric(lines["credit_amount"], errors="coerce").fillna(0)
                             - pd.to_numeric(lines["debit_amount"], errors="coerce").fillna(0)).abs() * 100)
    agg = (lines.groupby(["gl_code_n", "gl_description"])
           .agg(value_h=("_v", "sum"), vouchers=("grain_key", "nunique"))
           .reset_index().rename(columns={"gl_code_n": "gl_code"}))
    return agg.sort_values("value_h", ascending=False).reset_index(drop=True)


def _open_decisions(ar: pd.DataFrame) -> list:
    jv = int((ar["document_type"] == "JV").sum())
    o_rows = int((ar["tax_code"].astype(str).str.upper() == "O").sum())
    return [
        {"id": "jv_supplies", "text": f"Which of the {jv} JV rows in the sales register are taxable supplies and which are adjustments."},
        {"id": "tax_code_o", "text": f"Whether tax code O (out of scope), on {o_rows} of {len(ar)} rows with a net negative taxable value, is correct or a mapping problem."},
        {"id": "external_numbers", "text": "Whether documents 58008, 59008, 67008, 68013 come from a separate billing system and need their own number family."},
        {"id": "vat_only", "text": "Whether the vouchers carrying VAT output with no revenue line are tax-only adjustments or incomplete postings."},
        {"id": "period_basis", "text": "Whether the reconciled period should follow document date or accounting date, given the two differ across these files."},
    ]
