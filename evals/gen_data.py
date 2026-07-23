"""Deterministic synthetic dataset generator (spec §19).

Produces data/b2b and data/b2c with gl.csv, ar.csv, einv.csv and
ground_truth.csv. Every mandatory scenario (1..26) is present and labelled.
Filler clean 1:1:1 documents pad each plane past the 400-document minimum.

Amounts use MYR (minor exponent 2) with an 8% standard rate (SST-S), so
tax=500 => net=6250, gross=6750 and tax=1000 => net=12500, gross=13500.
"""
from __future__ import annotations

import csv
import os

REV = "400000"
TAXACC = "230000"
CUST = "140000"
BANK = "110000"
WHT = "231000"
ROUND = "880000"
DISPOSAL_UNMAPPED = "490000"     # gain on disposal, outside profile ranges -> E5
OTHERINC_UNMAPPED = "450000"     # notice-pay recovery, outside ranges -> E5
STD = "SST-S"

GL_COLS = ["BUKRS", "BELNR", "GJAHR", "BUZEI", "HKONT", "BLART", "BLDAT", "BUDAT",
           "WAERS", "KURSF", "DMBTR_SIGNED", "MWSKZ", "KUNNR", "STCEG", "NAME1", "PRCTR"]
AR_COLS = ["BUKRS", "VBELN", "AWKEY", "XBLNR", "GJAHR", "FKART", "FKDAT", "BUDAT",
           "WAERS", "KURSF", "NETWR", "MWSBP", "GROSS", "MWSKZ", "KUNNR", "STCEG", "NAME1"]
EINV_COLS = ["supplierCompanyCode", "irn", "invoiceNumber", "supplierTin", "documentType",
             "issueDate", "clearanceDate", "status", "uuid", "currency", "taxableAmount",
             "taxAmount", "totalAmount", "taxScheme", "buyerTin", "buyerName", "isConsolidated"]


def amt(tax):
    net = tax * 12.5
    return round(net, 2), round(tax, 2), round(net + tax, 2)


def d2(x):
    return f"{x:.2f}"


class Builder:
    def __init__(self, entity="1000"):
        self.entity = entity
        self.gl = []
        self.ar = []
        self.einv = []
        self.gt = []
        self._belnr = 5000000
        self._vbeln = 9000000
        self._irn = 100000

    def next_belnr(self):
        self._belnr += 1
        return str(self._belnr)

    def next_vbeln(self):
        self._vbeln += 1
        return str(self._vbeln)

    def next_irn(self):
        self._irn += 1
        return f"IRN{self._irn}"

    # ---- GL voucher ----------------------------------------------------
    def add_gl(self, belnr, blart, date, lines, tin=None, name=None, cust_id=None, pc="PC01"):
        for i, (acct, signed) in enumerate(lines, start=1):
            self.gl.append({
                "BUKRS": self.entity, "BELNR": belnr, "GJAHR": date[:4], "BUZEI": i,
                "HKONT": acct, "BLART": blart, "BLDAT": date, "BUDAT": date,
                "WAERS": "MYR", "KURSF": "1.0", "DMBTR_SIGNED": d2(signed), "MWSKZ": STD,
                "KUNNR": cust_id or "", "STCEG": tin or "", "NAME1": name or "", "PRCTR": pc,
            })
        return belnr

    def add_ar(self, vbeln, fkart, date, net, tax, gross, tin=None, name=None,
               cust_id=None, awkey="", xblnr=""):
        self.ar.append({
            "BUKRS": self.entity, "VBELN": vbeln, "AWKEY": awkey, "XBLNR": xblnr,
            "GJAHR": date[:4], "FKART": fkart, "FKDAT": date, "BUDAT": date,
            "WAERS": "MYR", "KURSF": "1.0", "NETWR": d2(net), "MWSBP": d2(tax),
            "GROSS": d2(gross), "MWSKZ": STD, "KUNNR": cust_id or "", "STCEG": tin or "",
            "NAME1": name or "",
        })
        return vbeln

    def add_einv(self, irn, invnum, date, net, tax, gross, buyer_tin=None, buyer_name=None,
                 status="CLEARED", doctype="INV", consolidated="false", clearance=None):
        self.einv.append({
            "supplierCompanyCode": self.entity, "irn": irn, "invoiceNumber": invnum,
            "supplierTin": "MYSUP0000001", "documentType": doctype, "issueDate": date,
            "clearanceDate": clearance or date, "status": status, "uuid": f"uuid-{irn}",
            "currency": "MYR", "taxableAmount": d2(net), "taxAmount": d2(tax),
            "totalAmount": d2(gross), "taxScheme": STD, "buyerTin": buyer_tin or "",
            "buyerName": buyer_name or "", "isConsolidated": consolidated,
        })
        return invnum

    def gt_row(self, sid, name, cell, bucket, tier, card, gl_ids, ar_ids, einv_ids,
               ambiguous=False, min_alts=0):
        self.gt.append({
            "scenario_id": sid, "scenario_name": name, "expected_cell": cell,
            "expected_bucket": bucket, "expected_tier": tier, "expected_cardinality": card,
            "gl_docs": ";".join(gl_ids), "ar_docs": ";".join(ar_ids),
            "einv_docs": ";".join(einv_ids), "expected_ambiguous": str(ambiguous).lower(),
            "expected_min_alternatives": min_alts,
        })

    def write(self, folder):
        os.makedirs(folder, exist_ok=True)
        _write_csv(os.path.join(folder, "gl.csv"), GL_COLS, self.gl)
        _write_csv(os.path.join(folder, "ar.csv"), AR_COLS, self.ar)
        _write_csv(os.path.join(folder, "einv.csv"), EINV_COLS, self.einv)
        _write_csv(os.path.join(folder, "ground_truth.csv"),
                   list(self.gt[0].keys()) if self.gt else ["scenario_id"], self.gt)


