"""Normalisation: document numbers, minor units, FX.

All matching runs on integer minor units. Floats are never compared.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def to_minor(amount, minor_exp: int) -> int:
    """Convert a decimal-ish amount to signed integer minor units.

    Uses Decimal with HALF_UP rounding so 12.345 at exp 2 -> 1235 minor,
    deterministically. Never uses binary floats for the boundary.
    """
    if amount is None or amount == "":
        return 0
    d = Decimal(str(amount))
    q = Decimal(1).scaleb(-minor_exp)  # 0.01 at exp 2
    return int((d / q).to_integral_value(rounding=ROUND_HALF_UP))


def minor_to_decimal(minor: int, minor_exp: int) -> Decimal:
    q = Decimal(1).scaleb(-minor_exp)
    return (Decimal(int(minor)) * q).quantize(q)


def normalize_number(raw: str | None, ops: list[dict]) -> str:
    """Apply the client profile's ordered normalisation ops to one number."""
    if raw is None:
        return ""
    s = str(raw).strip()
    for op in ops:
        kind = op.get("op")
        if kind == "upper":
            s = s.upper()
        elif kind == "lower":
            s = s.lower()
        elif kind == "strip_chars":
            for ch in op.get("chars", ""):
                s = s.replace(ch, "")
        elif kind == "strip_prefix":
            for pref in op.get("values", []):
                p = str(pref).upper()
                if s.upper().startswith(p):
                    s = s[len(p):]
                    break
        elif kind == "strip_suffix":
            for suf in op.get("values", []):
                p = str(suf).upper()
                if s.upper().endswith(p):
                    s = s[: len(s) - len(p)]
                    break
        elif kind == "strip_leading_zeros":
            s = s.lstrip("0") or "0"
    return s


# the four number families every document may carry
NUMBER_FAMILIES = ["doc_id_native", "accounting_doc_id", "billing_doc_id", "official_doc_id"]


def normalized_families(rec: dict, ops: list[dict]) -> dict:
    """Return {family: normalized_value} for every non-empty family."""
    out = {}
    for fam in NUMBER_FAMILIES:
        val = rec.get(fam)
        if val:
            norm = normalize_number(val, ops)
            if norm:
                out[fam] = norm
    return out
