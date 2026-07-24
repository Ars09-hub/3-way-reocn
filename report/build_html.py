"""Render the single self-contained recon HTML from the UI shell (spec 5).

The shell's style and script blocks are kept verbatim (report/_style_block.html,
report/_script_block.html). Only the PLACEHOLDER content is replaced with computed
values. No restyling, no colours outside :root, no em dashes in copy.
"""
from __future__ import annotations

import html
import json
import os

import pandas as pd

from core.normalize import halalas_to_str as H

HERE = os.path.dirname(os.path.abspath(__file__))

# Supplementary CSS: new classes only, for the filter bar, sub-tabs and the
# column-mode toggle (addendum section 8). Colours come from existing tokens.
DETAIL_CSS = """
<style>
.dd-filterbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:12px;
  background:var(--card);border:1px solid var(--border);border-radius:10px;padding:11px 16px;margin-bottom:14px}
.dd-fb-text{font-size:13px;color:var(--tp)}
.dd-fb-actions{margin-left:auto;display:flex;gap:8px}
.dd-btn{font:500 12px Inter,system-ui;padding:6px 12px;border:1px solid var(--border);
  border-radius:8px;background:var(--card);color:var(--tp);cursor:pointer}
.dd-btn:hover{background:var(--hover);border-color:var(--border-strong)}
.dd-subtabs{display:flex;gap:2px;border-bottom:1px solid var(--border);margin-bottom:14px}
.dd-subtab{background:none;border:none;color:var(--ts);padding:9px 16px;font:500 12.5px Inter,system-ui;
  cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.dd-subtab:hover{color:var(--tp)}
.dd-subtab.on{color:var(--tp);border-bottom-color:var(--tp)}
.dd-count{color:var(--tm);font-variant-numeric:tabular-nums}
.dd-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.dd-controls input{font:400 12.5px Inter,system-ui;padding:7px 10px;border:1px solid var(--border);
  border-radius:8px;background:var(--card);color:var(--tp);min-width:240px}
.dd-controls input:focus{outline:none;border-color:var(--border-strong)}
.dd-rowcount{font-size:12px;color:var(--tm);font-variant-numeric:tabular-nums;margin-left:auto}
.dd-note{font-size:12px;color:var(--ts);margin:0 0 10px}
.dd-empty{padding:28px;text-align:center;color:var(--tm);font-size:13px;
  background:var(--card);border:1px solid var(--border);border-radius:12px}
[data-drill]{cursor:pointer}
[data-drill]:hover .mcard-value,[data-drill]:hover .mcard-label,
[data-drill]:hover .strip-count,[data-drill]:hover .strip-label,
[data-drill]:hover .big,[data-drill]:hover .label,
.badge[data-drill]:hover,[data-drill]:hover .cust-link{text-decoration:underline}
.cust-link{cursor:pointer}
</style>
"""

BADGE = {
    "Exact match": "ok", "Fully reconciled": "ok",
    "Amount mismatch": "warn", "Reconciled with differences": "warn",
    "Needs review": "warn", "Suggested combination": "info",
    "Missing in AR": "bad", "Missing in GL": "bad", "Missing in e-invoice": "bad",
    "Not e-invoiced": "bad", "Not booked": "bad", "Submitted but not accepted": "bad",
    "Billed but no revenue posted": "warn", "Revenue posted, not billed": "warn",
    "Out of scope by design": "neutral", "Out of period": "neutral", "Not a supply": "neutral",
}