def _write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def credit_invoice(net, tax, gross):
    return [(CUST, gross), (REV, -net), (TAXACC, -tax)]


def cash_sale(net, tax, gross):
    return [(BANK, gross), (REV, -net), (TAXACC, -tax)]


def credit_note(net, tax, gross):
    return [(CUST, -gross), (REV, net), (TAXACC, tax)]


# ---------------------------------------------------------------------------
def build_b2b():
    b = Builder("1000")
    tin = lambda n: f"MYB{n:07d}"
    name = lambda n: f"Buyer {n}"

    # S1: clean 1:1:1 on doc number (T0) - shared official number
    n, t, g = amt(400)
    belnr = b.add_gl("DOC1001", "F2", "2026-06-03", credit_invoice(n, t, g), tin(1), name(1), "C1")
    b.add_ar("SI1001", "F2", "2026-06-03", n, t, g, tin(1), name(1), "C1",
             awkey=belnr, xblnr="SI1001")
    b.add_einv("IRN-1001", "SI1001", "2026-06-03", n, t, g, tin(1), name(1))
    b.gt_row(1, "clean_1_1_1_T0", "E1", "ALIGNED", "T0", "1:1:1", [belnr], ["SI1001"], ["SI1001"])

    # S2: 1:1:1 join only via cross-family number (T1): einv official vs AR billing
    n, t, g = amt(650)
    belnr = b.add_gl("DOC1002", "F2", "2026-06-04", credit_invoice(n, t, g), tin(2), name(2), "C2")
    b.add_ar("BILL2002", "F2", "2026-06-04", n, t, g, tin(2), name(2), "C2", awkey=belnr)
    # einv carries the AR billing number in its official_doc_id family (irn)
    b.add_einv("BILL2002", "EINV2002", "2026-06-04", n, t, g, tin(2), name(2))
    b.gt_row(2, "cross_family_T1", "E1", "ALIGNED", "T1", "1:1:1", [belnr], ["BILL2002"], ["EINV2002"])

    # S3: 1:1:2 worked example - einv 1000, AR 1000 (no number match), 2 GL of 500
    n1, t1, g1 = amt(1000)
    n5, t5, g5 = amt(500)
    gl_a = b.add_gl("WEXGL1", "F2", "2026-06-06", credit_invoice(n5, t5, g5), tin(3), name(3), "C3")
    gl_b = b.add_gl("WEXGL2", "F2", "2026-06-06", credit_invoice(n5, t5, g5), tin(3), name(3), "C3")
    # AR one day later so composite key differs -> E/A resolves at T3, not T2
    b.add_ar("WEXAR9", "F2", "2026-06-07", n1, t1, g1, tin(3), name(3), "C3")
    b.add_einv("WEXEI7", "WEXEI7", "2026-06-06", n1, t1, g1, tin(3), name(3))
    b.gt_row(3, "worked_example_1_1_2", "E1", "ALIGNED", "T4", "1:1:2",
             [gl_a, gl_b], ["WEXAR9"], ["WEXEI7"])

    # S4: 1:N - one e-invoice, three AR documents (split billing)
    parts = [amt(300), amt(400), amt(500)]
    ntot = sum(p[0] for p in parts); ttot = sum(p[1] for p in parts); gtot = sum(p[2] for p in parts)
    ar_ids = []
    for k, (nn, tt, gg) in enumerate(parts):
        ar_ids.append(b.add_ar(f"SPLIT4{k}", "F2", "2026-06-08", nn, tt, gg, tin(4), name(4), "C4"))
    b.add_einv("SPLITEI4", "SPLITEI4", "2026-06-08", ntot, ttot, gtot, tin(4), name(4))
    b.gt_row(4, "one_to_N_split_billing", "E5", "RECEIVABLE_REPORTED_NO_REVENUE",
             "T4", "1:3:0", [], ar_ids, ["SPLITEI4"])

    # S6: N:M - balanced cluster 4 einv vs 3 AR. Amounts chosen so no subset of
    # one side equals any document or subset on the other (no clean T3/T4 exists);
    # the whole component only balances as a cluster (sum 1500 == 1500).
    ar_vals = [amt(710), amt(530), amt(260)]
    ei_vals = [amt(370), amt(380), amt(390), amt(360)]
    ar_ids = [b.add_ar(f"NM6A{k}", "F2", "2026-06-10", *v, tin(6), name(6), "C6")
              for k, v in enumerate(ar_vals)]
    ei_ids = [b.add_einv(f"NM6E{k}", f"NM6E{k}", "2026-06-10", *v, tin(6), name(6))
              for k, v in enumerate(ei_vals)]
    b.gt_row(6, "N_M_balanced_cluster", "E5", "RECEIVABLE_REPORTED_NO_REVENUE",
             "T5", "4:3:0", [], ar_ids, ei_ids)

    # S7: degenerate - ten GL of tax 500, one einv of 1000 -> 45 alternatives
    gl_ids = []
    for k in range(10):
        gl_ids.append(b.add_gl(f"DEG7{k:02d}", "F2", "2026-06-12",
                               credit_invoice(*amt(500)), tin(7), name(7), "C7"))
    b.add_einv("DEG7EI", "DEG7EI", "2026-06-12", *amt(1000), tin(7), name(7))
    b.gt_row(7, "degenerate_45_alternatives", "E1", "ALIGNED", "T4", "1:0:2",
             gl_ids, [], ["DEG7EI"], ambiguous=True, min_alts=45)

    # S8: E2 - booked and billed, no e-invoice (portal rejection)
    n, t, g = amt(720)
    belnr = b.add_gl("E2A8", "F2", "2026-06-05", credit_invoice(n, t, g), tin(8), name(8), "C8")
    b.add_ar("E2AR8", "F2", "2026-06-05", n, t, g, tin(8), name(8), "C8", awkey=belnr)
    b.gt_row(8, "E2_billed_unreported", "E2", "BILLED_UNREPORTED", "UNMATCHED", "0:1:1",
             [belnr], ["E2AR8"], [])

    # S9: E2 - cancelled e-invoice never reissued
    n, t, g = amt(333)
    belnr = b.add_gl("E2A9", "F2", "2026-06-05", credit_invoice(n, t, g), tin(9), name(9), "C9")
    b.add_ar("E2AR9", "F2", "2026-06-05", n, t, g, tin(9), name(9), "C9", awkey=belnr)
    b.add_einv("E2EI9", "E2EI9", "2026-06-05", n, t, g, tin(9), name(9), status="CANCELLED")
    b.gt_row(9, "E2_cancelled_einvoice", "E2", "BILLED_UNREPORTED", "UNMATCHED", "0:1:1",
             [belnr], ["E2AR9"], [])

    # S11: E4 - unbilled revenue accrual (revenue + tax, no customer, no einv)
    n, t, g = amt(210)
    belnr = b.add_gl("E4A11", "SA", "2026-06-20",
                     [(BANK, g), (REV, -n), (TAXACC, -t)], tin(11), name(11), "C11")
    b.gt_row(11, "E4_accrual", "E4", "REVENUE_NO_RECEIVABLE_NO_REPORT", "UNMATCHED", "0:0:1",
             [belnr], [], [])

    # S12: E5 - asset disposal, credit to unmapped gain account
    n, t, g = amt(880)
    belnr = b.add_gl("E5A12", "F2", "2026-06-15",
                     [(CUST, g), (DISPOSAL_UNMAPPED, -n), (TAXACC, -t)], tin(12), name(12), "C12")
    b.add_einv("E5EI12", "E5EI12", "2026-06-15", n, t, g, tin(12), name(12))
    b.gt_row(12, "E5_asset_disposal", "E5", "RECEIVABLE_REPORTED_NO_REVENUE", "T2", "1:0:1",
             [belnr], [], ["E5EI12"])

    # S13: E5 - notice-pay recovery credited to unmapped other income
    n, t, g = amt(150)
    belnr = b.add_gl("E5A13", "F2", "2026-06-16",
                     [(CUST, g), (OTHERINC_UNMAPPED, -n), (TAXACC, -t)], tin(13), name(13), "C13")
    b.add_einv("E5EI13", "E5EI13", "2026-06-16", n, t, g, tin(13), name(13))
    b.gt_row(13, "E5_notice_pay", "E5", "RECEIVABLE_REPORTED_NO_REVENUE", "T2", "1:0:1",
             [belnr], [], ["E5EI13"])

    # S14: E6 - incoming receipt / clearing / write-off (must be suppressed)
    belnr = b.add_gl("E6A14", "DZ", "2026-06-18",
                     [(BANK, 5000.00), (CUST, -5000.00)], tin(14), name(14), "C14")
    b.gt_row(14, "E6_receipt_clearing", "E6", "RECEIVABLE_MOVEMENT_ONLY", "UNMATCHED", "0:0:1",
             [belnr], [], [])

    # S15: E7 - e-invoice cleared, accounting document parked/unposted
    n, t, g = amt(940)
    b.add_einv("E7EI15", "E7EI15", "2026-06-19", n, t, g, tin(15), name(15))
    b.gt_row(15, "E7_reported_unbooked", "E7", "REPORTED_UNBOOKED", "UNMATCHED", "1:0:0",
             [], [], ["E7EI15"])

    # S16: WHT - customer debited net of withholding
    n, t, g = amt(500)
    wht_amt = round(n * 0.10, 2)
    belnr = b.add_gl("WHT16", "F2", "2026-06-11",
                     [(CUST, g - wht_amt), (WHT, wht_amt), (REV, -n), (TAXACC, -t)],
                     tin(16), name(16), "C16")
    b.add_ar("WHTAR16", "F2", "2026-06-11", n, t, g, tin(16), name(16), "C16", awkey=belnr)
    b.add_einv("WHTEI16", "WHTAR16", "2026-06-11", n, t, g, tin(16), name(16))
    b.gt_row(16, "WHT_deduction", "E1", "ALIGNED", "T1", "1:1:1", [belnr], ["WHTAR16"], ["WHTEI16"])

    # S18: rounding difference line
    n, t, g = amt(377)
    belnr = b.add_gl("RND18", "F2", "2026-06-13",
                     [(CUST, g + 0.02), (REV, -n), (TAXACC, -t), (ROUND, -0.02)],
                     tin(18), name(18), "C18")
    b.add_ar("RNDAR18", "F2", "2026-06-13", n, t, g, tin(18), name(18), "C18", awkey=belnr)
    b.add_einv("RND18", "RNDAR18", "2026-06-13", n, t, g, tin(18), name(18))
    b.gt_row(18, "rounding_line", "E1", "ALIGNED", "T0", "1:1:1", [belnr], ["RNDAR18"], ["RND18"])

    # S19: multi-line - three revenue accounts, one customer line
    belnr = "MULTI19"
    lines = [(CUST, 33750.00), (REV, -10000.00), (REV, -8000.00), (REV, -7000.00),
             (TAXACC, -2000.00)]
    b.add_gl(belnr, "F2", "2026-06-14", lines, tin(19), name(19), "C19")
    b.add_ar("MULTIAR19", "F2", "2026-06-14", 25000.00, 2000.00, 27000.00,
             tin(19), name(19), "C19", awkey=belnr)
    b.add_einv("MULTI19", "MULTIAR19", "2026-06-14", 25000.00, 2000.00, 27000.00, tin(19), name(19))
    b.gt_row(19, "multiline_revenue", "E1", "ALIGNED", "T0", "1:1:1",
             [belnr], ["MULTIAR19"], ["MULTI19"])

    # S20: wrong tax code - net ties, tax breaks
    n, t, g = amt(500)
    belnr = b.add_gl("WTC20", "F2", "2026-06-17",
                     [(CUST, n + 250.00), (REV, -n), (TAXACC, -250.00)], tin(20), name(20), "C20")
    b.add_ar("WTCAR20", "F2", "2026-06-17", n, t, g, tin(20), name(20), "C20", awkey=belnr)
    b.add_einv("WTC20", "WTCAR20", "2026-06-17", n, t, g, tin(20), name(20))
    b.gt_row(20, "wrong_tax_code", "E1", "ALIGNED", "T0", "1:1:1", [belnr], ["WTCAR20"], ["WTC20"])

    # S21: credit note booked with inverted sign
    n, t, g = amt(260)
    belnr = b.add_gl("CN21", "G2", "2026-06-21", credit_note(n, t, g), tin(21), name(21), "C21")
    b.add_ar("CNAR21", "G2", "2026-06-21", n, t, g, tin(21), name(21), "C21", awkey=belnr)
    b.add_einv("CN21", "CNAR21", "2026-06-21", n, t, g, tin(21), name(21), doctype="G2")
    b.gt_row(21, "credit_note_inverted", "E1", "ALIGNED", "T0", "1:1:1",
             [belnr], ["CNAR21"], ["CN21"])

    # S22: cut-off - e-invoice cleared June, posted July
    n, t, g = amt(410)
    belnr = b.add_gl("CUT22", "F2", "2026-07-02", credit_invoice(n, t, g), tin(22), name(22), "C22")
    b.add_ar("CUTAR22", "F2", "2026-07-02", n, t, g, tin(22), name(22), "C22", awkey=belnr)
    b.add_einv("CUT22", "CUTAR22", "2026-06-30", n, t, g, tin(22), name(22))
    b.gt_row(22, "cut_off_timing", "E1", "ALIGNED", "T0", "1:1:1", [belnr], ["CUTAR22"], ["CUT22"])

    # S23: foreign currency invoice with FX difference posting (kept as MYR-reported)
    n, t, g = amt(700)
    belnr = b.add_gl("FX23", "F2", "2026-06-22",
                     [(CUST, g + 15.00), (REV, -n), (TAXACC, -t), (ROUND, -15.00)],
                     tin(23), name(23), "C23")
    b.add_ar("FXAR23", "F2", "2026-06-22", n, t, g, tin(23), name(23), "C23", awkey=belnr)
    b.add_einv("FX23", "FXAR23", "2026-06-22", n, t, g, tin(23), name(23))
    b.gt_row(23, "fx_difference", "E1", "ALIGNED", "T0", "1:1:1", [belnr], ["FXAR23"], ["FX23"])

    # S24: credit note with broken original-document reference. None of the four
    # number families join (T0/T1 fail), but the deterministic composite key
    # (entity + TIN + tax-point date + gross + tax) still ties all three planes.
    n, t, g = amt(180)
    belnr = b.add_gl("CN24", "G2", "2026-06-23", credit_note(n, t, g), tin(24), name(24), "C24")
    b.add_ar("CNAR24", "G2", "2026-06-23", n, t, g, tin(24), name(24), "C24")
    b.add_einv("CN24BROKEN", "CN24E", "2026-06-23", n, t, g, tin(24), name(24), doctype="G2")
    b.gt_row(24, "credit_note_broken_ref", "E1", "ALIGNED", "T2", "1:1:1",
             [belnr], ["CNAR24"], ["CN24E"])

    # S25: proforma present in AR extract - must be excluded, not matched
    n, t, g = amt(999)
    b.add_ar("PROF25", "F8", "2026-06-25", n, t, g, tin(25), name(25), "C25")
    b.gt_row(25, "proforma_excluded", "QUARANTINE", "excluded_doc_class:PROFORMA",
             "NONE", "0:0:0", [], ["PROF25"], [])

    # S26: duplicate e-invoice submission for one accounting document
    n, t, g = amt(555)
    belnr = b.add_gl("DUP26", "F2", "2026-06-26", credit_invoice(n, t, g), tin(26), name(26), "C26")
    b.add_ar("DUPAR26", "F2", "2026-06-26", n, t, g, tin(26), name(26), "C26", awkey=belnr)
    b.add_einv("DUPAR26", "DUPAR26", "2026-06-26", n, t, g, tin(26), name(26))
    b.add_einv("DUPAR26B", "DUPAR26", "2026-06-26", n, t, g, tin(26), name(26))
    b.gt_row(26, "duplicate_einvoice", "E1", "ALIGNED", "T0", "1:1:1",
             [belnr], ["DUPAR26"], ["DUPAR26"])

    _pad_b2b(b, target=420)
    return b


