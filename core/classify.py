"""Classification: account class, doc class, segment, settlement type, sign.

All decisions are driven by the client profile and country pack passed in.
No hardcoded client/country vocabulary lives here.
"""
from __future__ import annotations

from .config import LoadedConfig

# sign is derived from doc_class, never from amount polarity (spec §4).
SIGN_BY_DOC_CLASS = {
    "INVOICE": +1,
    "DEBIT_NOTE": +1,
    "ADVANCE": +1,
    "RECEIPT": +1,
    "PROFORMA": +1,
    "JOURNAL": +1,
    "ADJUSTMENT": +1,
    "OTHER": +1,
    "CREDIT_NOTE": -1,
    "CANCELLATION": -1,
}

# revenue-recognising classes for the R existence axis and Leg A revenue_side
REVENUE_CLASSES = {"REVENUE", "OTHER_INCOME", "ASSET_DISPOSAL"}
EXPLAINED_CLASSES = {"WHT", "ROUNDING", "FREIGHT", "DISCOUNT", "CLEARING"}


def sign_for(doc_class: str) -> int:
    return SIGN_BY_DOC_CLASS.get(doc_class, +1)


def doc_class_for(cfg: LoadedConfig, doc_type_native: str) -> dict:
    """Look up doc_type in the client profile's doc_type_map.

    Returns a dict with doc_class, einv_relevant, and optional
    settlement_type / is_reversal hints. Unknown types map to OTHER.
    """
    mapping = cfg.client.get("doc_type_map", {})
    entry = mapping.get(doc_type_native)
    if entry is None:
        return {"doc_class": "OTHER", "einv_relevant": False, "is_reversal": False}
    return {
        "doc_class": entry.get("doc_class", "OTHER"),
        "einv_relevant": bool(entry.get("einv_relevant", False)),
        "settlement_type": entry.get("settlement_type"),
        "is_reversal": bool(entry.get("is_reversal", False)),
    }


def segment_for(counterparty_tin: str | None, settlement_type: str | None,
                explicit: str | None) -> str:
    if explicit:
        return explicit
    if settlement_type in ("CASH", "CARD", "WALLET", "AGGREGATOR"):
        return "B2C"
    if counterparty_tin:
        return "B2B"
    return "UNKNOWN"


def settlement_for(account_classes_present: set[str], doc_hint: str | None) -> str:
    if doc_hint:
        return doc_hint
    if "BANK" in account_classes_present and "CUSTOMER_CONTROL" not in account_classes_present:
        return "CASH"
    if "CUSTOMER_CONTROL" in account_classes_present:
        return "CREDIT"
    return "UNKNOWN"