def esc(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return html.escape(str(s))


def sar(h) -> str:
    return "SAR " + H(int(h) if h is not None and not (isinstance(h, float) and pd.isna(h)) else 0)


def badge(label) -> str:
    return f'<span class="badge {BADGE.get(label, "neutral")}">{esc(label)}</span>'


def dot(kind) -> str:
    return f'<span class="dot {kind}"></span>'


def _mcard(label, value, cls, note, drill=None) -> str:
    attr = f' class="mcard drillable" data-drill="{esc(drill)}"' if drill else ' class="mcard"'
    return (f'<div{attr}><div class="mcard-label">{esc(label)}</div>'
            f'<div class="mcard-value {cls}">{esc(value)}</div>'
            f'<div class="mcard-note">{esc(note)}</div></div>')


def present(state) -> str:
    m = {"Yes": ("y", "Yes"), "No": ("n", "No"), "Not accepted": ("p", "Not accepted")}
    k, t = m.get(state, ("x", state))
    return f'<span class="present">{dot(k)}{esc(t)}</span>'


def _date(d) -> str:
    if d is None or pd.isna(d):
        return ""
    return pd.Timestamp(d).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- summary prep

def prep(R: dict) -> dict:
    tw = R["threeway"]["events"]
    per = R["period"]
    supplies = tw[~tw["status"].isin(["Out of scope by design", "Not a supply"])]

    def sv(status_list):
        s = tw[tw["status"].isin(status_list)]
        return len(s), int(s["taxable_h"].sum())

    fr_n, fr_v = sv(["Fully reconciled"])
    ne_n, ne_v = sv(["Not e-invoiced"])
    nb_n, nb_v = sv(["Not booked"])
    diff_n, diff_v = sv(["Reconciled with differences"])
    oos_n, oos_v = sv(["Out of scope by design"])
    na_row = R["leg2"]["einv_rows"]
    not_accepted = na_row[na_row["category"] == "Submitted but not accepted"] if len(na_row) else na_row
    na_n = len(not_accepted)
    na_v = int(not_accepted["einv_taxable_h"].sum()) if na_n else 0

    entity = ""
    if "company_name" in R["ar"].columns:
        names = R["ar"]["company_name"].dropna().astype(str)
        entity = names.iloc[0] if len(names) else ""

    return {
        "entity": entity or "Entity",
        "from": _date(per["from"]), "to": _date(per["to"]),
        "period_label": f"{_date(per['from'])} to {_date(per['to'])}",
        "in_scope_taxable": int(supplies["taxable_h"].sum()),
        "in_scope_vat": int(supplies["vat_h"].sum()),
        "in_scope_vouchers": len(supplies),
        "fr_n": fr_n, "fr_v": fr_v, "ne_n": ne_n, "ne_v": ne_v,
        "nb_n": nb_n, "nb_v": nb_v, "diff_n": diff_n, "diff_v": diff_v,
        "oos_n": oos_n, "oos_v": oos_v, "na_n": na_n, "na_v": na_v,
        "n_vouchers": len(supplies), "n_einv_in": R["leg2"]["counts"].get("Exact match", 0)
        + R["leg2"]["counts"].get("Amount mismatch", 0),
        "n_out_of_period_ei": R["leg2"]["counts"].get("Out of period", 0),
        "n_out_of_period_docs": _out_of_period_docs(R),
    }


def _out_of_period_docs(R):
    per = R["period"]; frm, to = per["from"], per["to"]
    ar = R["ar"]; gl = R["gl"]; ei = R["ei"]
    aoop = ((ar["voucher_date_d"] < frm) | (ar["voucher_date_d"] > to)).sum()
    goop = ((gl["voucher_date_d"] < frm) | (gl["voucher_date_d"] > to)).sum()
    ns = ei[~ei["is_test"]]
    eoop = ((ns["issue_date_d"] < frm) | (ns["issue_date_d"] > to)).sum()
    return int(aoop + goop + eoop)


# ------------------------------------------------------------------- page 1

def page1(R, S):
    headline = (f"{S['ne_n']} sales vouchers worth {sar(S['ne_v'])} were billed to customers "
                f"but not reported to ZATCA in the reconciled period.")
    if S["nb_n"]:
        headline += (f" A further {S['nb_n']} e-invoices worth {sar(S['nb_v'])} were reported "
                     f"but have no accounting entry.")
    cards = [
        ("Sales value in scope", sar(S["in_scope_taxable"]), "", f"Taxable value, {S['in_scope_vouchers']} vouchers", "exec.sales_in_scope"),
        ("VAT in scope", sar(S["in_scope_vat"]), "", "Output VAT", "exec.vat_in_scope"),
        ("Fully reconciled", str(S["fr_n"]), "g", sar(S["fr_v"]), "exec.fully_reconciled"),
        ("Not e-invoiced", str(S["ne_n"]), "r", f"{sar(S['ne_v'])} of taxable value", "exec.not_einvoiced"),
        ("Not booked", str(S["nb_n"]), "r", sar(S["nb_v"]), "exec.not_booked"),
        ("Submitted, not accepted", str(S["na_n"]), "a", f"Failed or not submitted, {sar(S['na_v'])}", "exec.submitted_not_accepted"),
        ("Differences to review", str(S["diff_n"]), "a", f"{sar(S['diff_v'])} net", "exec.differences"),
        ("Out of scope by design", str(S["oos_n"]), "", "Interest, forex, intercompany", "exec.out_of_scope"),
    ]
    card_html = "".join(_mcard(l, v, c, n, drill) for l, v, c, n, drill in cards)

    # largest open items
    tw = R["threeway"]["events"].copy()
    risk = tw[tw["status"].isin(["Not e-invoiced", "Not booked", "Submitted but not accepted",
                                 "Reconciled with differences", "Revenue posted, not billed"])].copy()
    risk["absv"] = risk["taxable_h"].abs()
    risk = risk.sort_values("absv", ascending=False).head(12)
    rows = ""
    for _, r in risk.iterrows():
        ref = r["voucher_number"] if pd.notna(r["voucher_number"]) else r["document_number"]
        rows += (f'<tr><td class="mono">{esc(ref)}</td><td>{_date(r["date"])}</td>'
                 f'<td class="wrapcell">{esc(r["customer_name"])}</td>'
                 f'<td class="num">{H(r["taxable_h"])}</td><td class="num">{H(r["vat_h"])}</td>'
                 f'<td>{badge(r["status"])}</td><td class="wrapcell">{esc(r["action"])}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="7" class="muted" style="padding:20px">No open items</td></tr>'

    return f"""
    <div class="briefing">
      <div class="briefing-label">Summary</div>
      <p class="briefing-lead">{esc(headline)}</p>
      <p class="briefing-sub">Reconciled {S['in_scope_vouchers']} vouchers and {S['n_einv_in']} e-invoices for
         {S['from']} to {S['to']}. {S['n_out_of_period_docs']} documents fall outside this window and are
         listed separately on the data quality page.</p>
    </div>
    <div class="main">
      <div class="section"><div class="card-grid">{card_html}</div></div>
      <div class="section">
        <div class="section-eyebrow">Largest open items</div>
        <h2 class="section-headline">What to look at first</h2>
        <p class="section-sub">Ranked by value at risk.</p>
        <div class="tablewrap"><table class="dt">
          <thead><tr><th>Document</th><th>Date</th><th>Customer</th>
            <th class="num">Taxable value</th><th class="num">VAT</th>
            <th>Issue</th><th>What to do next</th></tr></thead>
          <tbody>{rows}</tbody>
        </table></div>
      </div>
    </div>"""


# ------------------------------------------------------------------- page 2

def _strip_cell(label, dot_kind, count, value, first=False, drill=None):
    d = dot(dot_kind) if dot_kind else ""
    on = " on" if first else ""
    fkey = "all" if first else label
    da = f' data-drill="{esc(drill)}"' if drill else ""
    return (f'<div class="strip-cell{on}" data-f="{esc(fkey)}"{da}><div class="strip-label">{d}{esc(label)}</div>'
            f'<div class="strip-count">{count}</div><div class="strip-value">{sar(value)}</div></div>')


def page2(R):
    leg1 = R["leg1"]
    c, v = leg1["counts"], leg1["values"]
    total_n = sum(c.values()); total_v = sum(v.values())
    strip = _strip_cell("All", "", total_n, total_v, first=True, drill="leg1.all")
    dots = {"Exact match": "y", "Amount mismatch": "p", "Missing in AR": "n",
            "Missing in GL": "n", "Out of scope by design": "x"}
    drills = {"Exact match": "leg1.exact_match", "Amount mismatch": "leg1.amount_mismatch",
              "Missing in AR": "leg1.missing_in_ar", "Missing in GL": "leg1.missing_in_gl",
              "Out of scope by design": "leg1.out_of_scope"}
    for cat in leg1["order"]:
        strip += _strip_cell("Out of scope" if cat == "Out of scope by design" else cat,
                             dots[cat], c[cat], v[cat], drill=drills[cat])

    rows = ""
    df = leg1["rows"].sort_values(["category", "grain_key"])
    for _, r in df.iterrows():
        dt = r["diff_taxable_h"]; dtx = r["diff_tax_h"]
        dcls = "zero" if (pd.isna(dt) or dt == 0) else "pos"
        rows += (f'<tr class="expandable">'
                 f'<td class="mono">{esc(r["voucher_number"])}</td><td class="mono">{esc(r["document_number"])}</td>'
                 f'<td>{esc(r["document_type"])}</td><td>{_date(r["voucher_date"])}</td><td>{_date(r["document_date"])}</td>'
                 f'<td class="wrapcell">{esc(r["customer_name"])}</td><td class="mono">{esc(r["customer_vat"])}</td>'
                 f'<td class="num grp">{_h(r["gl_taxable_h"])}</td><td class="num">{_h(r["gl_tax_h"])}</td>'
                 f'<td class="num grp">{_h(r["ar_taxable_h"])}</td><td class="num">{_h(r["ar_vat_h"])}</td><td class="num">{_h(r["ar_gross_h"])}</td>'
                 f'<td class="num grp delta {dcls}">{_h(dt)}</td><td class="num delta {dcls}">{_h(dtx)}</td>'
                 f'<td>{esc(r["tax_code"])} {esc(_rate(r["tax_rate"]))}</td><td>{badge(r["category"])}</td></tr>')
    return f"""
    <div class="main">
      <div class="section-eyebrow">Leg 1</div>
      <h2 class="section-headline">Revenue and tax GL compared to customer GL</h2>
      <p class="section-sub">Matched on company code, fiscal year, voucher number and voucher date.
         Every voucher reduced to one record before comparison.</p>
      <div class="strip">{strip}</div>
      <div class="filters">
        <input type="text" placeholder="Search voucher, document or customer">
        <span class="filter-note">Showing {len(df)} of {len(df)} vouchers</span>
      </div>
      <div class="tablewrap"><table class="dt">
        <thead><tr><th>Voucher</th><th>Document</th><th>Type</th><th>Voucher date</th><th>Document date</th>
          <th>Customer</th><th>Customer VAT</th>
          <th class="num grp">GL taxable</th><th class="num">GL tax</th>
          <th class="num grp">AR taxable</th><th class="num">AR VAT</th><th class="num">AR gross</th>
          <th class="num grp">Diff taxable</th><th class="num">Diff tax</th>
          <th>Tax code</th><th>Status</th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
    </div>"""


def _h(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return '<span class="muted">-</span>'
    return H(int(v))


def _rate(r):
    if r is None or (isinstance(r, float) and pd.isna(r)):
        return ""
    try:
        return f"{float(r):.0f}%"
    except (TypeError, ValueError):
        return esc(r)


# ------------------------------------------------------------------- page 3

def page3(R):
    leg2 = R["leg2"]
    c = leg2["counts"]
    strip = _strip_cell("All", "", sum(c.values()), 0, first=True, drill="leg2.all")
    dmap = [("Exact match", "y", "leg2.exact_match"), ("Amount mismatch", "p", "leg2.amount_mismatch"),
            ("Missing in e-invoice", "n", "leg2.missing_in_einvoice"), ("Missing in AR", "n", "leg2.missing_in_ar"),
            ("Submitted but not accepted", "n", "leg2.not_accepted"),
            ("Suggested combination", "p", "leg2.suggested"), ("Out of period", "x", "leg2.out_of_period")]
    for label, dk, drill in dmap:
        strip += _strip_cell(label, dk, c.get(label, 0), 0, drill=drill)

    rows = ""
    er = leg2["einv_rows"].sort_values(["category", "einv_no"]) if len(leg2["einv_rows"]) else leg2["einv_rows"]
    for _, r in er.iterrows():
        errs = ""
        if r["category"] == "Submitted but not accepted" and r.get("errors"):
            items = "".join(f"<li>{esc(e)}</li>" for e in r["errors"]) or "<li>No error text</li>"
            errs = f'<ul class="errlist">{items}</ul>'
        arv = r.get("ar_voucher"); arv = esc(arv) if pd.notna(arv) else '<span class="muted">not found</span>'
        rows += (f'<tr><td class="mono">{esc(r["einv_no"])}</td><td>{_date(r["issue_date"])}</td>'
                 f'<td>{esc(r["doc_type"])}</td><td>{esc(r["txn_type"])}</td><td>{badge_status(r["status"])}</td>'
                 f'<td class="wrapcell">{esc(r["buyer_name"])}{errs}</td><td class="mono">{esc(r["buyer_vat"])}</td>'
                 f'<td class="num grp">{_h(r["einv_taxable_h"])}</td><td class="num">{_h(r["einv_vat_h"])}</td><td class="num">{_h(r["einv_total_h"])}</td>'
                 f'<td class="grp">{arv}</td><td class="num">{_h(r.get("ar_taxable_h"))}</td><td class="num">{_h(r.get("ar_vat_h"))}</td><td class="num">{_h(r.get("ar_gross_h"))}</td>'
                 f'<td class="num grp">{_h(r.get("diff_taxable_h"))}</td><td class="num">{_h(r.get("diff_vat_h"))}</td>'
                 f'<td class="muted">{esc(r["matched_how"])}</td><td>{badge(r["category"])}</td></tr>')

    combos = _combo_blocks(R)
    return f"""
    <div class="main">
      <div class="section-eyebrow">Leg 2</div>
      <h2 class="section-headline">E-invoice compared to customer GL</h2>
      <p class="section-sub">Matched on document number first, then on customer VAT, amount and date,
         then by combination search. Standard and export invoices are expected to reach CLEARED.
         Simplified invoices are expected to reach REPORTED.</p>
      <div class="strip">{strip}</div>
      <div class="filters">
        <input type="text" placeholder="Search e-invoice number, voucher or buyer">
        <span class="filter-note">Showing {len(er)} of {len(er)} documents</span>
      </div>
      <div class="tablewrap"><table class="dt">
        <thead><tr><th>E-invoice no</th><th>Issue date</th><th>Type</th><th>Transaction type</th><th>Status</th>
          <th>Buyer</th><th>Buyer VAT</th>
          <th class="num grp">E-inv taxable</th><th class="num">E-inv VAT</th><th class="num">E-inv total</th>
          <th class="grp">AR voucher</th><th class="num">AR taxable</th><th class="num">AR VAT</th><th class="num">AR gross</th>
          <th class="num grp">Diff taxable</th><th class="num">Diff VAT</th>
          <th>How matched</th><th>Status</th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
      <div class="section" style="margin-top:28px">
        <div class="section-eyebrow">Suggested combinations</div>
        <h2 class="section-headline">Where documents do not match one to one</h2>
        <p class="section-sub">These are proposals, not conclusions. Accept only after checking.</p>
        {combos}
      </div>
    </div>"""


def badge_status(status):
    ok = {"CLEARED": "ok", "REPORTED": "ok"}
    bad = {"FAILED": "bad", "NOT_SUBMITTED": "bad"}
    cls = ok.get(str(status)) or bad.get(str(status)) or "neutral"
    return f'<span class="badge {cls}">{esc(status)}</span>'


def _combo_blocks(R):
    items = R["leg2"]["suggested"] + R["leg2"]["ambiguous"]
    if not items:
        return '<p class="section-sub muted">No combinations were suggested inside the reconciled window.</p>'
    out = ""
    for it in items:
        combo = it["combo"]
        if combo["n_alternatives"] > 1:
            out += (f'<div class="combo"><div class="combo-head"><span class="mono">{esc(it["einv_no"])}</span>'
                    f'{badge("Needs review")}<span class="muted">{combo["n_alternatives"]} combinations fit equally well, none selected</span>'
                    f'<span class="amt">{sar(it["einv_total_h"])}</span></div>'
                    f'<div class="combo-body"><div class="combo-row muted">Showing the first three of {combo["n_alternatives"]} possibilities</div></div></div>')
        else:
            rows = "".join(f'<div class="combo-row"><span class="mono">{esc(x)}</span><span class="amt">-</span></div>'
                           for x in combo["indices"])
            out += (f'<div class="combo"><div class="combo-head"><span class="mono">{esc(it["einv_no"])}</span>'
                    f'{badge("Suggested combination")}<span class="muted">1 e-invoice to {combo["n_docs"]} AR vouchers</span>'
                    f'<span class="amt">{sar(it["einv_total_h"])}</span></div>'
                    f'<div class="combo-body">{rows}'
                    f'<div class="combo-total"><span>Total</span><span class="amt">{sar(combo["group_gross_h"])}</span></div>'
                    f'<div class="combo-diff"><span>Difference</span><span class="amt">{sar(combo["group_gross_h"]-it["einv_total_h"])}</span></div></div></div>')
    return out


# ------------------------------------------------------------------- page 4

def _tw_slug(status):
    import re as _re
    return "threeway.status." + _re.sub(r"[^a-z]+", "_", status.lower()).strip("_")


def page4(R):
    tw = R["threeway"]; flow = tw["flow"]
    fl = (f'<div class="flow">'
          f'<div class="flow-col" data-drill="threeway.flow_gl"><div class="label">Revenue and tax GL</div><div class="big">{flow["gl"]["n"]}</div><div class="sub">{sar(flow["gl"]["value_h"])}</div></div>'
          f'<div class="flow-arrow">&rarr;</div>'
          f'<div class="flow-col" data-drill="threeway.flow_ar"><div class="label">Customer GL</div><div class="big">{flow["ar"]["n"]}</div><div class="sub">{sar(flow["ar"]["value_h"])}</div></div>'
          f'<div class="flow-arrow">&rarr;</div>'
          f'<div class="flow-col" data-drill="threeway.flow_einv"><div class="label">E-invoice reported</div><div class="big">{flow["einv"]["n"]}</div><div class="sub">{sar(flow["einv"]["value_h"])}</div></div></div>')
    rows = ""
    df = tw["events"].sort_values(["status", "grain_key", "document_number"], na_position="last")
    for _, r in df.iterrows():
        status_cell = f'<span data-drill="{_tw_slug(r["status"])}">{badge(r["status"])}</span>'
        rows += (f'<tr><td class="mono">{esc(r["voucher_number"])}</td><td class="mono">{esc(r["document_number"])}</td>'
                 f'<td>{_date(r["date"])}</td><td class="wrapcell">{esc(r["customer_name"])}</td><td class="mono">{esc(r["customer_vat"])}</td>'
                 f'<td>{present("Yes" if r["in_gl"] else "No")}</td><td>{present("Yes" if r["in_ar"] else "No")}</td>'
                 f'<td>{present(r["einvoice"])}</td>'
                 f'<td class="num">{H(r["taxable_h"])}</td><td class="num">{H(r["vat_h"])}</td>'
                 f'<td>{status_cell}</td><td class="wrapcell">{esc(r["action"])}</td></tr>')
    return f"""
    <div class="main">
      <div class="section-eyebrow">Combined view</div>
      <h2 class="section-headline">Three-way assessment</h2>
      <p class="section-sub">Derived from the two comparisons above. One row per economic event.</p>
      {fl}
      <div class="filters"><input type="text" placeholder="Search voucher, document or customer">
        <span class="filter-note">Showing {len(df)} of {len(df)} events</span></div>
      <div class="tablewrap"><table class="dt">
        <thead><tr><th>Voucher</th><th>Document</th><th>Date</th><th>Customer</th><th>Customer VAT</th>
          <th>Revenue/tax GL</th><th>Customer GL</th><th>E-invoice</th>
          <th class="num">Taxable value</th><th class="num">VAT</th>
          <th>Three-way status</th><th>What to do next</th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
    </div>"""


# ------------------------------------------------------------------- page 5

def page5(R):
    cv = R["customers"]
    rows = ""
    for i, r in cv.iterrows():
        b = f"customer.{i}"
        rows += (f'<tr><td class="wrapcell"><span class="cust-link" data-drill="{b}.all">{esc(r["customer_name"])}</span></td>'
                 f'<td class="mono">{esc(r["customer_vat"])}</td>'
                 f'<td class="num">{r["vouchers"]}</td><td class="num">{H(r["taxable_h"])}</td><td class="num">{H(r["vat_h"])}</td>'
                 f'<td class="num grp" data-drill="{b}.fully_reconciled">{r["fully_reconciled_n"]}</td>'
                 f'<td class="num" data-drill="{b}.not_einvoiced">{r["not_einvoiced_n"]}</td>'
                 f'<td class="num" data-drill="{b}.not_booked">{r["not_booked_n"]}</td>'
                 f'<td class="num" data-drill="{b}.differences">{r["differences_n"]}</td>'
                 f'<td class="wrapcell">{esc(r["highest_risk"])}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="10" class="muted" style="padding:20px">No customers</td></tr>'
    return f"""
    <div class="main">
      <div class="section-eyebrow">By counterparty</div>
      <h2 class="section-headline">Customer view</h2>
      <p class="section-sub">Sorted by unreported value. Highest risk item shown per customer.</p>
      <div class="tablewrap"><table class="dt">
        <thead><tr><th>Customer</th><th>Customer VAT</th><th class="num">Vouchers</th>
          <th class="num">Taxable value</th><th class="num">VAT</th>
          <th class="num grp">Fully reconciled</th><th class="num">Not e-invoiced</th>
          <th class="num">Not booked</th><th class="num">Differences</th>
          <th>Highest risk item</th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
    </div>"""


# ------------------------------------------------------------------- page 6

def page6(R):
    q = R["quality"]; per = R["period"]
    ranges = per["ranges"]
    excl = q["excluded"]
    cards = [
        ("Reconciled window", f'{_date(per["from"])} to {_date(per["to"])}', "", "Common period across all three files", None),
        ("Out of period", str(_count(q, "Out of period")), "a", "Excluded from all exposure figures", "dq.out_of_period"),
        ("Test data quarantined", str(_count(q, "Test data quarantined")), "a", "Document numbers matching test patterns", "dq.test_data"),
        ("Duplicate submissions", str(_count(q, "Duplicate submissions")), "a", "Same document number, multiple attempts", "dq.duplicate"),
        ("Invalid VAT numbers", str(_count(q, "Invalid VAT numbers")), "a", "Not a valid 15 digit KSA TIN", "dq.invalid_vat"),
        ("Missing VAT numbers", str(_count(q, "Missing VAT numbers")), "a", "Blank on the customer record", "dq.missing_vat"),
        ("Excluded accounts", str(excl["gl"]["rows"] + excl["ar"]["rows"]), "", "Interest, forex, intercompany, deferred", "dq.excluded"),
        ("Unclassified rows", str(_count(q, "Unclassified rows")), "a", "Null gl_classification, sent to review", "dq.unclassified"),
    ]
    card_html = ""
    for l, v, c, n, drill in cards:
        style = ' style="font-size:15px"' if l == "Reconciled window" else ""
        da = f' drillable" data-drill="{drill}' if drill else ""
        card_html += (f'<div class="mcard{da}"><div class="mcard-label">{esc(l)}</div>'
                      f'<div class="mcard-value {c}"{style}>{esc(v)}</div><div class="mcard-note">{esc(n)}</div></div>')

    dq_ids = {"Out of period": "dq.out_of_period", "Test data quarantined": "dq.test_data",
              "Duplicate submissions": "dq.duplicate", "Invalid VAT numbers": "dq.invalid_vat",
              "Missing VAT numbers": "dq.missing_vat", "Unclassified rows": "dq.unclassified",
              "VAT output with no revenue line": "dq.vat_no_revenue", "Excluded accounts": "dq.excluded"}
    detail = ""
    for chk in q["checks"]:
        did = dq_ids.get(chk["check"])
        da = f' data-drill="{did}"' if did else ""
        detail += (f'<tr{da}><td>{esc(chk["check"])}</td><td class="num">{chk["rows"]}</td>'
                   f'<td class="num">{H(chk["value_h"])}</td><td class="wrapcell">{esc(chk["effect"])}</td>'
                   f'<td class="wrapcell muted">{esc(chk["examples"])}</td></tr>')
    decisions = "".join(f"<li>{esc(d['text'])}</li>" for d in q["open_decisions"])
    return f"""
    <div class="main">
      <div class="section-eyebrow">Before you trust the numbers</div>
      <h2 class="section-headline">Data quality</h2>
      <p class="section-sub">Everything that would otherwise look like a reconciliation break.</p>
      <div class="card-grid" style="margin-bottom:22px">{card_html}</div>
      <div class="section">
        <div class="section-eyebrow">Detail</div>
        <div class="tablewrap"><table class="dt">
          <thead><tr><th>Check</th><th class="num">Rows</th><th class="num">Value</th>
            <th>Effect on the reconciliation</th><th>Examples</th></tr></thead>
          <tbody>{detail}</tbody>
        </table></div>
      </div>
      <div class="section">
        <div class="section-eyebrow">Open decisions</div>
        <h2 class="section-headline">Questions for the client, not resolved here</h2>
        <ul class="errlist" style="color:var(--ts);max-width:820px">{decisions}</ul>
      </div>
    </div>"""


def _count(q, name):
    for c in q["checks"]:
        if c["check"] == name:
            return c["rows"]
    return 0


# ------------------------------------------------------------------- page 7

def page7(R):
    return """
    <div class="main">
      <div class="section-eyebrow">All source rows</div>
      <h2 class="section-headline">Document detail</h2>
      <p class="section-sub">The underlying rows of all three datasets in their native form. Click any
         figure on another page to open this page filtered to exactly the documents behind it.</p>
      <div class="dd-filterbar" id="dd-filterbar">
        <span class="dd-fb-text">Showing all documents</span>
        <div class="dd-fb-actions">
          <button class="dd-btn dd-clear" id="dd-clear" style="display:none">Clear filter</button>
          <button class="dd-btn dd-back" id="dd-back" style="display:none">Back</button>
        </div>
      </div>
      <div class="dd-subtabs">
        <button class="dd-subtab on" id="dd-subtab-gl">GL register <span class="dd-count"></span></button>
        <button class="dd-subtab" id="dd-subtab-ar">Sales register <span class="dd-count"></span></button>
        <button class="dd-subtab" id="dd-subtab-ei">E-invoice <span class="dd-count"></span></button>
      </div>
      <div class="dd-controls">
        <input type="text" id="dd-search" placeholder="Search displayed columns">
        <button class="dd-btn" id="dd-grain" style="display:none">Voucher level</button>
        <button class="dd-btn" id="dd-colmode">All columns</button>
        <button class="dd-btn" id="dd-export">Export CSV</button>
        <span class="dd-rowcount" id="dd-rowcount"></span>
      </div>
      <div id="dd-body"></div>
    </div>"""


def _recon_payload(R):
    """window.RECON = { gl:[rows], ar:[rows], ei:[rows], meta:{...}, drill:{...} }."""
    d = R["detail"]
    out = {"meta": {}, "drill": R["registry"]}
    for name in ("gl", "ar", "ei"):
        ds = d[name]
        out[name] = ds["rows"]
        out["meta"][name] = {
            "essential": ds["essential"], "all": ds["all"], "numeric": ds["numeric"],
            "tooltips": ds["tooltips"], "total": ds["total"],
            "doclevel_labels": ds.get("doclevel_labels", []),
        }
    return out


# ------------------------------------------------------------------- assemble

def build(R: dict, out_path: str) -> str:
    with open(os.path.join(HERE, "_style_block.html"), encoding="utf-8") as fh:
        style = fh.read()
    with open(os.path.join(HERE, "_script_block.html"), encoding="utf-8") as fh:
        script = fh.read()
    with open(os.path.join(HERE, "detail.js"), encoding="utf-8") as fh:
        detail_js = fh.read()
    S = prep(R)

    tabs = [("p1", "Executive summary"), ("p2", "GL vs AR"), ("p3", "E-invoice vs AR"),
            ("p4", "Three-way assessment"), ("p5", "Customer view"), ("p6", "Data quality"),
            ("p7", "Document detail")]
    tabbar = "".join(f'<button class="tab{" on" if i == 0 else ""}" data-p="{p}">{t}</button>'
                     for i, (p, t) in enumerate(tabs))

    pages = [("p1", page1(R, S)), ("p2", page2(R)), ("p3", page3(R)),
             ("p4", page4(R)), ("p5", page5(R)), ("p6", page6(R)), ("p7", page7(R))]
    pages_html = "".join(
        f'<div class="page{" on" if i == 0 else ""}" id="{pid}">{content}</div>'
        for i, (pid, content) in enumerate(pages))

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sales reconciliation</title>
{style}
{DETAIL_CSS}
</head>
<body>
<div id="app">
  <div class="chrome">
    <div class="chrome-row">
      <div class="brand">Sales reconciliation
        <small>Revenue and tax GL · Customer GL · E-invoice</small>
      </div>
      <div class="chrome-controls">
        <span class="chrome-pill">{esc(S['entity'])}</span>
        <span class="chrome-pill">SAR</span>
        <span class="chrome-pill">{esc(S['period_label'])}</span>
      </div>
    </div>
    <div class="tabbar">{tabbar}</div>
  </div>
  {pages_html}
  <div class="foot">
    Figures reconcile to source rows by line id and row id. Suggested matches are proposals and are never
    applied automatically. Documents outside the reconciled window are excluded from all exposure figures
    and listed on the data quality page.
  </div>
</div>
{script}
<script>window.RECON = {json.dumps(_recon_payload(R), ensure_ascii=False)};
window.__FILTER__ = null;
function showDetailPage(){{var t=document.querySelector('.tab[data-p="p7"]');if(t)t.click();}}
</script>
<script>{detail_js}</script>
</body>
</html>"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return out_path
