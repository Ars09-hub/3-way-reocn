"""Derive every GCC eInvoicing Command Center figure from the real workbooks.

Reads the three GCC datasets (UAE, KSA, Oman) and the run index, then folds each
country into one record carrying the AR (outward) and AP (inward) pipeline and
reconciliation metrics defined by the gcc-einvoice-command-center skill.

House rules enforced here:
  - GCC only (UAE, KSA, Oman). No India, France, or Malaysia.
  - Amounts are non-additive across currencies. Nothing sums AED, SAR and OMR.
  - Plain-English finding labels come straight from the data; internal codes
    (MM-VAL, ME-NONE, ...) stay in the rulebook and never leave this module.
  - Severity is Level 3 / Level 2 / Level 1, exactly as the recon run stamped it.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "gcc-data")

# Country registry (skill section 1). Rate/authority/currency are jurisdiction
# facts; entities and figures come from the data.
REGISTRY = {
    "UAE": {"name": "United Arab Emirates", "authority": "FTA",
            "model": "Peppol 5-corner (DCTCE)", "currency": "AED", "decimals": 2,
            "vat_rate": 0.05, "status": "Live", "ap_feed": "Received via ASP",
            "penalty_rate": {"failure to issue einvoice": 2500,
                             "failure to issue credit note": 2500},
            "on_time_rule": "14-day issuance window"},
    "KSA": {"name": "Saudi Arabia", "authority": "ZATCA (Fatoora)",
            "model": "Clearance + reporting", "currency": "SAR", "decimals": 2,
            "vat_rate": 0.15, "status": "Live", "ap_feed": "Client-provided",
            "penalty_rate": None,  # ZATCA schedule not parameterised in dataset
            "on_time_rule": "Clear pre-issuance, simplified within 24h"},
    "OMN": {"name": "Oman", "authority": "OTA",
            "model": "Peppol 5-corner (ASP)", "currency": "OMR", "decimals": 3,
            "vat_rate": 0.05, "status": "Live", "ap_feed": "Received via ASP",
            "penalty_rate": None,  # OTA schedule not yet published
            "on_time_rule": "14-day issuance window"},
}
ISO3_TO_CODE = {"UAE": "UAE", "KSA": "KSA", "OMN": "OMN"}

_MISSED = "Invoice not reported to authority"
_LATE = "Reported or issued late"
_GENFAIL = "E-invoice generation failed"
_INGFAIL = "Ingestion failed (landing failed)"

# finding label -> universal parent (surface only; codes never rendered)
PARENT = {
    "Matched": "Matched",
    "Tax / taxable value mismatch": "Mismatch",
    "Tax rate / category mismatch": "Mismatch",
    "Customer TIN / buyer ID mismatch": "Mismatch",
    "Document metadata mismatch": "Mismatch",
    "Status / lifecycle conflict": "Mismatch",
    _MISSED: "Missing in e-invoice",
    _LATE: "Missing in e-invoice",
    _GENFAIL: "Pipeline failure",
    _INGFAIL: "Pipeline failure",
    "Unbooked revenue (e-invoice, no GL)": "Missing in GL",
    "Cancelled in GL but e-invoice still live": "Missing in GL",
    "Out of scope, no obligation": "Out of scope",
    # AP
    "Value / tax mismatch": "Mismatch",
    "Vendor TIN mismatch": "Mismatch",
    "Under-reported in books": "Mismatch",
    "Missing e-invoice (not sent by vendor)": "Missing in e-invoice",
    "Missed booking (in e-invoice, no GL)": "Missing in GL",
    "Unregistered vendor receipt": "Missing in e-invoice",
    "Reverse charge, self-account": "Out of scope",
    "Blocked input tax": "Out of scope",
}
SEV_RANK = {"Level 3": 3, "Level 2": 2, "Level 1": 1}


def _sheet(ws):
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    return [dict(zip(hdr, r)) for r in it]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _round(v, d):
    return round(v, d)


def _grouped_findings(rows, risk_col):
    """Group recon rows by plain-English finding, carrying count + value at risk."""
    agg = defaultdict(lambda: {"count": 0, "risk": 0.0, "severity": "Level 1",
                               "parent": "", "delta": 0.0})
    for r in rows:
        lbl = r.get("finding_label")
        a = agg[lbl]
        a["count"] += 1
        a["risk"] += _num(r.get(risk_col))
        a["delta"] += abs(_num(r.get("value_delta")))
        a["parent"] = PARENT.get(lbl, "Other")
        if SEV_RANK.get(r.get("severity"), 0) > SEV_RANK.get(a["severity"], 0):
            a["severity"] = r.get("severity")
    return agg


def _by(rows, key, risk_col, decimals):
    d = defaultdict(float)
    for r in rows:
        d[r.get(key)] += _num(r.get(risk_col))
    return [{"name": k, "value": _round(v, decimals)}
            for k, v in sorted(d.items(), key=lambda x: -x[1])]


def compute_country(iso3, meta):
    reg = REGISTRY[iso3]
    dec = reg["decimals"]
    path = os.path.join(DATA_DIR, f"{iso3}_einvoice_recon_dataset.xlsx")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    gl_s = _sheet(wb["GL_Sales"])
    gl_p = _sheet(wb["GL_Purchase"])
    ei_s = _sheet(wb["Einvoice_Sales"])
    ei_p = _sheet(wb["Einvoice_Purchase"])
    rc_s = _sheet(wb["Recon_Sales"])
    rc_p = _sheet(wb["Recon_Purchase"])
    wb.close()

    # ---- AR pipeline (from Recon_Sales, the authoritative tie-out) ----
    reported = [r for r in rc_s if r.get("authority_status") in ("Reported", "Cleared")]
    delayed = sum(1 for r in reported if r.get("on_time_flag") in (False, "False"))
    on_time = len(reported) - delayed
    fcount = Counter(r.get("finding_label") for r in rc_s)
    missed = fcount.get(_MISSED, 0)
    gen_failed = fcount.get(_GENFAIL, 0)
    ing_failed = fcount.get(_INGFAIL, 0)
    oos = fcount.get("Out of scope, no obligation", 0)
    applicable = len(rc_s) - oos
    denom = on_time + delayed + missed + gen_failed + ing_failed
    adherence = (on_time / denom) if denom else 0.0

    ar_find = _grouped_findings(rc_s, "vat_at_risk")
    ar_risk_total = sum(a["risk"] for a in ar_find.values())

    # penalty exposure (skill section 5): instances x statutory rate
    pcls = Counter(r.get("penalty_class") for r in rc_s
                   if r.get("penalty_class") and r.get("penalty_class") != "None")
    penalty_rows = []
    penalty_total = 0.0
    for cls, inst in sorted(pcls.items(), key=lambda x: -x[1]):
        rate = (reg["penalty_rate"] or {}).get(cls)
        exposure = (inst * rate) if rate is not None else None
        if exposure is not None:
            penalty_total += exposure
        penalty_rows.append({"cls": cls, "instances": inst, "rate": rate,
                             "exposure": _round(exposure, dec) if exposure is not None else None})

    ar = {
        "gl_docs": len(gl_s),
        "gl_taxable": _round(sum(_num(r.get("taxable_value")) for r in gl_s), dec),
        "gl_tax": _round(sum(_num(r.get("tax_value")) for r in gl_s), dec),
        "generated": len(ei_s),
        "generated_tax": _round(sum(_num(r.get("tax_amount")) for r in ei_s), dec),
        "applicable": applicable,
        "cleared": len(reported),
        "on_time": on_time, "delayed": delayed, "missed": missed,
        "gen_failed": gen_failed, "ing_failed": ing_failed, "out_of_scope": oos,
        "adherence_pct": _round(adherence * 100, 1),
        "vat_at_risk": _round(ar_risk_total, dec),
        "findings": [
            {"label": lbl, "count": a["count"], "risk": _round(a["risk"], dec),
             "severity": a["severity"], "parent": a["parent"],
             "delta": _round(a["delta"], dec)}
            for lbl, a in sorted(ar_find.items(),
                                 key=lambda kv: (-SEV_RANK.get(kv[1]["severity"], 0),
                                                 -kv[1]["risk"]))
        ],
        "var_by_system": _by(rc_s, "source_system", "vat_at_risk", dec),
        "var_by_entity": _by(rc_s, "entity_name", "vat_at_risk", dec),
        "var_by_team": _by(rc_s, "owning_team", "vat_at_risk", dec),
        "penalty_rows": penalty_rows,
        "penalty_total": _round(penalty_total, dec),
        "penalty_priced": reg["penalty_rate"] is not None,
    }

    # ---- AP pipeline (from Recon_Purchase; data source qualifies KSA) ----
    ap_feed = Counter(str(r.get("data_source")) for r in rc_p).most_common(1)[0][0]
    elig = defaultdict(lambda: {"count": 0, "tax": 0.0})
    for r in gl_p:
        e = elig[r.get("itc_eligibility")]
        e["count"] += 1
        e["tax"] += _num(r.get("input_tax_value"))
    ap_find = _grouped_findings(rc_p, "input_vat_at_risk")
    ap_risk_total = sum(a["risk"] for a in ap_find.values())

    ap = {
        "gl_docs": len(gl_p),
        "gl_taxable": _round(sum(_num(r.get("taxable_value")) for r in gl_p), dec),
        "gl_input_tax": _round(sum(_num(r.get("input_tax_value")) for r in gl_p), dec),
        "received": len(ei_p),
        "data_source": ap_feed,
        "eligibility": {k: {"count": v["count"], "tax": _round(v["tax"], dec)}
                        for k, v in elig.items()},
        "input_vat_at_risk": _round(ap_risk_total, dec),
        "findings": [
            {"label": lbl, "count": a["count"], "risk": _round(a["risk"], dec),
             "severity": a["severity"], "parent": a["parent"]}
            for lbl, a in sorted(ap_find.items(),
                                 key=lambda kv: (-SEV_RANK.get(kv[1]["severity"], 0),
                                                 -kv[1]["risk"]))
        ],
        "var_by_system": _by(rc_p, "source_system", "input_vat_at_risk", dec),
        "var_by_entity": _by(rc_p, "entity_name", "input_vat_at_risk", dec),
        "top_vendors": _by(rc_p, "vendor_name", "input_vat_at_risk", dec)[:6],
    }

    return {
        "code": iso3,
        "name": reg["name"],
        "authority": reg["authority"],
        "model": reg["model"],
        "currency": reg["currency"],
        "decimals": dec,
        "vat_rate": reg["vat_rate"],
        "status": reg["status"],
        "ap_feed": reg["ap_feed"],
        "on_time_rule": reg["on_time_rule"],
        "entities": meta.get("entities", []),
        "live_entities": len(meta.get("entities", [])),
        "source_systems": meta.get("source_systems", []),
        "ar": ar,
        "ap": ap,
    }


def build_dataset():
    with open(os.path.join(DATA_DIR, "run_index.json"), encoding="utf-8") as fh:
        idx = json.load(fh)
    meta_by_iso = {d["country_iso3"]: d for d in idx["datasets"]}
    order = ["UAE", "KSA", "OMN"]
    countries = [compute_country(iso, meta_by_iso[iso]) for iso in order
                 if iso in meta_by_iso]
    return {
        "meta": {
            "region": "GCC",
            "generated_utc": idx.get("generated_utc"),
            "run_id": "recon-" + str(idx.get("generated_utc", ""))[:19].replace(":", "").replace("-", "").replace("T", "-"),
            "countries": [c["code"] for c in countries],
            "currencies": [c["currency"] for c in countries],
        },
        "countries": countries,
    }


if __name__ == "__main__":
    d = build_dataset()
    print("COUNTRY SET:", ", ".join(f"{c['name']} ({c['code']})" for c in d["countries"]))
    print("(no France, no Malaysia, no India; GCC only)\n")
    print("Headline confirmation, one real number per country in native currency:")
    for c in d["countries"]:
        print(f"  {c['code']}  GL sales taxable = {c['currency']} "
              f"{c['ar']['gl_taxable']:,.{c['decimals']}f}   |   "
              f"AR VAT at risk = {c['currency']} {c['ar']['vat_at_risk']:,.{c['decimals']}f}   |   "
              f"on-time adherence = {c['ar']['adherence_pct']}%")
