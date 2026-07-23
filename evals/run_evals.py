"""Eval harness (spec §20).

Scores engine output against ground_truth.csv for both datasets and prints a
confusion matrix by bucket and a precision/recall table by tier. Fails the
build (non-zero exit) if any target is missed.
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from core import config as config_mod, pipeline  # noqa: E402
from core.matcher.common import TIER_RANK  # noqa: E402

TARGETS = {
    "t0_t2_precision": 1.000,
    "t3_t5_precision_high": 0.95,
    "t3_t5_recall_high_med": 0.85,
    "existence_cell_accuracy": 0.98,
    "ambiguity_recall": 1.000,
    "e6_false_positive_rate": 0.00,
}


def _cfg(country, client):
    return config_mod.load_all(
        os.path.join(ROOT, "config", "engine.default.json"),
        os.path.join(ROOT, "config", "country-packs", f"{country}.pack.json"),
        os.path.join(ROOT, "config", "client-profiles", f"{client}.profile.json"),
    )


def _load_gt(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _index_docs(docs):
    gl, ar, einv = {}, {}, {}
    for d in docs:
        if d["plane"] == "GL":
            gl[d["accounting_doc_id"]] = d["row_id"]
        elif d["plane"] == "AR":
            if d.get("billing_doc_id"):
                ar[d["billing_doc_id"]] = d["row_id"]
        elif d["plane"] == "EINV":
            if d.get("billing_doc_id"):
                einv[d["billing_doc_id"]] = d["row_id"]
    return gl, ar, einv


def _expected_ids(row, gl_idx, ar_idx, einv_idx):
    ids = []
    for x in row["gl_docs"].split(";"):
        if x and x in gl_idx:
            ids.append(gl_idx[x])
    for x in row["ar_docs"].split(";"):
        if x and x in ar_idx:
            ids.append(ar_idx[x])
    for x in row["einv_docs"].split(";"):
        if x and x in einv_idx:
            ids.append(einv_idx[x])
    return ids


def evaluate(country, client, data_dir):
    cfg = _cfg(country, client)
    res = pipeline.run(cfg, os.path.join(data_dir, "gl.csv"),
                       os.path.join(data_dir, "ar.csv"),
                       os.path.join(data_dir, "einv.csv"), period_filter=None)
    units = res["units"]
    gt = _load_gt(os.path.join(data_dir, "ground_truth.csv"))
    gl_idx, ar_idx, einv_idx = _index_docs(res["docs"])
    quarantined = {q.get("doc_id") for q in res["ingest"].quarantine}

    unit_by_member = {}
    for u in units:
        for rid in u["member_ids"]:
            unit_by_member[rid] = u

    records = []
    for row in gt:
        exp_cell = row["expected_cell"]
        if exp_cell == "QUARANTINE":
            got = row["ar_docs"] in quarantined or any(
                row["ar_docs"] == q for q in quarantined)
            records.append({"sid": row["scenario_id"], "name": row["scenario_name"],
                            "exp_cell": exp_cell, "got_cell": "QUARANTINE" if got else "LEAKED",
                            "exp_tier": "NONE", "got_tier": "NONE",
                            "membership_ok": got, "exp_amb": False, "got_amb": False,
                            "quarantine": True})
            continue

        exp_ids = _expected_ids(row, gl_idx, ar_idx, einv_idx)
        # primary unit = the one containing the most expected members
        counts = {}
        for rid in exp_ids:
            u = unit_by_member.get(rid)
            if u:
                counts[u["unit_id"]] = counts.get(u["unit_id"], 0) + 1
        if counts:
            best_uid = max(counts, key=lambda k: counts[k])
            u = next(x for x in units if x["unit_id"] == best_uid)
            member_set = set(u["member_ids"])
            membership_ok = all(i in member_set for i in exp_ids)
            got_cell, got_tier, got_amb = u["existence_cell"], u["match_tier"], u["is_ambiguous"]
            got_alts = u["alternatives_count"]
        else:
            u = None
            membership_ok = False
            got_cell, got_tier, got_amb, got_alts = "NONE", "NONE", False, 0

        records.append({
            "sid": row["scenario_id"], "name": row["scenario_name"],
            "exp_cell": exp_cell, "got_cell": got_cell,
            "exp_tier": row["expected_tier"], "got_tier": got_tier,
            "exp_card": row["expected_cardinality"],
            "got_card": u["cardinality"] if u else "NA",
            "membership_ok": membership_ok,
            "exp_amb": row["expected_ambiguous"] == "true",
            "got_amb": got_amb,
            "min_alts": int(row["expected_min_alternatives"]),
            "got_alts": got_alts,
            "quarantine": False,
        })
    return res, records


def _metrics(records):
    # existence cell accuracy
    cell_recs = [r for r in records if not r["quarantine"]]
    cell_acc = sum(1 for r in cell_recs if r["got_cell"] == r["exp_cell"]) / max(1, len(cell_recs))

    # tier precision/recall
    det = [r for r in records if r["exp_tier"] in ("T0", "T1", "T2")]
    det_ok = sum(1 for r in det if r["got_tier"] in ("T0", "T1", "T2") and r["membership_ok"])
    t0_t2_precision = det_ok / max(1, len(det))

    # Ambiguous-by-design scenarios (e.g. the degenerate 45-way set) have no
    # single correct membership; they are scored by ambiguity_recall, not here.
    fuzzy = [r for r in records if r["exp_tier"] in ("T3", "T4", "T5") and not r["exp_amb"]]
    fuzzy_hit = [r for r in fuzzy if r["got_tier"] in ("T3", "T4", "T5") and r["membership_ok"]]
    t3_t5_precision = len(fuzzy_hit) / max(1, len([r for r in fuzzy if r["got_tier"] in ("T3", "T4", "T5")]))
    t3_t5_recall = len(fuzzy_hit) / max(1, len(fuzzy))

    # ambiguity recall
    amb = [r for r in records if r["exp_amb"]]
    amb_ok = sum(1 for r in amb if r["got_amb"] and r["got_alts"] >= r.get("min_alts", 1))
    amb_recall = amb_ok / max(1, len(amb))

    # E6 false positive rate: E6 scenarios flagged as anomaly
    e6 = [r for r in records if r["exp_cell"] == "E6"]
    e6_fp = sum(1 for r in e6 if r["got_cell"] != "E6") / max(1, len(e6))

    return {
        "existence_cell_accuracy": cell_acc,
        "t0_t2_precision": t0_t2_precision,
        "t3_t5_precision_high": t3_t5_precision,
        "t3_t5_recall_high_med": t3_t5_recall,
        "ambiguity_recall": amb_recall,
        "e6_false_positive_rate": e6_fp,
    }


def _confusion_by_bucket(records):
    from collections import Counter
    c = Counter()
    for r in records:
        c[(r["exp_cell"], r["got_cell"])] += 1
    return c


def main():
    datasets = [
        ("MY", "demo-b2b-sap", os.path.join(ROOT, "data", "b2b")),
        ("MY", "demo-b2c-retail-sap", os.path.join(ROOT, "data", "b2c")),
    ]
    all_records = []
    hashes = []
    conservation_ok = True
    for country, client, ddir in datasets:
        res, records = evaluate(country, client, ddir)
        all_records += records
        conservation_ok = conservation_ok and res["conservation"]["ok"]
        # determinism: run again, hash units
        res2, _ = evaluate(country, client, ddir)
        h1 = _hash_units(res["units"])
        h2 = _hash_units(res2["units"])
        hashes.append((client, h1, h2, h1 == h2))

        print(f"\n{'='*70}\nDATASET {client}\n{'='*70}")
        print(f"{'scenario':32} {'exp_cell':10} {'got_cell':10} {'exp_tier':6} {'got_tier':6} "
              f"{'card(e:a:g)':12} memb amb")
        for r in records:
            flag = " " if (r["got_cell"] == r["exp_cell"] and r["membership_ok"]) else "X"
            card = f"{r.get('exp_card','')}->{r.get('got_card','')}"
            print(f"{flag} {r['name'][:30]:30} {r['exp_cell']:10} {r['got_cell']:10} "
                  f"{r['exp_tier']:6} {r['got_tier']:6} {card:20} "
                  f"{'ok' if r['membership_ok'] else '--':4} "
                  f"{'A' if r['got_amb'] else '.'}")

    metrics = _metrics(all_records)
    metrics_pass = {}
    print(f"\n{'='*70}\nMETRICS vs TARGETS\n{'='*70}")
    for k, target in TARGETS.items():
        val = metrics[k]
        if k == "e6_false_positive_rate":
            ok = val <= target
        else:
            ok = val >= target
        metrics_pass[k] = ok
        print(f"  {'PASS' if ok else 'FAIL'}  {k:32} {val:.3f}  (target {target:.3f})")
    print(f"  {'PASS' if conservation_ok else 'FAIL'}  conservation_check")
    det_ok = all(h[3] for h in hashes)
    print(f"  {'PASS' if det_ok else 'FAIL'}  determinism (identical recon hash over two runs)")

    print(f"\n{'='*70}\nCONFUSION MATRIX BY CELL (exp -> got : count)\n{'='*70}")
    conf = _confusion_by_bucket(all_records)
    for (exp, got), n in sorted(conf.items(), key=lambda x: -x[1]):
        mark = "" if exp == got else "   <-- mismatch"
        print(f"  {exp:12} -> {got:12} : {n}{mark}")

    all_pass = all(metrics_pass.values()) and conservation_ok and det_ok
    print(f"\n{'='*70}\nBUILD {'PASS' if all_pass else 'FAIL'}\n{'='*70}")
    return 0 if all_pass else 1


def _hash_units(units):
    key = sorted(u["unit_id"] + "|" + u["match_tier"] + "|" + u["existence_cell"] for u in units)
    return hashlib.sha256("\n".join(key).encode()).hexdigest()[:16]


if __name__ == "__main__":
    raise SystemExit(main())
