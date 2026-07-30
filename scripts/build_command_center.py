#!/usr/bin/env python3
"""Build the GCC e-invoice command center.

Reads the staged datasets in ``gcc-data/`` (three country workbooks, the
country registry and the run index), computes a single portfolio + per country
data model, and writes a self contained ``gcc-command-center/index.html``.

No LLM anywhere in this path. Every number on the page is derived here from the
source files and embedded into the page, so the artifact is reproducible: run
the script again and the same inputs give the same page.

    python scripts/build_command_center.py

Only dependency is ``openpyxl`` (already implied by the recon datasets).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "gcc-data"
OUT_DIR = ROOT / "gcc-command-center"

LIVE = ["UAE", "KSA", "OMN"]
WORKBOOKS = {c: DATA_DIR / f"{c}_einvoice_recon_dataset.xlsx" for c in LIVE}


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _rows(ws):
    it = ws.iter_rows(values_only=True)
    header = list(next(it))
    for row in it:
        if all(cell is None for cell in row):
            continue
        yield dict(zip(header, row))


def _read_workbook(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    data = {
        "recon": list(_rows(wb["Recon_Sales"])) + list(_rows(wb["Recon_Purchase"])),
        "worklist": list(_rows(wb["Worklist"])),
        "adherence": list(_rows(wb["Daily_Adherence"])),
    }
    wb.close()
    return data


def _side_agg(runs) -> dict:
    docs = sum(r["documents"] for r in runs)
    matched = sum(r["matched"] for r in runs)
    return {
        "documents": docs,
        "matched": matched,
        "match_pct": round(matched / docs * 100, 1) if docs else 0.0,
        "vat_at_risk": round(sum(r["vat_at_risk"] for r in runs), 2),
        "exceptions": sum(r["exceptions_to_review"] for r in runs),
    }


def build_model() -> dict:
    registry = json.loads((DATA_DIR / "country_registry.json").read_text())
    run_index = json.loads((DATA_DIR / "run_index.json").read_text())

    countries: dict[str, dict] = {}
    for code in LIVE:
        raw = _read_workbook(WORKBOOKS[code])
        runs = [r for r in run_index if r["country"] == code]
        recon = raw["recon"]

        def rvar(r):
            return _num(r.get("vat_at_risk") if r.get("vat_at_risk") is not None else r.get("input_vat_at_risk"))

        var_by_team: dict = defaultdict(float)
        var_by_finding: dict = defaultdict(float)
        cnt_by_team: Counter = Counter()
        cnt_by_severity: Counter = Counter()
        for r in recon:
            var_by_team[r.get("owning_team")] += rvar(r)
            var_by_finding[r.get("finding_label")] += rvar(r)
            cnt_by_team[r.get("owning_team")] += 1
            cnt_by_severity[r.get("severity")] += 1

        worklist = sorted(raw["worklist"], key=lambda r: _num(r.get("vat_at_risk")), reverse=True)
        top = [
            {
                "document_no": r["document_no"],
                "entity": r["entity_name"],
                "side": r["side"],
                "finding": r["finding_label"],
                "severity": r["severity"],
                "vat": round(_num(r.get("vat_at_risk")), 2),
                "team": r["owning_team"],
                "state": r["recon_state"],
                "authority": r.get("authority_status"),
                "on_time": r.get("on_time_flag"),
            }
            for r in worklist
            if _num(r.get("vat_at_risk")) > 0
        ][:10]

        adherence = sorted(raw["adherence"], key=lambda a: a["date"])
        ontime = Counter(str(r.get("on_time_flag")) for r in recon)

        entities = [
            {
                "entity_id": r["entity_id"],
                "entity_name": r["entity_name"],
                "side": r["side"],
                "source": r["source_systems"][0],
                "documents": r["documents"],
                "matched": r["matched"],
                "match_pct": r["match_pct"],
                "vat_at_risk": round(r["vat_at_risk"], 2),
                "exceptions": r["exceptions_to_review"],
            }
            for r in runs
        ]

        countries[code] = {
            "currency": runs[0]["currency"],
            "authority": runs[0]["authority"],
            "jurisdiction": runs[0]["jurisdiction"],
            "documents": sum(r["documents"] for r in runs),
            "matched": sum(r["matched"] for r in runs),
            "match_pct": round(sum(r["matched"] for r in runs) / sum(r["documents"] for r in runs) * 100, 1),
            "vat_at_risk": round(sum(r["vat_at_risk"] for r in runs), 2),
            "exceptions": sum(r["exceptions_to_review"] for r in runs),
            "sales": _side_agg([r for r in runs if r["side"] == "sales"]),
            "purchase": _side_agg([r for r in runs if r["side"] == "purchase"]),
            "entities": entities,
            "recon_state": dict(Counter(r["recon_state"] for r in recon)),
            "recon_total": len(recon),
            "var_by_team": {k: round(v, 2) for k, v in sorted(var_by_team.items(), key=lambda x: -x[1])},
            "var_by_finding": {k: round(v, 2) for k, v in sorted(var_by_finding.items(), key=lambda x: -x[1])[:6]},
            "cnt_by_team": dict(cnt_by_team),
            "cnt_by_severity": dict(cnt_by_severity),
            "on_time": dict(ontime),
            "worklist_top": top,
            "adherence": [
                {
                    "date": a["date"],
                    "pct": _num(a["adherence_pct"]),
                    "on_time": a["on_time"],
                    "delayed": a["delayed"],
                    "missed": a["missed"],
                    "failed": a["failed"],
                }
                for a in adherence
            ],
        }

    return {
        "generated": "2026-07-30",
        "run_timestamp": run_index[0]["run_timestamp"],
        "registry": registry,
        "countries": countries,
    }


def render_html(model: dict) -> str:
    payload = json.dumps(model, separators=(",", ":"))
    template = (OUT_DIR / "_template.html").read_text()
    return template.replace("/*__DATA__*/", payload)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    model = build_model()
    (OUT_DIR / "dashboard_data.json").write_text(json.dumps(model, indent=2))
    html = render_html(model)
    (OUT_DIR / "index.html").write_text(html)
    print(f"Wrote {OUT_DIR / 'index.html'} ({len(html):,} bytes)")
    print(f"Wrote {OUT_DIR / 'dashboard_data.json'}")


if __name__ == "__main__":
    main()
