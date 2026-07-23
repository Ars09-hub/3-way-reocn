"""Plane tests (spec §11.1, §16).

Every match and every aligned unit is tested on a vector of three planes -
[tax_minor, net_minor, gross_minor]. Tax is the primary, most discriminating
key; net and gross are verification planes. A plane 'ties' when the sides agree
within tolerance and 'breaks' otherwise.
"""
from __future__ import annotations

from .config import LoadedConfig

PLANES = ["gross", "net", "tax"]


def tol_for(cfg: LoadedConfig, k: int, target: int) -> int:
    """tol(k, target) = max(rounding_abs_minor_per_doc * k, relative_tol * |target|)."""
    return max(cfg.rounding_abs_minor_per_doc * max(k, 1),
               int(round(cfg.relative_tol * abs(target))))


def plane_status(cfg: LoadedConfig, values: dict, cardinality: int) -> dict:
    """values: {plane: {'gl':int,'ar':int,'einv':int}} signed minor sums.

    Returns per-plane status with deltas between adjacent planes present.
    """
    out = {}
    for plane in PLANES:
        v = values.get(plane, {})
        gl = v.get("gl")
        ar = v.get("ar")
        einv = v.get("einv")
        present = [x for x in (gl, ar, einv) if x is not None]
        target = max((abs(x) for x in present), default=0)
        tol = tol_for(cfg, cardinality, target)
        delta_gl_ar = (abs(gl) - abs(ar)) if (gl is not None and ar is not None) else None
        delta_ar_einv = (abs(ar) - abs(einv)) if (ar is not None and einv is not None) else None
        delta_gl_einv = (abs(gl) - abs(einv)) if (gl is not None and einv is not None) else None
        breaks = []
        for d in (delta_gl_ar, delta_ar_einv, delta_gl_einv):
            if d is not None:
                breaks.append(abs(d) > tol)
        status = "TIE" if (breaks and not any(breaks)) else ("BREAK" if breaks else "NA")
        out[plane] = {
            "gl": gl, "ar": ar, "einv": einv,
            "delta_gl_ar": delta_gl_ar,
            "delta_ar_einv": delta_ar_einv,
            "delta_gl_einv": delta_gl_einv,
            "tolerance": tol,
            "status": status,
        }
    return out


def diagnose(planes: dict, integrity_ok: bool, sign_inverted: bool,
             cutoff: bool, tin_mismatch: bool,
             implied_rate_dev: bool) -> str:
    """Plane diagnosis within an aligned unit (spec §16)."""
    net = planes.get("net", {}).get("status")
    tax = planes.get("tax", {}).get("status")
    gross = planes.get("gross", {}).get("status")

    if sign_inverted:
        return "DOCUMENT_CLASS_INVERSION"
    if tin_mismatch:
        return "COUNTERPARTY_DETERMINATION"
    if implied_rate_dev:
        return "RATE_MISAPPLICATION"
    if cutoff:
        return "CUT_OFF_TIMING"
    if net == "TIE" and tax == "BREAK":
        return "TAX_CODE_DETERMINATION"
    if tax == "TIE" and net == "BREAK":
        return "TAXABLE_VALUE_COMPOSITION"
    if gross == "TIE" and (net == "BREAK" or tax == "BREAK"):
        return "TAX_CODE_MAPPING"
    if net == "BREAK" and tax == "BREAK":
        return "QUANTITY_OR_PRICE_VARIANCE"
    return "ALIGNED"
