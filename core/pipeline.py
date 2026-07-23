"""Orchestrates the reconciliation stages into a single result object.

Stages: ingest -> annotate/sets -> scope/period -> leg 1 -> leg 2 -> three-way
-> customer view -> data quality. Later stages are added as they are built.
"""
from __future__ import annotations

import pandas as pd

from core import (ingest, scope as scope_mod, sets, leg1_gl_vs_ar, leg2_einv_vs_ar,
                  threeway as threeway_mod, customer_view, quality)


def run(cfg: dict, gl_path: str, ar_path: str, einv_path: str,
        period_from: str | None = None, period_to: str | None = None) -> dict:
    acc, eng, ksa = cfg["account_scope"], cfg["engine"], cfg["ksa"]
    idx = scope_mod.build_account_index(acc)

    gl = ingest.load_gl(gl_path)
    ar = ingest.load_ar(ar_path)
    ei, ei_hist = ingest.load_einvoice(einv_path, ksa)

    gla = sets.annotate_gl(gl, acc, idx["excluded"])
    ara = sets.annotate_ar(ar, acc, idx["excluded"])

    set1 = sets.build_set1_vouchers(gla)
    set2 = sets.build_set2_vouchers(ara)

    period = scope_mod.detect_period(gl, ar, ei, eng, ei_in_scope=~ei["is_test"])
    frm = pd.Timestamp(period_from) if period_from else period["from"]
    to = pd.Timestamp(period_to) if period_to else period["to"]
    period["from"], period["to"] = frm, to

    leg1 = leg1_gl_vs_ar.run(set1, set2, eng, frm, to)
    leg2 = leg2_einv_vs_ar.run(ei, set2, eng, ksa, frm, to)
    threeway = threeway_mod.derive(leg1, leg2)

    R = {
        "cfg": cfg, "engine": eng,
        "gl": gl, "ar": ar, "ei": ei, "ei_hist": ei_hist,
        "gla": gla, "ara": ara,
        "set1": set1, "set2": set2,
        "period": period,
        "leg1": leg1,
        "leg2": leg2,
        "threeway": threeway,
    }
    R["customers"] = customer_view.build(threeway, ksa)
    R["quality"] = quality.build(R)
    return R