def _pad_b2b(b, target):
    """Clean 1:1:1 B2B credit invoices, unique counterparty + date each."""
    day = 1
    k = 1000
    while len(b.gl) < target or len(b.ar) < target or len(b.einv) < target:
        tin = f"MYF{k:07d}"
        name = f"Filler {k}"
        date = f"2026-06-{(day % 27) + 1:02d}"
        n, t, g = amt(100 + (k % 400))
        num = f"FIL{k}"
        belnr = b.add_gl(num, "F2", date, credit_invoice(n, t, g), tin, name, f"K{k}")
        b.add_ar(num, "F2", date, n, t, g, tin, name, f"K{k}", awkey=belnr, xblnr=num)
        b.add_einv(num, num, date, n, t, g, tin, name)
        b.gt_row(1000 + k, "filler_clean_T0", "E1", "ALIGNED", "T0", "1:1:1",
                 [belnr], [num], [num])
        k += 1
        day += 1


def build_b2c():
    b = Builder("1100")
    tin = lambda n: f"MYB{n:07d}"

    # S5: N:1 - twelve e-invoices, one consolidated daily GL posting
    ei_ids = []
    total_n = total_t = total_g = 0.0
    for k in range(12):
        n, t, g = amt(50 + k * 10)
        total_n += n; total_t += t; total_g += g
        ei_ids.append(b.add_einv(f"C5E{k:02d}", f"C5E{k:02d}", "2026-06-02",
                                 n, t, g, consolidated="false"))
    belnr = b.add_gl("C5GL", "BV", "2026-06-02", cash_sale(total_n, total_t, total_g),
                     pc="STORE01")
    b.gt_row(5, "N_to_1_consolidated", "E3", "NON_CUSTOMER_SETTLED_SALE", "T4", "12:0:1",
             [belnr], [], ei_ids)

    # S10: E3 - cash sale, Dr Bank / Cr Rev / Cr Tax, einv present, no customer line.
    # Identical gross/tax/date -> deterministic composite match (T2).
    n, t, g = amt(120)
    belnr = b.add_gl("C10GL", "BV", "2026-06-03", cash_sale(n, t, g), pc="STORE02")
    b.add_einv("C10E", "C10E", "2026-06-03", n, t, g)
    b.gt_row(10, "E3_cash_sale", "E3", "NON_CUSTOMER_SETTLED_SALE", "T2", "1:0:1",
             [belnr], [], ["C10E"])

    # S17: TCS added on top of gross (extra collection line in ROUNDING/clearing)
    n, t, g = amt(300)
    tcs = round(g * 0.01, 2)
    belnr = b.add_gl("C17GL", "BV", "2026-06-04",
                     [(BANK, g + tcs), (REV, -n), (TAXACC, -t), (ROUND, -tcs)], pc="STORE01")
    b.add_einv("C17E", "C17E", "2026-06-04", n, t, g)
    b.gt_row(17, "TCS_on_top", "E3", "NON_CUSTOMER_SETTLED_SALE", "T3", "1:0:1",
             [belnr], [], ["C17E"])

    # worked example again in B2C (mandatory in both datasets): 1:1:2.
    # Modelled as a credit sale inside the retail entity (customer + counterparty)
    # so all four documents share a block and resolve E<->A (T3) + A<->G (T4).
    n1, t1, g1 = amt(1000)
    n5, t5, g5 = amt(500)
    gl_a = b.add_gl("C3WGL1", "F2", "2026-06-06", credit_invoice(n5, t5, g5),
                    tin(300), "Buyer 300", "C300")
    gl_b = b.add_gl("C3WGL2", "F2", "2026-06-06", credit_invoice(n5, t5, g5),
                    tin(300), "Buyer 300", "C300")
    b.add_ar("C3WAR", "F2", "2026-06-07", n1, t1, g1, tin(300), "Buyer 300", "C300")
    b.add_einv("C3WEI", "C3WEI", "2026-06-06", n1, t1, g1, tin(300), "Buyer 300")
    b.gt_row(3, "worked_example_1_1_2", "E1", "ALIGNED", "T4", "1:1:2",
             [gl_a, gl_b], ["C3WAR"], ["C3WEI"])

    # degenerate again in B2C
    gl_ids = []
    for k in range(10):
        gl_ids.append(b.add_gl(f"C7DEG{k:02d}", "BV", "2026-06-12",
                               cash_sale(*amt(500)), pc="STORE07"))
    b.add_einv("C7DEGE", "C7DEGE", "2026-06-12", *amt(1000))
    b.gt_row(7, "degenerate_45_alternatives", "E3", "NON_CUSTOMER_SETTLED_SALE",
             "T4", "1:0:2", gl_ids, [], ["C7DEGE"], ambiguous=True, min_alts=45)

    # E6 suppression case in B2C too
    belnr = b.add_gl("C14GL", "DZ", "2026-06-18", [(BANK, 8000.00), (CUST, -8000.00)],
                     tin(214), "Buyer 214", "C214")
    b.gt_row(14, "E6_receipt_clearing", "E6", "RECEIVABLE_MOVEMENT_ONLY", "UNMATCHED",
             "0:0:1", [belnr], [], [])

    _pad_b2c(b, target=420)
    return b


