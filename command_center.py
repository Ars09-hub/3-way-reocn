#!/usr/bin/env python3
"""GCC Command Center - CLI entry point.

Rolls up many three-way reconciliation runs into a single control-tower
dashboard. It consumes only the artifacts each run already writes, so it can be
pointed at a directory of historical runs after the fact.

Examples:
  # auto-discover every completed run under out/
  python command_center.py --scan out --out out/command_center.html

  # or name the run directories explicitly
  python command_center.py --runs out/b2c out/b2b out/sa-b2b \
    --out out/command_center.html --title "GCC Q2 estate"
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dashboard import command_center  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="GCC Command Center dashboard")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--scan", metavar="DIR",
                     help="discover run directories under DIR (recursively)")
    src.add_argument("--runs", nargs="+", metavar="DIR",
                     help="explicit list of run output directories")
    ap.add_argument("--out", default="out/command_center.html",
                    help="output HTML path (default: out/command_center.html)")
    ap.add_argument("--config", default=os.path.join(HERE, "config"),
                    help="config dir for currency/pack enrichment (default: ./config)")
    ap.add_argument("--title", default="GCC Command Center")
    args = ap.parse_args(argv)

    if args.scan:
        run_dirs = command_center.discover_runs(args.scan)
        if not run_dirs:
            ap.error(f"no runs found under {args.scan} "
                     "(need coverage_summary.json + run_manifest.json)")
    else:
        run_dirs = args.runs

    out = command_center.build(run_dirs, args.out, config_dir=args.config,
                               title=args.title)

    print("=" * 68)
    print(f"GCC Command Center: {len(run_dirs)} run director"
          f"{'y' if len(run_dirs) == 1 else 'ies'} aggregated")
    print("=" * 68)
    for d in run_dirs:
        print(f"  - {os.path.relpath(d)}")
    print(f"\nCommand Center: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
