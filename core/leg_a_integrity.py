"""Leg A - within-document integrity (spec §7).

Runs on GL only. Groups lines by entity + fiscal_year + accounting_doc_id and
checks that gross reconciles to net + tax + explained residual. This is a
GROUP BY, not a match: it runs first and never fails to join.

Uses DuckDB for the aggregation to stay consistent with the rule-pack SQL style.
"""
from __future__ import annotations

from decimal import Decimal

import duckdb

from .config import LoadedConfig
from . import classify


def run(cfg: LoadedConfig, gl_lines: list[dict]) -> dict:
    """Return {accounting_doc_key: integrity_record}."""
    if not gl_lines:
        return {}

    con = duckdb.connect(database=":memory:")
    rows = [
        {
            "entity_id": ln["entity_id"],
            "fiscal_year": ln["fiscal_year"],
            "accounting_doc_id": ln["accounting_doc_id"],
            "account_class": ln["account_class"],
            "amount_minor": int(ln["amount_minor"]),
            "tax_code": ln["tax_code"],
        }
        for ln in gl_lines
    ]
    con.register("gl", _as_arrow(rows))

    rev_classes = "('" + "','".join(sorted(classify.REVENUE_CLASSES)) + "')"
    exp_classes = "('" + "','".join(sorted(classify.EXPLAINED_CLASSES)) + "')"

    agg = con.execute(f"""
        SELECT
          entity_id, fiscal_year, accounting_doc_id,
          SUM(CASE WHEN account_class = 'CUSTOMER_CONTROL' THEN amount_minor ELSE 0 END) AS customer_side,
          SUM(CASE WHEN account_class = 'BANK' THEN amount_minor ELSE 0 END) AS bank_side,
          SUM(CASE WHEN account_class IN {rev_classes} THEN amount_minor ELSE 0 END) AS revenue_side,
          SUM(CASE WHEN account_class = 'TAX_OUTPUT' THEN amount_minor ELSE 0 END) AS tax_side,
          SUM(CASE WHEN account_class IN {exp_classes} THEN amount_minor ELSE 0 END) AS explained_side,
          COUNT(*) AS line_count
        FROM gl
        GROUP BY entity_id, fiscal_year, accounting_doc_id
    """).fetchall()

    tol_per_line = cfg.rounding_abs_minor_per_doc
    out = {}
    for (entity, fy, acc_doc, cust, bank, rev, tax, expl, n) in agg:
        # Signed accounting identity: for a balanced voucher the classified
        # buckets net to the negative of anything left in unclassified (OTHER)
        # accounts, so a non-zero residual is exactly the unexplained amount.
        # This absorbs WHT / rounding / discount / freight with either sign,
        # which the plain absolute-value form (spec §7) does not.
        residual = cust + bank + rev + tax + expl
        tol = tol_per_line * n
        status = "OK" if abs(residual) <= tol else "UNEXPLAINED"

        implied_rate = None
        rate_status = None
        if rev != 0:
            implied_rate = Decimal(abs(tax)) / Decimal(abs(rev))
        key = (entity, fy, acc_doc)
        out[key] = {
            "entity_id": entity,
            "fiscal_year": fy,
            "accounting_doc_id": acc_doc,
            "customer_side": int(cust),
            "bank_side": int(bank),
            "revenue_side": int(rev),
            "tax_side": int(tax),
            "explained_side": int(expl),
            "line_count": int(n),
            "residual_minor": int(residual),
            "tolerance_minor": int(tol),
            "status": status,
            "implied_rate": str(implied_rate) if implied_rate is not None else None,
        }
    con.close()
    return out


def check_implied_rate(cfg: LoadedConfig, integ: dict) -> None:
    """Annotate each integrity record with IMPLIED_RATE_DEVIATION if the
    implied output-tax rate strays from any pack rate beyond 0.1 percentage pt."""
    pack_rates = [Decimal(str(r["rate"])) for r in cfg.country.get("tax_rates", [])
                  if r.get("category") == "STANDARD"]
    for rec in integ.values():
        rec["rate_flag"] = None
        if rec["implied_rate"] is None or not pack_rates:
            continue
        ir = Decimal(rec["implied_rate"])
        if ir == 0:
            continue
        if all(abs(ir - pr) > Decimal("0.001") for pr in pack_rates):
            rec["rate_flag"] = "IMPLIED_RATE_DEVIATION"


def _as_arrow(rows: list[dict]):
    import pandas as pd
    return pd.DataFrame(rows)
