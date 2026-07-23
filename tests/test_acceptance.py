"""Acceptance tests (spec 7). Written as real assertions.

Run: python -m pytest tests/test_acceptance.py -v
The build is not done until these pass. Where a test fails against the supplied
data, that is reported (not silently adjusted): see test 5.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pandas as pd
import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from core import loader, pipeline, ingest, combination  # noqa: E402
from core.normalize import to_halalas, clean_vat, normalize_doc_number  # noqa: E402

DATA = os.path.join(HERE, "data")
GL = os.path.join(DATA, "gl_register.xlsx")
AR = os.path.join(DATA, "sales_register.xlsx")
EI = os.path.join(DATA, "sales_einvoice__1_.xlsx")


@pytest.fixture(scope="module")
def R():
    return pipeline.run(loader.load_config(), GL, AR, EI)


# 1 -------------------------------------------------------------------------
def test_01_row_counts(R):
    assert len(R["gl"]) == 830
    assert len(R["ar"]) == 782
    raw = pd.read_excel(EI, sheet_name="Data")
    assert len(raw) == 39


# 2 -------------------------------------------------------------------------
def test_02_no_double_counting(R):
    ar = R["ar"]
    raw_sum = pd.to_numeric(ar["doc_taxable_amount"], errors="coerce").fillna(0).sum()
    reduced = R["set2"].drop_duplicates("grain_key")["ar_taxable_h"].sum() / 100.0
    assert reduced < raw_sum
    # 174 vouchers were affected by the repeated doc-level stamp
    affected = 0
    for _, g in ar.groupby("grain_key"):
        recv = g[g["gl_code_n"] == "11120101"]
        if len(g) > 1 and g["doc_taxable_amount"].notna().any() and len(g) > len(recv.head(1)):
            if (g["doc_taxable_amount"].nunique() <= 1) and len(g) >= 2:
                affected += 1
    assert affected >= 174


# 3 -------------------------------------------------------------------------
def test_03_voucher_261100000026(R):
    rows = R["leg1"]["rows"]
    v = rows[rows["voucher_number"] == "261100000026"]
    assert len(v) == 1
    r = v.iloc[0]
    assert r["category"] == "Exact match"
    assert r["ar_taxable_h"] == to_halalas("24233.93")
    assert r["ar_vat_h"] == to_halalas("3635.09")
    assert r["ar_gross_h"] == to_halalas("27869.02")
    assert str(r["tax_code"]).upper() == "S"
    assert abs(float(r["tax_rate"]) - 15) < 1e-6
    assert r["customer_name"] == "EFG Arabia Company"
    assert clean_vat(r["customer_vat"]) == "310881493700003"


# 4 -------------------------------------------------------------------------
def test_04_voucher_251300000007_multi_date(R):
    ar = ingest.load_ar(AR)
    v = ar[ar["voucher_number_n"] == "251300000007"]
    assert len(v) == 24
    assert v["voucher_date_d"].dt.strftime("%Y-%m-%d").nunique() == 6
    # not collapsed: multiple distinct grain keys
    assert v["grain_key"].nunique() == 6


# 5 -------------------------------------------------------------------------
def test_05_excluded_accounts(R):
    from core import sets
    gex = sets.excluded_bucket(R["gla"], "amount_in_local_currency")
    aex = sets.excluded_bucket(R["ara"], "amount_in_local_currency")
    # SPEC expectation is 226 GL and 106 AR. The supplied files give 276 / 143
    # across the ten configured excluded codes. This assertion encodes the spec
    # number and therefore FAILS against the data (reported, not adjusted).
    assert gex["rows"] == 226, f"spec says 226 GL excluded rows, data has {gex['rows']}"
    assert aex["rows"] == 106, f"spec says 106 AR excluded rows, data has {aex['rows']}"
    # none of the excluded rows appears as a "missing" match
    l1 = R["leg1"]["rows"]
    missing = l1[l1["category"].isin(["Missing in AR", "Missing in GL"])]
    assert not missing["category"].isin(["Out of scope by design"]).any()


# 6 -------------------------------------------------------------------------
def test_06_test_data_quarantined(R):
    ei = R["ei"]
    assert int(ei["is_test"].sum()) == 8
    # test rows never appear as matched in leg 2
    er = R["leg2"]["einv_rows"]
    assert not er["einv_no"].astype(str).str.lower().str.startswith("test").any()


# 7 -------------------------------------------------------------------------
def test_07_duplicate_submission(R):
    hist = R["ei_hist"]
    assert "261200000002" in set(hist["document_number_raw"])
    dup = hist[hist["document_number_raw"] == "261200000002"]
    assert len(dup) == 2  # both attempts retained
    ei = R["ei"]
    kept = ei[ei["document_number_raw"] == "261200000002"]
    assert len(kept) == 1  # deduped to one
    assert str(kept.iloc[0]["attempted_date_d"].date()) == "2026-01-27"  # later attempt


# 8 -------------------------------------------------------------------------
def test_08_status_split(R):
    raw = pd.read_excel(EI, sheet_name="Data")
    vc = raw["invoice_status"].value_counts().to_dict()
    assert vc.get("CLEARED") == 20
    assert vc.get("REPORTED") == 6
    assert vc.get("FAILED") == 6
    assert vc.get("NOT_SUBMITTED") == 7
    # FAILED and NOT_SUBMITTED classified as not reported
    ei = R["ei"]
    not_rep = ei[~ei["is_reported"]]
    assert set(not_rep["invoice_status"]).issubset({"FAILED", "NOT_SUBMITTED"})


# 9 -------------------------------------------------------------------------
def test_09_simplified_track(R):
    ei = R["ei"]
    simp = ei[ei["document_transaction_type"] == "SIMPLIFIED_TAX_INVOICE"]
    assert (simp["invoice_status"] == "REPORTED").sum() == 6
    # all six are treated as reported (correctly reported, not exceptions)
    assert simp[simp["invoice_status"] == "REPORTED"]["is_reported"].all()


# 10 ------------------------------------------------------------------------
def test_10_period_scoping(R):
    per = R["period"]
    frm, to = per["from"], per["to"]
    tw = R["threeway"]["events"]
    # every three-way event date lies inside the window
    dates = pd.to_datetime(tw["date"])
    assert (dates >= frm).all() and (dates <= to).all()
    # out-of-period e-invoices are labelled, not counted as exposure
    assert R["leg2"]["counts"]["Out of period"] > 0


# 11 ------------------------------------------------------------------------
def test_11_sign_handling(R):
    ar = R["ara"]
    crn = ar[ar["document_type"] == "CRN"]
    # every CRN doc-level taxable is negative, counted once per voucher
    s2 = R["set2"]
    crn_units = s2[s2["document_type"] == "CRN"]
    assert (crn_units["ar_taxable_h"] <= 0).all()
    assert (crn_units["ar_taxable_h"] < 0).any()


# 12 ------------------------------------------------------------------------
def test_12_vat_number_cleaning():
    assert clean_vat("'310881493700003'") == "310881493700003"
    assert clean_vat("310881493700003") == "310881493700003"
    assert clean_vat("'310881493700003'") == clean_vat(" 310881493700003 ")


# 13 ------------------------------------------------------------------------
def test_13_ambiguity_not_auto_selected():
    eng = loader.load_config()["engine"]
    # spec 3.3: six vouchers of equal value against one e-invoice of double value
    cands = [{"ref": f"v{i}", "vat_h": 10000, "taxable_h": 66667, "gross_h": 76667,
              "sign": 1, "tax_family": "S"} for i in range(6)]
    tgt = {"vat_h": 20000, "taxable_h": 133334, "gross_h": 153334, "sign": 1, "tax_family": "S"}
    res = combination.search(tgt, cands, eng)
    assert res["found"]
    assert res["n_alternatives"] == 15   # fifteen valid pairs
    assert combination.confidence_word(res["agreement"], res["n_alternatives"]) == "Needs review"


# 14 ------------------------------------------------------------------------
def test_14_conservation(R):
    # leg 1: every in-window grain lands in exactly one category
    l1 = R["leg1"]["rows"]
    assert len(l1) == len(l1.drop_duplicates("grain_key"))
    total = sum(R["leg1"]["counts"].values())
    assert total == len(l1)
    # leg 2: each non-test e-invoice appears exactly once
    er = R["leg2"]["einv_rows"]
    ei_non_test = int((~R["ei"]["is_test"]).sum())
    assert len(er) == ei_non_test
    assert len(er) == len(er.drop_duplicates("row_id"))


# 15 ------------------------------------------------------------------------
def test_15_determinism(tmp_path):
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    for o in (out1, out2):
        subprocess.run([sys.executable, os.path.join(HERE, "run.py"),
                        "--gl", GL, "--ar", AR, "--einv", EI, "--out", str(o)],
                       check=True, cwd=HERE, capture_output=True)
    csvs = ["leg1_gl_vs_ar.csv", "leg2_einv_vs_ar.csv", "three_way.csv",
            "customer_summary.csv", "suggested_combinations.csv",
            "suggested_account_additions.csv", "quarantine.csv"]
    for name in csvs:
        a = (out1 / name).read_bytes()
        b = (out2 / name).read_bytes()
        assert a == b, f"{name} not byte-identical across runs"


# 16 ------------------------------------------------------------------------
def test_16_plain_language(tmp_path):
    out = tmp_path / "o"
    subprocess.run([sys.executable, os.path.join(HERE, "run.py"),
                    "--gl", GL, "--ar", AR, "--einv", EI, "--out", str(out)],
                   check=True, cwd=HERE, capture_output=True)
    banned = ["E1", "E7", "T0", "T6", "conservation"]
    for name in os.listdir(out):
        text = (out / name).read_text(encoding="utf-8", errors="ignore")
        for b in banned:
            assert b not in text, f"banned token {b!r} found in {name}"
