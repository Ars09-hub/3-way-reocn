"""Outputs: CSV/parquet writers, coverage summary, run manifest, dashboard
data contract (spec §17). run_manifest.json makes a run reproducible and
auditable - it hashes every config file and every input file.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import pandas as pd

from .config import file_sha256
from .matcher.common import TIER_RANK


def _minor(v, exp):
    from decimal import Decimal
    q = Decimal(1).scaleb(-exp)
    return str((Decimal(int(v)) * q).quantize(q))


def write_all(result: dict, out_dir: str, inputs: dict, seed: int) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    cfg = result["cfg"]
    units = result["units"]
    exp = cfg.minor_exp

    # ---- recon_units ----------------------------------------------------
    unit_rows = [_flatten_unit(u, exp) for u in units]
    udf = pd.DataFrame(unit_rows)
    udf.to_csv(os.path.join(out_dir, "recon_units.csv"), index=False)
    try:
        udf.to_parquet(os.path.join(out_dir, "recon_units.parquet"), index=False)
    except Exception:  # noqa: BLE001 - parquet optional if pyarrow missing
        pass

    # ---- suggestions (T3-T5) -------------------------------------------
    sug = [u for u in unit_rows if u["match_tier"] in ("T3", "T4", "T5")]
    sug.sort(key=lambda r: -r["value_at_risk_minor"])
    pd.DataFrame(sug).to_csv(os.path.join(out_dir, "suggestions.csv"), index=False)

    # ---- exceptions by bucket ------------------------------------------
    exc_cells = {"E2", "E4", "E5", "E7"}
    exc = [u for u in unit_rows if u["existence_cell"] in exc_cells
           or u["integrity_status"] == "UNEXPLAINED"]
    exc.sort(key=lambda r: (-_sev(r["severity"]), -r["value_at_risk_minor"]))
    pd.DataFrame(exc).to_csv(os.path.join(out_dir, "exceptions_by_bucket.csv"), index=False)

    # ---- unmatched residue ---------------------------------------------
    for plane, fname in (("GL", "unmatched_gl.csv"), ("AR", "unmatched_ar.csv"),
                         ("EINV", "unmatched_einv.csv")):
        rows = [u for u in unit_rows if u["match_status"] == "UNMATCHED"
                and u["cardinality"].count("0") >= 2 and _plane_of(u) == plane]
        pd.DataFrame(rows or [{}]).to_csv(os.path.join(out_dir, fname), index=False)

    # ---- suggested account class additions (E5 self-correction) --------
    from . import buckets
    add_rows = buckets.suggested_account_additions(units, result["gl_docs_by_id"])
    pd.DataFrame(add_rows or [{}]).to_csv(
        os.path.join(out_dir, "suggested_account_class_additions.csv"), index=False)

    # ---- doc number linkage report -------------------------------------
    pd.DataFrame(_linkage_report(result)).to_csv(
        os.path.join(out_dir, "doc_number_linkage_report.csv"), index=False)

    # ---- quarantine -----------------------------------------------------
    pd.DataFrame(result["ingest"].quarantine or [{}]).to_csv(
        os.path.join(out_dir, "quarantine.csv"), index=False)

    # ---- coverage summary ----------------------------------------------
    coverage = _coverage(result, exp)
    with open(os.path.join(out_dir, "coverage_summary.json"), "w") as fh:
        json.dump(coverage, fh, indent=2)

    # ---- run manifest ---------------------------------------------------
    manifest = {
        "engine_version": cfg.engine.get("engine_version", "0.1.0"),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "country": cfg.country.get("country"),
        "country_pack_version": cfg.country.get("pack_version"),
        "country_completeness": cfg.country.get("completeness"),
        "client": cfg.client.get("client"),
        "config_hashes": cfg.hashes,
        "input_hashes": {k: file_sha256(v) for k, v in inputs.items() if v and os.path.exists(v)},
        "warnings": cfg.warnings,
        "conservation": result["conservation"]["ok"],
        "open_decisions": _open_decisions(cfg),
    }
    with open(os.path.join(out_dir, "run_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    return {"coverage": coverage, "manifest": manifest, "unit_rows": unit_rows}


def _plane_of(u):
    einv, ar, gl = u["cardinality"].split(":")
    if int(gl) > 0:
        return "GL"
    if int(ar) > 0:
        return "AR"
    return "EINV"


def _sev(s):
    return {"SUPPRESSED": 0, "INFO": 1, "REVIEW": 2, "HIGH": 3, "CRITICAL": 4}.get(s, 0)


def _flatten_unit(u, exp):
    tax = u["planes"].get("tax", {})
    return {
        "unit_id": u["unit_id"],
        "cardinality": u["cardinality"],
        "existence_cell": u["existence_cell"],
        "bucket": u["bucket"],
        "severity": u["severity"],
        "match_tier": u["match_tier"],
        "match_status": u["match_status"],
        "confidence": u["confidence"],
        "confidence_band": u["confidence_band"],
        "search_mode": u["search_mode"],
        "is_ambiguous": u["is_ambiguous"],
        "alternatives_count": u["alternatives_count"],
        "degeneracy_reason": u["degeneracy_reason"],
        "diagnosis": u["diagnosis"],
        "integrity_status": u["integrity"]["status"],
        "integrity_residual_minor": u["integrity"]["residual_minor"],
        "tax_gl": tax.get("gl"), "tax_ar": tax.get("ar"), "tax_einv": tax.get("einv"),
        "value_at_risk_minor": u["value_at_risk_minor"],
        "gl_rows": ";".join(u["gl_rev_tax_rows"] + u["gl_customer_rows"]),
        "ar_rows": ";".join(u["ar_rows"]),
        "einv_rows": ";".join(u["einv_rows"]),
        "period": u["period"],
        "entity_id": u["entity_id"],
        "rules_fired": ";".join(u["rules_fired"]),
    }


def _coverage(result, exp):
    ing = result["ingest"]
    units = result["units"]
    docs = result["docs"]
    by_tier = {}
    for u in units:
        by_tier[u["match_tier"]] = by_tier.get(u["match_tier"], 0) + 1

    total_tax = {"GL": 0, "AR": 0, "EINV": 0}
    matched_tax = {"GL": 0, "AR": 0, "EINV": 0}
    doc_by_id = {d["row_id"]: d for d in docs}
    for d in docs:
        total_tax[d["plane"]] += d["tax_minor"]
    for u in units:
        if TIER_RANK.get(u["match_tier"], 9) <= 2:
            for rid in u["member_ids"]:
                dd = doc_by_id[rid]
                matched_tax[dd["plane"]] += dd["tax_minor"]

    assurance = {p: (round(matched_tax[p] / total_tax[p], 4) if total_tax[p] else None)
                 for p in total_tax}
    return {
        "raw_counts": ing.stats["raw_counts"],
        "gl_lines": ing.stats["gl_lines"],
        "docs": {"gl": ing.stats["docs_gl"], "ar": ing.stats["docs_ar"], "einv": ing.stats["docs_einv"]},
        "quarantined": ing.stats["quarantined"],
        "awkey_coverage": ing.stats["awkey_coverage"],
        "units_by_tier": by_tier,
        "value_total_tax_minor": total_tax,
        "value_matched_deterministic_tax_minor": matched_tax,
        "assurance_pct_by_plane": assurance,
        "conservation_ok": result["conservation"]["ok"],
        "b2c": result["b2c"],
    }


def _linkage_report(result):
    rows = []
    pair_fam = {}
    for l in result["links"]:
        if l["tier"] in ("T0", "T1"):
            fam = l["rules_fired"][0] if l["rules_fired"] else "?"
            key = (l["plane_a"], l["plane_b"], fam)
            pair_fam[key] = pair_fam.get(key, 0) + 1
    for (pa, pb, fam), n in sorted(pair_fam.items(), key=lambda x: -x[1]):
        rows.append({"source_a": pa, "source_b": pb, "family_rule": fam, "join_count": n})
    return rows or [{}]


def _open_decisions(cfg):
    return [
        {"id": "ADVANCE_TREATMENT",
         "text": "Advance/down-payment treatment is taxable at receipt in KSA and India, "
                 "not universally. Country pack must declare it.",
         "pack_value": cfg.country.get("advance_payment_taxable", "TODO")},
        {"id": "ACCEPT_PERSISTENCE",
         "text": "Should an accepted suggestion persist across re-runs when a member "
                 "document's amount changes? Current default: invalidate and re-suggest."},
        {"id": "SUGGESTION_FLOOR",
         "text": "Confidence floor for inclusion in the suggestion queue.",
         "current_default": cfg.engine.get("suggestion_queue_confidence_floor", "MEDIUM")},
        {"id": "MAX_GROUP_CARDINALITY",
         "text": "max_group_cardinality default of 8 may need to be far higher for "
                 "PER_DAY_PER_STORE_PER_TAXCODE retail, forcing heuristic search as default.",
         "current_default": cfg.engine["matching"]["max_group_cardinality"]},
    ]
