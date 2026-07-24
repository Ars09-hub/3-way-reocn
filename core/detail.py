"""Document detail datasets for the seventh page (addendum sections 3, 4).

Produces the raw rows of all three datasets in native form, each carrying its
document key, the recon bucket assigned to it, and (GL) a derived account class.
Column specs give plain-English labels with the source column as a tooltip, and
columns that are empty across the whole extract are dropped.
"""
from __future__ import annotations

import pandas as pd

from core import normalize as nz

# -- column specs (label, source or @derived) -------------------------------

GL_ESSENTIAL = [
    ("Voucher number", "voucher_number"), ("Voucher date", "voucher_date"),
    ("Document date", "document_date"), ("Document reference", "document_reference"),
    ("GL code", "gl_code"), ("GL description", "gl_description"),
    ("Account class", "@account_class"), ("Debit", "debit_amount"),
    ("Credit", "credit_amount"), ("Amount (local)", "@amount_local"),
    ("Currency", "local_currency"), ("Customer ID", "customer_id"),
    ("Customer TIN", "customer_vat"), ("Status", "@status"),
]
GL_ALL_ADD = ["entry_id", "line_id", "company_code", "company_name", "fiscal_year",
              "sales_or_purchase", "amount_in_doc_currency", "doc_currency", "exchange_rate",
              "chart_of_account_id", "cost_center", "is_reversed", "created_by",
              "debit_credit_indicator", "source_system"]

AR_ESSENTIAL = [
    ("Voucher number", "voucher_number"), ("Document number", "document_number"),
    ("Document type", "document_type"), ("Voucher date", "voucher_date"),
    ("Document date", "document_date"), ("Customer name", "customer_name"),
    ("Customer TIN", "customer_vat_number"), ("GL classification", "gl_classification"),
    ("GL code", "gl_code_combination"), ("GL description", "gl_description"),
    ("Taxable value", "doc_taxable_amount"), ("Output VAT", "doc_vat_output"),
    ("Total with tax", "doc_total_tax"), ("Tax code", "tax_code"),
    ("Tax rate", "tax_rate"), ("Tax group", "tax_group"),
    ("Currency", "doc_currency"), ("Status", "@status"),
]
AR_ALL_ADD = ["line_id", "company_code", "company_vat_number", "company_name", "entity_name",
              "fiscal_year", "account_type", "debit_amount", "credit_amount",
              "amount_in_local_currency", "local_currency", "amount_in_doc_currency",
              "exchange_rate", "customer_id", "debit_credit_indicator", "is_reversed",
              "erp_transaction_name", "created_by", "source_system"]

EI_ESSENTIAL = [
    ("E-invoice number", "document_number"), ("Issue date", "document_issue_date"),
    ("Document type", "document_type"), ("Transaction type", "document_transaction_type"),
    ("Status", "@invoice_status"), ("Buyer name", "buyer_name_en"),
    ("Buyer TIN", "@buyer_tin"), ("Seller TIN", "seller_vat"),
    ("Taxable value", "total_invoice_amount_without_vat"), ("VAT", "total_vat_amount_sar"),
    ("Total with VAT", "invoice_total_with_vat"), ("Standard rated", "vat_standard_rated"),
    ("Zero rated", "vat_zero_rated"), ("Exempt", "vat_exempted"),
    ("Out of scope", "vat_out_of_scope"), ("Original invoice reference", "@billing_ref"),
    ("Validation errors", "@errors"), ("Recon status", "@status"),
]
EI_ALL_ADD = ["row_id", "branch", "device_name", "method_of_generation", "qr_code_status",
              "seller_name", "seller_other_id_type", "seller_other_id_crn",
              "buyer_other_id_type", "buyer_other_id_crn", "total_allowance_amount",
              "total_vat_amount_doc_currency", "pre_paid_amount", "rounding_amount",
              "amount_due_for_payment", "credit_debit_note_reason", "document_attempted_date",
              "document_attempted_time", "document_issue_time", "error_source", "warnings",
              "is_modified", "document_currency", "created_at"]

NUMERIC_LABELS = {"Debit", "Credit", "Amount (local)", "Taxable value", "Output VAT",
                  "Total with tax", "VAT", "Total with VAT", "Standard rated", "Zero rated",
                  "Exempt", "Out of scope", "Tax rate", "amount_in_doc_currency", "exchange_rate",
                  "amount_in_local_currency", "debit_amount", "credit_amount",
                  "total_allowance_amount", "total_vat_amount_doc_currency", "pre_paid_amount",
                  "rounding_amount", "amount_due_for_payment"}

ACCOUNT_CLASS_LABEL = {"REVENUE": "Revenue", "TAX_OUTPUT": "Output tax",
                       "CONTRA_REVENUE": "Contra revenue", "CUSTOMER_CONTROL": "Customer control",
                       "OTHER_INCOME": "Other income", "UNCLASSIFIED": "Unclassified"}


def _in_window(d, frm, to):
    return not pd.isna(d) and frm <= d <= to


def build(R: dict) -> dict:
    frm, to = R["period"]["from"], R["period"]["to"]
    gl_status = _key_status(R, "gl_keys")
    ar_status = _key_status(R, "ar_keys")
    ei_status = _ei_status(R)

    gl = _gl_rows(R["gla"], gl_status, frm, to)
    ar = _ar_rows(R["ara"], ar_status, frm, to)
    ei = _ei_rows(R["ei_raw"], ei_status)
    return {"gl": gl, "ar": ar, "ei": ei}