def _pad_b2c(b, target):
    """Clean B2C cash sales: one GL cash voucher + one e-invoice, matched at T2.

    Filler uses dates 06-20..06-27 so it never shares a daily (B3) block with the
    labelled scenarios, which live on 06-02..06-12.
    """
    k = 1
    while len(b.gl) < target or len(b.einv) < target:
        n, t, g = amt(30 + (k % 300))
        date = f"2026-06-{20 + (k % 8):02d}"
        num = f"C2CF{k}"
        belnr = b.add_gl(num, "BV", date, cash_sale(n, t, g), pc=f"STORE{k%9:02d}")
        b.add_einv(num, num, date, n, t, g)
        b.gt_row(2000 + k, "filler_cash_T2", "E3", "NON_CUSTOMER_SETTLED_SALE",
                 "T2", "1:0:1", [belnr], [], [num])
        k += 1
    # credit-sale filler pads the AR plane past the 400-document minimum; matched
    # at T0 on a shared document number and isolated by a unique counterparty.
    k = 1
    while len([r for r in b.ar]) < 400:
        n, t, g = amt(50 + (k % 200))
        date = f"2026-06-{20 + (k % 8):02d}"
        num = f"C2CB{k}"
        tinv = f"MYC{k:07d}"
        belnr = b.add_gl(num, "F2", date, credit_invoice(n, t, g), tinv, f"Cred {k}", f"CC{k}")
        b.add_ar(num, "F2", date, n, t, g, tinv, f"Cred {k}", f"CC{k}", awkey=belnr, xblnr=num)
        b.add_einv(num, num, date, n, t, g, tinv, f"Cred {k}")
        b.gt_row(3000 + k, "filler_credit_T0", "E1", "ALIGNED", "T0", "1:1:1",
                 [belnr], [num], [num])
        k += 1


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build_b2b().write(os.path.join(root, "data", "b2b"))
    build_b2c().write(os.path.join(root, "data", "b2c"))
    print("Generated data/b2b and data/b2c")


if __name__ == "__main__":
    main()
