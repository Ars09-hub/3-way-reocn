#!/usr/bin/env python3
"""Three-way sales reconciliation (KSA / ZATCA). CLI entry point (spec 6).

  python run.py --gl data/gl_register.xlsx --ar data/sales_register.xlsx \
    --einv data/sales_einvoice__1_.xlsx --out out/
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core import loader, pipeline, outputs  # noqa: E402
from core.normalize import halalas_to_str as H  # noqa: E402
from report import build_html  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Three-way sales reconciliation (KSA/ZATCA)")
    ap.add_argument("--gl", default=os.path.join(HERE, "data", "gl_register.xlsx"))
    ap.add_argument("--ar", default=os.path.join(HERE, "data", "sales_register.xlsx"))
    ap.add_argument("--einv", default=os.path.join(HERE, "data", "sales_einvoice__1_.xlsx"))
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--period-from", default=None)
    ap.add_argument("--period-to", default=None)
    args = ap.parse_args(argv)

    cfg = loader.load_config()
    R = pipeline.run(cfg, args.gl, args.ar, args.einv,
                     period_from=args.period_from, period_to=args.period_to)
    written = outputs.write_all(R, args.out)
    html_path = build_html.build(R, os.path.join(args.out, "recon.html"))

    per = R["period"]
    print("=" * 68)
    print("Three-way sales reconciliation (KSA / ZATCA)")
    print("=" * 68)
    print(f"Rows: GL {len(R['gl'])}, AR {len(R['ar'])}, e-invoice 39 (deduped {len(R['ei'])})")
    print(f"Reconciled window: {per['from'].date()} to {per['to'].date()}"
          f"  (basis: {cfg['engine']['period']['erp_date_field']})")
    print(f"\nLeg 1 (GL vs AR):   {R['leg1']['counts']}")
    print(f"Leg 2 (e-inv vs AR):{R['leg2']['counts']}")
    print(f"Three-way:          {R['threeway']['counts']}")

    print("\nOpen decisions (surface, do not resolve):")
    for d in R["quality"]["open_decisions"]:
        print(f"  - {d['text']}")

    print(f"\nOutputs written to: {args.out}")
    print(f"Dashboard: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
