"""Normalisation helpers: document numbers, signs, halalas, VAT numbers, string arrays.

Deterministic and side-effect free. Every rule here maps to spec section 1 and 2.2.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, ROUND_HALF_UP

_CM_DM = re.compile(r"^(CM|DM)-", re.IGNORECASE)
_LEADING_ZEROS = re.compile(r"^0+(?=\d)")


def to_halalas(value) -> int:
    """Convert a currency amount to integer halalas (2 dp). Never compare floats (spec 2.2).

    Blank / NaN becomes 0.
    """
    if value is None:
        return 0
    if isinstance(value, float) and math.isnan(value):
        return 0
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return 0
    s = s.replace(",", "")
    return int(Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def halalas_to_str(h: int) -> str:
    """Render integer halalas back as a fixed 2 dp string with thousands separators."""
    neg = h < 0
    h = abs(int(h))
    whole, frac = divmod(h, 100)
    out = f"{whole:,}.{frac:02d}"
    return ("-" + out) if neg else out


def clean_vat(value) -> str:
    """Strip literal apostrophes and whitespace, keep alphanumerics only (spec 2.2)."""
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() == "nan":
        return ""
    return re.sub(r"[^0-9A-Za-z]", "", s)


def is_valid_tin(value, tin_cfg: dict) -> bool:
    """KSA TIN: 15 digits, starts and ends with 3 (config driven)."""
    v = clean_vat(value)
    return (
        len(v) == tin_cfg["length"]
        and v.isdigit()
        and v.startswith(tin_cfg["starts_with"])
        and v.endswith(tin_cfg["ends_with"])
    )


def normalize_doc_number(value) -> str:
    """Canonical document key across the three number families (spec 1.4).

    Strip CM-/DM- credit-note prefix, upper-case, trim, strip leading zeros.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() == "nan" or s == "":
        return ""
    s = _CM_DM.sub("", s)
    s = s.strip().upper()
    s = _LEADING_ZEROS.sub("", s)
    return s


def is_credit_note_number(value) -> bool:
    return bool(_CM_DM.match(str(value).strip())) if value is not None else False


def parse_string_array(value) -> list[str]:
    """Parse the '[a, b]' / '[]' / blank string-array format (spec 2.2)."""
    if value is None:
        return []
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return []
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    if s == "":
        return []
    parts = [p.strip().strip("'\"") for p in s.split(",")]
    return [p for p in parts if p != ""]


def map_currency(value, aliases: dict) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return aliases.get(s, s)


def clean_gl_code(value) -> str:
    """GL codes sometimes arrive as floats (e.g. 41140104.0). Return the bare integer string."""
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() == "nan" or s == "":
        return ""
    return re.sub(r"\.0$", "", s)
