"""Scoring (spec §12).

score = Σ wᵢ × componentᵢ  (weights from engine config, sum to 1.0)

Rejection rules override scoring: conflicting TINs, mismatched tax categories,
opposite signs, or a date spread beyond the window disqualify a candidate
regardless of amount agreement. A perfect amount tie between two different
customers is a coincidence, not a match.
"""
from __future__ import annotations

import math
from datetime import date

from ..config import LoadedConfig


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        y, m, d = str(s)[:10].split("-")
        return date(int(y), int(m), int(d))
    except Exception:  # noqa: BLE001
        return None


def _name_sim(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    a, b = a.strip().upper(), b.strip().upper()
    if a == b:
        return 1.0
    # token Jaccard - cheap, deterministic
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def side_sum(side: list[dict], plane: str) -> int:
    return sum(d[f"{plane}_minor"] for d in side)


def rel_diff(a: int, b: int) -> float:
    denom = max(abs(a), abs(b), 1)
    return abs(a - b) / denom


class ScoreResult:
    def __init__(self):
        self.score = 0.0
        self.components: dict = {}
        self.rejected = False
        self.reject_reason: str | None = None


def score_match(cfg: LoadedConfig, side_a: list[dict], side_b: list[dict],
                is_b2c: bool, alternatives_count: int = 1) -> ScoreResult:
    r = ScoreResult()
    w = cfg.engine["scoring_weights"]
    plane_w = cfg.engine["plane_weights"]
    max_rel = cfg.max_relative_tol

    # ---- hard rejection rules ------------------------------------------
    # opposite signs
    signs_a = {d["sign"] for d in side_a}
    signs_b = {d["sign"] for d in side_b}
    if signs_a and signs_b and (max(signs_a) != max(signs_b) or min(signs_a) != min(signs_b)):
        if signs_a != signs_b:
            r.rejected = True
            r.reject_reason = "OPPOSITE_SIGN"
            return r

    # tax category conflict
    cats_a = {d.get("tax_category") for d in side_a if d.get("tax_category")}
    cats_b = {d.get("tax_category") for d in side_b if d.get("tax_category")}
    if cats_a and cats_b and cats_a.isdisjoint(cats_b):
        r.rejected = True
        r.reject_reason = "TAX_CATEGORY_CONFLICT"
        return r

    # conflicting TINs
    tins_a = {d.get("counterparty_tin") for d in side_a if d.get("counterparty_tin")}
    tins_b = {d.get("counterparty_tin") for d in side_b if d.get("counterparty_tin")}
    if tins_a and tins_b and tins_a.isdisjoint(tins_b):
        r.rejected = True
        r.reject_reason = "TIN_CONFLICT"
        return r

    # date window
    tau = 15 if is_b2c else 7
    window = cfg.engine["matching"]["date_window_days_b2c"] if is_b2c else cfg.engine["matching"]["date_window_days"]
    dates = [_parse_date(d["doc_date"]) for d in side_a + side_b]
    dates = [d for d in dates if d]
    if len(dates) >= 2:
        spread = (max(dates) - min(dates)).days
        if spread > window:
            r.rejected = True
            r.reject_reason = "DATE_WINDOW"
            return r

    # ---- amount component ----------------------------------------------
    amount = 0.0
    used_w = 0.0
    for plane in ("tax", "net", "gross"):
        sa = side_sum(side_a, plane)
        sb = side_sum(side_b, plane)
        if sa == 0 and sb == 0:
            continue
        pw = plane_w[plane]
        rd = rel_diff(sa, sb)
        amount += pw * (1.0 - min(1.0, rd / max_rel))
        used_w += pw
    amount = amount / used_w if used_w else 0.0

    # ---- date component -------------------------------------------------
    if len(dates) >= 2:
        dd = (max(dates) - min(dates)).days
        date_comp = math.exp(-abs(dd) / tau)
    else:
        date_comp = 1.0

    # ---- counterparty component ----------------------------------------
    if tins_a and tins_b:
        cp = 1.0 if (tins_a & tins_b) else 0.0
    elif not tins_a and not tins_b:
        cp = 0.6  # B2C neutral
    else:
        names_a = [d.get("counterparty_name") for d in side_a]
        names_b = [d.get("counterparty_name") for d in side_b]
        best = max((_name_sim(x, y) for x in names_a for y in names_b), default=0.0)
        cp = 0.7 if best >= 0.9 else 0.3

    # ---- taxcode component ---------------------------------------------
    codes_a = {d.get("tax_code") for d in side_a if d.get("tax_code")}
    codes_b = {d.get("tax_code") for d in side_b if d.get("tax_code")}
    if codes_a and codes_b:
        if codes_a & codes_b:
            tc = 1.0
        elif not cats_a.isdisjoint(cats_b):
            tc = 0.6
        else:
            tc = 0.0
    else:
        tc = 0.6

    # ---- cardinality component -----------------------------------------
    n = len(side_a) + len(side_b)
    card = 1.0 / (1.0 + 0.15 * max(0, n - 2))

    # ---- uniqueness component ------------------------------------------
    uniq = 1.0 / (1.0 + math.log(max(1, alternatives_count)))

    r.components = {
        "amount": amount, "date": date_comp, "counterparty": cp,
        "taxcode": tc, "cardinality": card, "uniqueness": uniq,
    }
    r.score = (w["amount"] * amount + w["date"] * date_comp + w["counterparty"] * cp
               + w["taxcode"] * tc + w["cardinality"] * card + w["uniqueness"] * uniq)
    return r


def band_for(cfg: LoadedConfig, score: float) -> str:
    b = cfg.engine["confidence_bands"]
    if score >= b["high"]:
        return "HIGH"
    if score >= b["medium"]:
        return "MEDIUM"
    return "LOW"
