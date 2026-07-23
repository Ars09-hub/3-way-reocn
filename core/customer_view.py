"""Customer view (spec page 5). Grouped by customer, sorted by unreported value.

Uses customer_vat_number where valid, customer_name otherwise. Derived from the
three-way events so the customer totals reconcile to the transaction pages.
"""
from __future__ import annotations

import pandas as pd

from core import normalize as nz

RISK_STATUSES = ("Not e-invoiced", "Not booked", "Reconciled with differences",
                 "Billed but no revenue posted", "Revenue posted, not billed")


def build(threeway: dict, ksa: dict) -> pd.DataFrame:
    df = threeway["events"].copy()
    if not len(df):
        return df

    def keyname(row):
        vat = str(row["customer_vat"]) if row["customer_vat"] else ""
        if nz.is_valid_tin(vat, ksa["tin"]):
            return vat
        return row["customer_name"] if pd.notna(row["customer_name"]) and str(row["customer_name"]).strip() else "(no customer)"

    df["cust_key"] = df.apply(keyname, axis=1)

    rows = []
    for key, g in df.groupby("cust_key", sort=False):
        name = next((n for n in g["customer_name"] if pd.notna(n) and str(n).strip()), key)
        vat = next((v for v in g["customer_vat"] if v and nz.is_valid_tin(str(v), ksa["tin"])), "")

        def cv(status):
            s = g[g["status"] == status]
            return len(s), int(s["taxable_h"].sum())

        fr_n, fr_v = cv("Fully reconciled")
        ne_n, ne_v = cv("Not e-invoiced")
        nb_n, nb_v = cv("Not booked")
        diff = g[g["status"] == "Reconciled with differences"]
        diff_n, diff_v = len(diff), int(diff["taxable_h"].sum())

        risk = g[g["status"].isin(RISK_STATUSES)].copy()
        if len(risk):
            risk["absv"] = risk["taxable_h"].abs()
            top = risk.sort_values("absv", ascending=False).iloc[0]
            ref = top["voucher_number"] if pd.notna(top["voucher_number"]) else top["document_number"]
            highest = f"{top['status']}: {ref}"
        else:
            highest = "None"

        rows.append({
            "customer_key": key, "customer_name": name, "customer_vat": vat,
            "vouchers": len(g), "taxable_h": int(g["taxable_h"].sum()),
            "vat_h": int(g["vat_h"].sum()),
            "fully_reconciled_n": fr_n, "fully_reconciled_v": fr_v,
            "not_einvoiced_n": ne_n, "not_einvoiced_v": ne_v,
            "not_booked_n": nb_n, "not_booked_v": nb_v,
            "differences_n": diff_n, "differences_v": diff_v,
            "unreported_v": ne_v + nb_v, "highest_risk": highest,
        })

    out = pd.DataFrame(rows)
    out["_sort"] = out["unreported_v"].abs()
    out = out.sort_values(["_sort", "taxable_h"], ascending=[False, False]).drop(columns="_sort")
    return out.reset_index(drop=True)