# -- status maps ------------------------------------------------------------

def _key_status(R, key_field: str) -> dict:
    """Map each gl_key / ar_key to the three-way status of its event."""
    m = {}
    for _, e in R["threeway"]["events"].iterrows():
        for k in (e.get(key_field) or []):
            m[k] = e["status"]
    return m


def _ei_status(R) -> dict:
    """Map each e-invoice row_id to its recon bucket."""
    m = {}
    er = R["leg2"]["einv_rows"]
    if len(er):
        for _, r in er.iterrows():
            if r.get("ei_key") is not None and not pd.isna(r.get("ei_key")):
                m[r["ei_key"]] = r["category"]
    return m


# -- row builders -----------------------------------------------------------

def _gl_rows(gla, status_map, frm, to):
    def status(row):
        s = status_map.get(row["gl_key"])
        if s:
            return s
        if pd.notna(row["excluded_reason"]):
            return "Out of scope by design"
        if not _in_window(row["voucher_date_d"], frm, to):
            return "Out of period"
        return "Not in reconciliation scope"

    def account_class(row):
        if pd.notna(row["excluded_reason"]):
            return "Excluded"
        return ACCOUNT_CLASS_LABEL.get(row["account_class"], row["account_class"])

    derived = {
        "@account_class": account_class,
        "@amount_local": lambda r: nz.halalas_to_str(int(r["signed_local"])),
        "@status": status,
    }
    return _dataset(gla, GL_ESSENTIAL, GL_ALL_ADD, derived, "gl_key")


def _ar_rows(ara, status_map, frm, to):
    def status(row):
        s = status_map.get(row["ar_key"])
        if s:
            return s
        if pd.notna(row["excluded_reason"]):
            return "Out of scope by design"
        if pd.isna(row["gl_classification"]):
            return "Unclassified"
        if not _in_window(row["voucher_date_d"], frm, to):
            return "Out of period"
        return "Not in reconciliation scope"

    derived = {"@status": status}
    ds = _dataset(ara, AR_ESSENTIAL, AR_ALL_ADD, derived, "ar_key")
    ds["group_field"] = "ar_key"          # for line-vs-voucher grouping
    ds["doclevel_labels"] = ["Taxable value", "Output VAT", "Total with tax"]
    return ds


def _ei_rows(ei_raw, status_map):
    def status(row):
        if row["is_test"]:
            return "Test data quarantined"
        s = status_map.get(row["ei_key"])
        if s:
            return s
        # a raw row not in the deduped result is a superseded resubmission attempt
        return "Superseded attempt"

    derived = {
        "@invoice_status": lambda r: r["invoice_status"],
        "@buyer_tin": lambda r: nz.clean_vat(r["buyer_vat"]),
        "@billing_ref": lambda r: ", ".join(nz.parse_string_array(r["billing_reference_id"])),
        "@errors": lambda r: nz.parse_string_array(r["errors"]),
        "@status": status,
    }
    ds = _dataset(ei_raw, EI_ESSENTIAL, EI_ALL_ADD, derived, "ei_key")
    ds["status_badge_label"] = "Status"       # invoice_status renders as a badge
    ds["errors_label"] = "Validation errors"
    return ds


def _dataset(df, essential, all_add, derived, key_col):
    # drop source columns that are empty across the whole extract
    def empty(col):
        return col not in df.columns or df[col].isna().all() or \
            (df[col].astype(str).str.strip().replace("nan", "").eq("").all())

    ess = [(lbl, src) for lbl, src in essential if src.startswith("@") or not empty(src)]
    dropped = [src for lbl, src in essential if not src.startswith("@") and empty(src)]
    all_cols = [c for c in all_add if not empty(c)]
    dropped += [c for c in all_add if empty(c)]

    ess_labels = [lbl for lbl, _ in ess]
    all_labels = ess_labels + all_cols
    tooltips = {lbl: (src if not src.startswith("@") else "derived") for lbl, src in ess}
    tooltips.update({c: c for c in all_cols})

    lid_col = "row_id" if key_col == "ei_key" else "line_id"
    rows = []
    for _, r in df.iterrows():
        rec = {"_key": str(r[key_col]), "_lid": str(r[lid_col])}
        for lbl, src in ess:
            rec[lbl] = _fmt(derived[src](r) if src.startswith("@") else r.get(src), lbl)
        for c in all_cols:
            rec[c] = _fmt(r.get(c), c)
        rec["_status"] = derived["@status"](r) if "@status" in derived else ""
        if "@errors" in derived:
            rec["_errors"] = derived["@errors"](r)
            rec["_invoice_status"] = str(r["invoice_status"])
        rows.append(rec)

    return {
        "essential": ess_labels, "all": all_labels, "tooltips": tooltips,
        "numeric": [lbl for lbl in all_labels if lbl in NUMERIC_LABELS],
        "rows": rows, "dropped": dropped, "total": len(df),
    }


def _fmt(v, label):
    if isinstance(v, list):
        return v
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if label in NUMERIC_LABELS:
        try:
            f = float(v)
            return f"{f:,.2f}"
        except (TypeError, ValueError):
            return str(v)
    s = str(v)
    return s[:-2] if s.endswith(".0") and s[:-2].isdigit() else s
