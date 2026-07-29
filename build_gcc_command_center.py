#!/usr/bin/env python3
"""GCC eInvoicing Command Center - build entry point.

Reads the three GCC recon workbooks under gcc-data/ and emits a single-file,
self-contained HTML command center for UAE, KSA and Oman. Prints the country
set and one real headline number per country before writing anything.

Usage:
  python build_gcc_command_center.py [--out out/gcc/command_center.html]
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gcc_command_center import compute, build as builder  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the GCC eInvoicing Command Center")
    ap.add_argument("--out", default="out/gcc/command_center.html")
    args = ap.parse_args(argv)

    data = compute.build_dataset()

    # Confirmation before rendering (required): country set + one real headline
    # number per country, each in its own currency.
    print("=" * 70)
    print("GCC eInvoicing Command Center")
    print("=" * 70)
    print("COUNTRY SET:", ", ".join(f"{c['name']} ({c['code']})" for c in data["countries"]))
    print("Scope is GCC only. No France, no Malaysia, no India. No EUR, no MYR.\n")
    print("Headline confirmation (real figures read from gcc-data/, native currency):")
    for c in data["countries"]:
        d = c["decimals"]
        print(f"  {c['code']} · {c['authority']} · {c['currency']} · VAT {int(c['vat_rate']*100)}%")
        print(f"       GL sales taxable   = {c['currency']} {c['ar']['gl_taxable']:,.{d}f}")
        print(f"       AR VAT at risk     = {c['currency']} {c['ar']['vat_at_risk']:,.{d}f}")
        print(f"       AP input VAT risk  = {c['currency']} {c['ap']['input_vat_at_risk']:,.{d}f}")
        print(f"       on-time adherence  = {c['ar']['adherence_pct']}%")
    print()

    out = builder.build(args.out)
    print(f"Command Center written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
