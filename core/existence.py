"""Existence matrix - the 7-cell R/C/E classification (spec §8).

R = revenue/tax lines present, C = customer-control (or AR) present,
E = e-invoice present. The customer axis is CONDITIONAL on settlement_type:
cash / card / wallet / aggregator sales never touch the customer control
account, so R + E with no C is expected (E3), not an anomaly.
"""
from __future__ import annotations

# (R, C, E) -> (cell, bucket, severity, disposition)
_MATRIX = {
    (True, True, True):   ("E1", "ALIGNED", "INFO", "proceed to plane tests"),
    (True, True, False):  ("E2", "BILLED_UNREPORTED", "CRITICAL", "exposure"),
    (True, False, True):  ("E3", "NON_CUSTOMER_SETTLED_SALE", "INFO", "expected when settlement != CREDIT"),
    (True, False, False): ("E4", "REVENUE_NO_RECEIVABLE_NO_REPORT", "REVIEW", "accrual / RAR / interco / reclass"),
    (False, True, True):  ("E5", "RECEIVABLE_REPORTED_NO_REVENUE", "HIGH", "usually account-mapping gap"),
    (False, True, False): ("E6", "RECEIVABLE_MOVEMENT_ONLY", "SUPPRESSED", "cash traffic - filter, don't flag"),
    (False, False, True): ("E7", "REPORTED_UNBOOKED", "CRITICAL", "reverse exposure"),
}

SETTLED_NON_CREDIT = {"CASH", "CARD", "WALLET", "AGGREGATOR"}


def classify_cell(has_revenue: bool, has_customer: bool, has_einv: bool,
                  settlement_type: str | None) -> dict:
    key = (bool(has_revenue), bool(has_customer), bool(has_einv))
    if key == (False, False, False):
        # nothing present - should not happen for a real unit
        return {"existence_cell": "E0", "bucket": "EMPTY", "severity": "SUPPRESSED",
                "disposition": "empty unit"}
    cell, bucket, severity, disp = _MATRIX[key]

    # E3 is mandatory and correct for non-credit settlement. If somehow an
    # R+not-C+E unit is on a CREDIT settlement it is worth a REVIEW instead.
    if cell == "E3" and settlement_type == "CREDIT":
        severity = "REVIEW"
        disp = "revenue + e-invoice but no receivable on a credit sale - investigate"
    return {"existence_cell": cell, "bucket": bucket, "severity": severity,
            "disposition": disp}
