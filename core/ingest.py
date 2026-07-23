"""Read the three xlsx files and apply the cleaning rules (spec 2.1, 2.2, 1.5).

Nothing is dropped here. Test data is flagged, e-invoice resubmissions are
deduplicated to the latest attempt with the history retained.
"""
from __future__ import annotations

import re

import pandas as pd

from core import normalize as nz

SHEET = "Data"


def _read(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_gl(path: str) -> pd.DataFrame:
    df = _read(path)
    df["gl_code_n"] = df["gl_code"].map(nz.clean_gl_code)
    df["voucher_number_s"] = df["voucher_number"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["voucher_date_d"] = pd.to_datetime(df["voucher_date"], errors="coerce")
    df["document_date_d"] = pd.to_datetime(df["document_date"], errors="coerce")
    df["customer_vat_n"] = df["customer_vat"].map(nz.clean_vat)
    df["grain_key"] = _grain_key(df)
    return df


def load_ar(path: str) -> pd.DataFrame:
    df = _read(path)
    df["gl_code_n"] = df["gl_code_combination"].map(nz.clean_gl_code)
    df["voucher_number_s"] = df["voucher_number"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["voucher_date_d"] = pd.to_datetime(df["voucher_date"], errors="coerce")
    df["document_date_d"] = pd.to_datetime(df["document_date"], errors="coerce")
    df["doc_number_n"] = df["document_number"].map(nz.normalize_doc_number)
    df["is_credit_note_num"] = df["document_number"].map(nz.is_credit_note_number)
    df["customer_vat_n"] = df["customer_vat_number"].map(nz.clean_vat)
    df["doc_taxable_h"] = df["doc_taxable_amount"].map(nz.to_halalas)
    df["doc_vat_h"] = df["doc_vat_output"].map(nz.to_halalas)
    df["doc_total_tax_h"] = df["doc_total_tax"].map(nz.to_halalas)
    df["amount_local_h"] = df["amount_in_local_currency"].map(nz.to_halalas)
    df["grain_key"] = _grain_key(df)
    return df


def load_einvoice(path: str, ksa: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (deduped e-invoice frame, resubmission history frame).

    Duplicate document numbers are deduplicated to the latest attempt by
    document_attempted_date; every attempt is preserved in the history frame.
    """
    df = _read(path)
    df["doc_number_n"] = df["document_number"].map(nz.normalize_doc_number)
    df["buyer_vat_n"] = df["buyer_vat"].map(nz.clean_vat)
    df["seller_vat_n"] = df["seller_vat"].map(nz.clean_vat)
    df["issue_date_d"] = pd.to_datetime(df["document_issue_date"], errors="coerce")
    df["attempted_date_d"] = pd.to_datetime(df["document_attempted_date"], errors="coerce")
    df["taxable_h"] = df["total_invoice_amount_without_vat"].map(nz.to_halalas)
    df["vat_h"] = df["total_vat_amount_sar"].map(nz.to_halalas)
    df["total_h"] = df["invoice_total_with_vat"].map(nz.to_halalas)
    df["currency_n"] = df["document_currency"].map(lambda v: nz.map_currency(v, ksa["currency_aliases"]))
    df["errors_list"] = df["errors"].map(nz.parse_string_array)
    df["warnings_list"] = df["warnings"].map(nz.parse_string_array)
    df["billing_ref_list"] = df["billing_reference_id"].map(nz.parse_string_array)

    test_re = re.compile(ksa["test_document_pattern"], re.IGNORECASE)
    df["is_test"] = df["document_number"].astype(str).map(lambda s: bool(test_re.match(s.strip())))

    not_reported = set(ksa["not_reported_statuses"])
    df["is_reported"] = ~df["invoice_status"].isin(not_reported)

    # resubmission handling: the SAME raw document number attempted more than once
    # (spec 1.5). Dedupe on the raw number, never the normalised one, so a credit
    # note is not merged onto its parent invoice. Keep the latest attempt.
    df["_order"] = range(len(df))
    df["document_number_raw"] = df["document_number"].astype(str).str.strip()
    dup_mask = df.duplicated("document_number_raw", keep=False)
    history = df[dup_mask].copy()

    df_sorted = df.sort_values(["document_number_raw", "attempted_date_d", "_order"], na_position="first")
    deduped = df_sorted.drop_duplicates("document_number_raw", keep="last")
    deduped = deduped.sort_values("_order").reset_index(drop=True)
    history = history.sort_values(["document_number_raw", "attempted_date_d"]).reset_index(drop=True)
    return deduped, history


def _grain_key(df: pd.DataFrame) -> pd.Series:
    vd = pd.to_datetime(df["voucher_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return (
        df["company_code"].astype(str) + "|"
        + df["fiscal_year"].astype(str) + "|"
        + df["voucher_number"].astype(str).str.replace(r"\.0$", "", regex=True) + "|"
        + vd.astype(str)
    )
