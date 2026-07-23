#!/usr/bin/env python3
"""Three-way reconciliation engine - CLI entry point (spec §3).

Example:
  python run.py --country MY --client demo-b2c-retail-sap \
    --gl data/b2c/gl.csv --ar data/b2c/ar.csv --einv data/b2c/einv.csv \
    --period 2026-06 --out out/my-june --explain
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core import config as config_mod, pipeline, outputs  # noqa: E402
from dashboard import build_dashboard  # noqa: E402


def _paths(country, client):
    return (
        os.path.join(HERE, "config", "engine.default.json"),
        os.path.join(HERE, "config", "country-packs", f"{country}.pack.json"),
        os.path.join(HERE, "config", "client-profiles", f"{client}.profile.json"),
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="Three-way reconciliation engine")
    ap.add_argument("--country", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--gl", required=True)
    ap.add_argument("--ar", required=True)
    ap.add_argument("--einv", required=True)
    ap.add_argument("--period", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--explain", action="store_true",
                    help="emit per-finding narrative (consumes computed evidence only)")
    args = ap.parse_args(argv)

    eng_p, ctry_p, cli_p = _paths(args.country, args.client)
    for p in (eng_p, ctry_p, cli_p):
        if not os.path.exists(p):
            ap.error(f"config not found: {p}")

    cfg = config_mod.load_all(eng_p, ctry_p, cli_p)
    seed = cfg.engine["matching"]["heuristic_seed"]

    result = pipeline.run(cfg, args.gl, args.ar, args.einv, period_filter=args.period)
    written = outputs.write_all(result, args.out,
                                inputs={"gl": args.gl, "ar": args.ar, "einv": args.einv}, seed=seed)

    build_dashboard.build(result, written, os.path.join(args.out, "dashboard.html"),
                          explain=args.explain)

    cov = written["coverage"]
    print("=" * 68)
    print(f"Three-way recon: {args.country} / {args.client}"
          + (f" / {args.period}" if args.period else ""))
    print("=" * 68)
    print(f"Documents: GL={cov['docs']['gl']} AR={cov['docs']['ar']} EINV={cov['docs']['einv']}"
          f"  quarantined={cov['quarantined']}")
    print(f"Units by tier: {cov['units_by_tier']}")
    print(f"Assurance (deterministic tax value matched): {cov['assurance_pct_by_plane']}")
    print(f"accounting_doc_id (AWKEY) coverage on AR: {cov['awkey_coverage']:.0%}")
    print(f"Conservation check: {'PASS' if cov['conservation_ok'] else 'FAIL'}")
    if not result['conservation']['ok']:
        print("  !! conservation violated:", result['conservation'])

    # surface open decisions and warnings (spec §21, §23)
    if cfg.warnings:
        print("\nWARNINGS:")
        for w in cfg.warnings:
            print("  -", w)
    print("\nOPEN DECISIONS (surface, do not resolve silently):")
    for d in written["manifest"]["open_decisions"]:
        extra = d.get("current_default") or d.get("pack_value") or ""
        print(f"  - DECISION: {d['id']}: {d['text']}" + (f"  [default: {extra}]" if extra else ""))

    print(f"\nOutputs written to: {args.out}")
    print(f"Dashboard: {os.path.join(args.out, 'dashboard.html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
