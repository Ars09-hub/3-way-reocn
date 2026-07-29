"""GCC Command Center dashboard builder.

Where ``build_dashboard.py`` renders one reconciliation *run* (a single
country / client / period), the Command Center rolls up *many* runs into one
control tower. It is the layer a group controller or GCC (Global Capability
Center / Gulf Cooperation Council estate) tax lead looks at first: which
engagements are clean, where the money at risk is, what is waiting on a human
decision, and whether any run is operationally unhealthy.

It reads only the artifacts each run already writes -- ``coverage_summary.json``,
``run_manifest.json`` and ``recon_units.csv`` -- so it stays decoupled from the
engine internals and can aggregate historical runs after the fact. Currency and
display metadata are enriched, best-effort, from the country pack.

Guardrail carried over from the engine: monetary value is **never summed across
currencies**. Portfolio money is reported per-currency; the only estate-wide
scalars are counts and value-weighted percentages.
"""
from __future__ import annotations

import csv
import glob
import json
import os
from collections import Counter
from decimal import Decimal


# --------------------------------------------------------------------------- #
# Discovery + loading
# --------------------------------------------------------------------------- #
def discover_runs(scan_dir: str) -> list[str]:
    """Return sub-directories of *scan_dir* that look like a completed run."""
    found = []
    for cov in glob.glob(os.path.join(scan_dir, "**", "coverage_summary.json"),
                         recursive=True):
        d = os.path.dirname(cov)
        if os.path.exists(os.path.join(d, "run_manifest.json")):
            found.append(d)
    return sorted(set(found))


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_units(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("unit_id")]


def _pack_meta(config_dir, country):
    """Best-effort currency + minor-unit lookup from the country pack."""
    if not config_dir or not country:
        return {}
    p = os.path.join(config_dir, "country-packs", f"{country}.pack.json")
    if not os.path.exists(p):
        return {}
    try:
        pk = _read_json(p)
    except Exception:  # noqa: BLE001 - a broken pack must not sink the rollup
        return {}
    return {
        "currency": pk.get("currency", ""),
        "minor_exp": pk.get("minor_unit_exponent", 2),
        "pack_version": pk.get("pack_version"),
    }


def _to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _cur(minor, exp):
    q = Decimal(1).scaleb(-exp)
    return float((Decimal(int(minor)) * q).quantize(q))


_SEV_RANK = {"SUPPRESSED": 0, "INFO": 1, "REVIEW": 2, "HIGH": 3, "CRITICAL": 4}
_EXCEPTION_CELLS = {"E2", "E4", "E5", "E7"}
_EXPOSURE_CELLS = {"E2", "E7"}       # billed-unreported + reported-unbooked
_SUGGESTION_TIERS = {"T3", "T4", "T5"}


# --------------------------------------------------------------------------- #
# Per-run aggregation
# --------------------------------------------------------------------------- #
def load_run(run_dir: str, config_dir: str | None = None) -> dict | None:
    """Fold one run directory into a single engagement record."""
    cov_p = os.path.join(run_dir, "coverage_summary.json")
    man_p = os.path.join(run_dir, "run_manifest.json")
    if not (os.path.exists(cov_p) and os.path.exists(man_p)):
        return None
    cov = _read_json(cov_p)
    man = _read_json(man_p)
    units = _read_units(os.path.join(run_dir, "recon_units.csv"))

    country = man.get("country") or "??"
    pack = _pack_meta(config_dir, country)
    exp = pack.get("minor_exp", 2)
    currency = pack.get("currency", "")

    period = Counter(u.get("period") for u in units if u.get("period")).most_common(1)
    period = period[0][0] if period else (man.get("period") or "")
    entities = sorted({u.get("entity_id") for u in units if u.get("entity_id")})

    exposure_minor = 0
    unexplained_minor = 0
    sev_count = Counter()
    sev_value = Counter()
    exceptions = []
    suggestions = []
    sug_by_band = Counter()
    ambiguous = 0
    heuristic = 0
    sug_value_minor = 0

    for u in units:
        cell = u.get("existence_cell", "")
        var = _to_int(u.get("value_at_risk_minor"))
        integ = u.get("integrity_status", "")
        sev = u.get("severity", "INFO")

        if cell in _EXPOSURE_CELLS:
            exposure_minor += var
        if integ == "UNEXPLAINED":
            unexplained_minor += abs(_to_int(u.get("integrity_residual_minor")))

        if cell in _EXCEPTION_CELLS or integ == "UNEXPLAINED":
            sev_count[sev] += 1
            sev_value[sev] += var
            exceptions.append({
                "cell": cell, "bucket": u.get("bucket", ""), "severity": sev,
                "diagnosis": u.get("diagnosis", ""), "cardinality": u.get("cardinality", ""),
                "integrity": integ, "value": _cur(var, exp),
            })

        if u.get("match_tier") in _SUGGESTION_TIERS and u.get("match_status") != "SUPERSEDED":
            sug_value_minor += var
            sug_by_band[u.get("confidence_band", "LOW")] += 1
            if str(u.get("is_ambiguous", "")).lower() == "true":
                ambiguous += 1
            if u.get("search_mode") == "heuristic":
                heuristic += 1
            suggestions.append({
                "tier": u.get("match_tier"), "cardinality": u.get("cardinality", ""),
                "band": u.get("confidence_band", "LOW"), "cell": cell,
                "diagnosis": u.get("diagnosis", ""), "value": _cur(var, exp),
                "is_ambiguous": str(u.get("is_ambiguous", "")).lower() == "true",
            })

    assur = cov.get("assurance_pct_by_plane", {}) or {}
    assur_vals = [v for v in assur.values() if v is not None]
    assurance = min(assur_vals) if assur_vals else None

    conservation_ok = bool(cov.get("conservation_ok", man.get("conservation", True)))
    completeness = man.get("country_completeness", "unknown")

    exceptions.sort(key=lambda e: (-_SEV_RANK.get(e["severity"], 0), -e["value"]))
    suggestions.sort(key=lambda s: -s["value"])

    eng = {
        "run_dir": os.path.relpath(run_dir),
        "country": country,
        "client": man.get("client", ""),
        "period": period,
        "currency": currency,
        "minor_exp": exp,
        "entities": entities,
        "completeness": completeness,
        "pack_version": man.get("country_pack_version") or pack.get("pack_version"),
        "engine_version": man.get("engine_version"),
        "timestamp_utc": man.get("timestamp_utc"),
        "conservation_ok": conservation_ok,
        "quarantined": _to_int(cov.get("quarantined")),
        "awkey_coverage": cov.get("awkey_coverage"),
        "docs": cov.get("docs", {}),
        "units_by_tier": cov.get("units_by_tier", {}),
        "assurance": assurance,
        "exposure": _cur(exposure_minor, exp),
        "exposure_minor": exposure_minor,
        "unexplained_residual": _cur(unexplained_minor, exp),
        "exception_count": sum(sev_count.values()),
        "critical_count": sev_count.get("CRITICAL", 0) + sev_count.get("HIGH", 0),
        "sev_count": dict(sev_count),
        "open_suggestions": len(suggestions),
        "suggestion_value": _cur(sug_value_minor, exp),
        "sug_by_band": dict(sug_by_band),
        "ambiguous_suggestions": ambiguous,
        "heuristic_suggestions": heuristic,
        "warnings": man.get("warnings", []),
        "open_decisions": man.get("open_decisions", []),
        "top_exceptions": exceptions[:8],
        "top_suggestions": suggestions[:8],
    }
    eng["engagement"] = f"{country} · {man.get('client','')}" + (f" · {period}" if period else "")
    eng["attention"] = _attention(eng)
    return eng


def _attention(e):
    """A single ranked posture used to sort and colour the estate.

    CRITICAL: conservation broke, or there is billed-unreported / reported-
    unbooked exposure -- real tax money is unaccounted for. REVIEW: exceptions
    or a backlog awaiting a human. CLEAR otherwise.
    """
    if not e["conservation_ok"]:
        return {"level": "CRITICAL", "reason": "conservation check failed"}
    if e["exposure"] > 0:
        return {"level": "CRITICAL",
                "reason": "completeness / reverse-completeness exposure"}
    if e["critical_count"] > 0:
        return {"level": "REVIEW", "reason": "high-severity exceptions open"}
    if e["open_suggestions"] > 0:
        return {"level": "REVIEW", "reason": "suggestions awaiting decision"}
    if e["exception_count"] > 0 or e["unexplained_residual"] > 0:
        return {"level": "REVIEW", "reason": "exceptions to review"}
    return {"level": "CLEAR", "reason": "deterministically reconciled"}


_ATTN_RANK = {"CRITICAL": 3, "REVIEW": 2, "CLEAR": 1}


# --------------------------------------------------------------------------- #
# Portfolio aggregation
# --------------------------------------------------------------------------- #
def aggregate(engagements: list[dict]) -> dict:
    engagements = sorted(
        engagements,
        key=lambda e: (-_ATTN_RANK.get(e["attention"]["level"], 0), -e["exposure_minor"]),
    )

    # Money is only ever summed within a currency (engine guardrail).
    by_ccy = {}
    for e in engagements:
        c = e["currency"] or "—"
        b = by_ccy.setdefault(c, {"currency": c, "exposure": 0.0,
                                  "suggestion_value": 0.0, "unexplained": 0.0,
                                  "engagements": 0})
        b["exposure"] += e["exposure"]
        b["suggestion_value"] += e["suggestion_value"]
        b["unexplained"] += e["unexplained_residual"]
        b["engagements"] += 1
    currencies = sorted(by_ccy.values(), key=lambda b: -b["exposure"])

    # Value-weighted assurance is currency-agnostic (a ratio), but weighting by
    # raw amount across currencies would be dishonest, so weight by matched
    # tax value *within* currency then average by that currency's total.
    assur_num = assur_den = 0.0
    for e in engagements:
        if e["assurance"] is None:
            continue
        w = max(e["docs"].get("gl", 0) + e["docs"].get("ar", 0) + e["docs"].get("einv", 0), 1)
        assur_num += e["assurance"] * w
        assur_den += w
    weighted_assurance = (assur_num / assur_den) if assur_den else None

    sev_total = Counter()
    for e in engagements:
        for s, n in e["sev_count"].items():
            sev_total[s] += n

    countries = sorted({e["country"] for e in engagements})
    clients = sorted({e["client"] for e in engagements if e["client"]})

    # Cross-estate risk register: every exception, tagged with its engagement,
    # ranked by severity then value. Money stays currency-tagged.
    register = []
    for e in engagements:
        for x in e["top_exceptions"]:
            register.append({**x, "engagement": e["engagement"],
                             "country": e["country"], "currency": e["currency"]})
    register.sort(key=lambda r: (-_SEV_RANK.get(r["severity"], 0), -r["value"]))

    return {
        "generated_meta": {
            "engagements": len(engagements),
            "countries": countries,
            "clients": clients,
            "currencies": [c["currency"] for c in currencies],
        },
        "headline": {
            "exposure_by_ccy": currencies,
            "weighted_assurance_pct": round(weighted_assurance * 100, 1)
            if weighted_assurance is not None else None,
            "open_suggestions": sum(e["open_suggestions"] for e in engagements),
            "exception_count": sum(e["exception_count"] for e in engagements),
            "attention_critical": sum(1 for e in engagements
                                      if e["attention"]["level"] == "CRITICAL"),
            "attention_review": sum(1 for e in engagements
                                    if e["attention"]["level"] == "REVIEW"),
            "attention_clear": sum(1 for e in engagements
                                   if e["attention"]["level"] == "CLEAR"),
            "conservation_failures": sum(1 for e in engagements
                                         if not e["conservation_ok"]),
            "partial_packs": sum(1 for e in engagements
                                 if e["completeness"] != "complete"),
        },
        "severity_totals": dict(sev_total),
        "engagements": engagements,
        "register": register[:60],
    }


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
def build(run_dirs, out_path, config_dir=None, title="GCC Command Center"):
    engagements = []
    skipped = []
    for d in run_dirs:
        try:
            e = load_run(d, config_dir)
        except Exception as ex:  # noqa: BLE001 - one bad run must not sink the tower
            e, ex_msg = None, str(ex)
            skipped.append({"run_dir": d, "error": ex_msg})
        if e is not None:
            engagements.append(e)
        elif not skipped or skipped[-1]["run_dir"] != d:
            skipped.append({"run_dir": d, "error": "missing coverage/manifest"})

    if not engagements:
        raise SystemExit(
            "command_center: no runs with coverage_summary.json + run_manifest.json "
            f"found in: {', '.join(run_dirs) or '(none)'}")

    data = aggregate(engagements)
    data["title"] = title
    data["skipped"] = skipped

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    html = _TEMPLATE.replace("__DATA__", json.dumps(data))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GCC Command Center</title>
<style>
:root{
  --chrome-bg:#0E1420;--chrome-text:#E6EAF2;--chrome-muted:#8A97A8;--chrome-line:#2A374C;--navy:#22304A;
  --surface:#F6F7F9;--card:#FFFFFF;--border:#E3E7EE;--border-strong:#D3D9E2;--hover:#F0F4F9;
  --tp:#16202E;--ts:#5B6B7F;--tm:#8A97A8;--green:#1E9E6A;--amber:#D98E04;--red:#C6373C;
  --govern:#6C5AC2;--cat-1:#4A90A4;--cat-2:#B87333;--cat-3:#5A6E8C;--cat-4:#7A5E8A;
}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--surface);color:var(--tp);font-size:13px;line-height:1.5}
#app{max-width:1240px;margin:0 auto}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
.eyebrow{font-size:10.5px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--tm)}
.chrome{background:var(--chrome-bg);color:var(--chrome-text);padding:14px 32px 0}
.chrome-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.brand{font-size:15px;font-weight:600}
.brand small{display:block;font-size:10.5px;font-weight:400;color:var(--chrome-muted);letter-spacing:.05em;text-transform:uppercase;margin-top:2px}
.chrome-controls{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.chrome-pill{background:#1A2333;border:1px solid var(--chrome-line);padding:6px 12px;border-radius:20px;font:500 11px Inter;color:var(--chrome-text)}
.tabbar{display:flex;gap:4px;margin-top:14px;border-bottom:1px solid var(--chrome-line);flex-wrap:wrap}
.tab{background:transparent;border:none;color:#9FB0C6;padding:10px 16px;font:500 12.5px Inter;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab:hover{color:#E6EAF2}.tab.on{color:#fff;border-bottom-color:#fff}
.wrap{padding:28px 32px}
.page{display:none}.page.on{display:block}
.briefing{background:var(--navy);color:#EAF0F8;padding:26px 32px;border-radius:12px;margin-bottom:24px}
.briefing-label{font-size:10.5px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:#8ea3c4;margin-bottom:10px}
.briefing h1{font-size:22px;font-weight:500;letter-spacing:-.01em;margin:0 0 6px;line-height:1.35}
.briefing p{margin:0;color:#c2cee2;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px}
.kpi .v{font-size:26px;font-weight:600;letter-spacing:-.01em;margin-top:6px}
.kpi .l{font-size:11px;color:var(--tm);text-transform:uppercase;letter-spacing:.06em}
.kpi .sub{font-size:11px;color:var(--tm);margin-top:6px}
.kpi.red .v{color:var(--red)}.kpi.green .v{color:var(--green)}.kpi.amber .v{color:var(--amber)}
.kpi .stack{display:flex;flex-direction:column;gap:2px;margin-top:6px}
.kpi .stack span{font-size:15px;font-weight:600}
.section-head{display:flex;align-items:baseline;gap:12px;margin:8px 0 16px}
.section-head h2{font-size:16px;font-weight:600;margin:0}
.section-head .hint{color:var(--tm);font-size:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.cellchip{font:600 12px Inter;padding:3px 8px;border-radius:6px;text-align:center;display:inline-block}
.sev-CRITICAL{background:#fbe9ea;color:var(--red)}.sev-HIGH{background:#fdf1e0;color:var(--amber)}
.sev-REVIEW{background:#eef1f6;color:var(--ts)}.sev-INFO{background:#e8f3ee;color:var(--green)}.sev-SUPPRESSED{background:#eef1f6;color:var(--tm)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;font-weight:500;color:var(--tm);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;padding:8px 10px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:10px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
.tag{display:inline-block;font:500 10.5px Inter;padding:2px 7px;border-radius:5px;background:var(--hover);color:var(--ts)}
.tag.hi{background:#e8f3ee;color:var(--green)}.tag.med{background:#fdf1e0;color:var(--amber)}.tag.lo{background:#eef1f6;color:var(--tm)}
.tag.amb{background:#fbe9ea;color:var(--red)}.tag.crit{background:#fbe9ea;color:var(--red)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:middle}
.dot.CRITICAL{background:var(--red)}.dot.REVIEW{background:var(--amber)}.dot.CLEAR{background:var(--green)}
.assbar{position:relative;height:8px;border-radius:4px;background:#e9edf3;width:90px;display:inline-block;vertical-align:middle;overflow:hidden}
.assbar > i{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.rowlink{cursor:pointer}.rowlink:hover{background:var(--hover)}
.mono{font-variant-numeric:tabular-nums}
.warn{background:#fdf1e0;border:1px solid #f3d9a6;border-radius:8px;padding:10px 14px;margin-bottom:10px;color:#8a5a00;font-size:12px}
.gap{border:1px dashed var(--border-strong);border-radius:12px;padding:18px 20px;color:var(--tm);background:repeating-linear-gradient(45deg,#fafbfc,#fafbfc 10px,#f4f6f8 10px,#f4f6f8 20px)}
.split{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:11.5px;color:var(--ts);margin-top:4px}
.legend .dot{margin-right:5px}
.attn{display:flex;flex-direction:column;gap:8px}
.attn-row{display:grid;grid-template-columns:14px 1fr auto;align-items:center;gap:12px;padding:11px 14px;border:1px solid var(--border);border-radius:10px;background:var(--card)}
.attn-row .why{font-size:11.5px;color:var(--tm)}
.stackbar{display:flex;height:22px;border-radius:6px;overflow:hidden;border:1px solid var(--border)}
.stackbar > i{display:block}
.foot{padding:20px 32px;color:var(--tm);font-size:11px}
@media(max-width:900px){.kpis{grid-template-columns:repeat(2,1fr)}.split{grid-template-columns:1fr}}
</style></head>
<body><div id="app">
  <div class="chrome">
    <div class="chrome-row">
      <div class="brand">GCC Command Center<small>Three-way reconciliation · portfolio control tower</small></div>
      <div class="chrome-controls" id="chrome-pills"></div>
    </div>
    <div class="tabbar" id="tabs"></div>
  </div>
  <div class="wrap">
    <div class="page on" id="p1"></div>
    <div class="page" id="p2"></div>
    <div class="page" id="p3"></div>
    <div class="page" id="p4"></div>
    <div class="page" id="p5"></div>
  </div>
  <div class="foot">Aggregated from per-run artifacts only (coverage_summary.json, run_manifest.json, recon_units.csv). Deterministic engine · no LLM in the matching path. Monetary value is never summed across currencies.</div>
</div>
<script>
const DATA = __DATA__;
const E = DATA.engagements;
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const nf=n=>Number(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const money=(n,ccy)=>(n==null?"—":(ccy?ccy+" ":"")+nf(n));
const pct=v=>v==null?"—":v+"%";
function sectionHead(h,hint){const d=el("div","section-head");d.appendChild(el("h2",null,h));if(hint)d.appendChild(el("span","hint",hint));return d;}
function assColor(v){return v==null?"var(--tm)":v>=0.97?"var(--green)":v>=0.90?"var(--amber)":"var(--red)";}

// chrome pills
(function(){const c=document.getElementById("chrome-pills");const m=DATA.generated_meta;
 c.appendChild(el("span","chrome-pill",m.engagements+" engagements"));
 c.appendChild(el("span","chrome-pill",m.countries.join(" · ")));
 const cons=DATA.headline.conservation_failures;
 const p=el("span","chrome-pill",cons?("conservation ✗ ×"+cons):"conservation ✓");
 p.style.color=cons?"#f0a0a2":"#7fd7b0";c.appendChild(p);
})();

const PAGES=[["Command Center","p1"],["Estate map","p2"],["Risk register","p3"],["Suggestion backlog","p4"],["Operations","p5"]];
const tabs=document.getElementById("tabs");
PAGES.forEach(([name,id],i)=>{const b=el("button","tab"+(i==0?" on":""),name);
 b.onclick=()=>{document.querySelectorAll(".tab").forEach(t=>t.classList.remove("on"));b.classList.add("on");
 document.querySelectorAll(".page").forEach(p=>p.classList.remove("on"));document.getElementById(id).classList.add("on");};
 tabs.appendChild(b);});

function gotoEstate(){document.querySelectorAll(".tab").forEach((t,i)=>t.classList.toggle("on",i==1));
 document.querySelectorAll(".page").forEach(p=>p.classList.remove("on"));document.getElementById("p2").classList.add("on");window.scrollTo(0,0);}

// ---- Page 1: Command Center ----
(function(){const p=document.getElementById("p1");const h=DATA.headline;const m=DATA.generated_meta;
 const crit=h.attention_critical, rev=h.attention_review, clr=h.attention_clear;
 const lead = crit>0
   ? (crit+" of "+m.engagements+" engagements carry unaccounted tax exposure or a broken conservation check.")
   : (rev>0 ? "No unaccounted exposure across the estate; "+rev+" engagements have items awaiting a human decision."
            : "Every engagement in the estate is deterministically reconciled and conserved.");
 const b=el("div","briefing");
 b.appendChild(el("div","briefing-label","Estate briefing · "+m.countries.join(", ")+" · "+m.engagements+" engagements"));
 b.appendChild(el("h1",null,lead));
 const ex=h.exposure_by_ccy.filter(c=>c.exposure>0).map(c=>money(c.exposure,c.currency)).join(" · ");
 b.appendChild(el("p",null,"Value-weighted deterministic assurance is "+pct(h.weighted_assurance_pct)+" across the book. "
   +h.open_suggestions+" suggested matches await decision. "
   +(ex?("Open completeness / reverse-completeness exposure: "+ex+"."):"No completeness exposure detected.")));
 p.appendChild(b);

 const k=el("div","kpis");
 // exposure tile (per-currency stack)
 const exTile=el("div","kpi "+(crit>0?"red":"green"));
 exTile.appendChild(el("div","l","Exposure (E2 + E7)"));
 const exPos=h.exposure_by_ccy.filter(c=>c.exposure>0);
 if(exPos.length){const st=el("div","stack");exPos.forEach(c=>st.appendChild(el("span","num",money(c.exposure,c.currency))));exTile.appendChild(st);}
 else {exTile.appendChild(el("div","v num","0.00"));}
 exTile.appendChild(el("div","sub","never summed across currencies"));
 k.appendChild(exTile);

 const kpi=(cls,val,lab,sub)=>{const d=el("div","kpi "+cls);d.appendChild(el("div","l",lab));d.appendChild(el("div","v num",val));if(sub)d.appendChild(el("div","sub",sub));return d;};
 k.appendChild(kpi("green",pct(h.weighted_assurance_pct),"Weighted assurance","value-weighted, T0–T2"));
 k.appendChild(kpi(h.open_suggestions?"amber":"green",h.open_suggestions,"Open suggestions","across all engagements"));
 k.appendChild(kpi(h.exception_count?"amber":"green",h.exception_count,"Open exceptions",h.partial_packs+" engagement(s) on partial packs"));
 p.appendChild(k);

 // posture stack bar
 const pc=el("div","card");
 pc.appendChild(el("div","eyebrow","Estate posture"));
 const total=Math.max(1,crit+rev+clr);
 const sb=el("div","stackbar");sb.style.marginTop="10px";
 const seg=(n,col,lab)=>{if(n<=0)return;const i=el("i");i.style.width=(100*n/total)+"%";i.style.background=col;i.title=lab+": "+n;sb.appendChild(i);};
 seg(crit,"var(--red)","Critical");seg(rev,"var(--amber)","Review");seg(clr,"var(--green)","Clear");
 pc.appendChild(sb);
 const lg=el("div","legend");
 lg.innerHTML="<span><span class='dot CRITICAL'></span>Critical "+crit+"</span>"
   +"<span><span class='dot REVIEW'></span>Review "+rev+"</span>"
   +"<span><span class='dot CLEAR'></span>Clear "+clr+"</span>";
 pc.appendChild(lg);
 p.appendChild(pc);

 // attention list
 p.appendChild(sectionHead("Needs attention first","Engagements ranked by posture, then value at risk"));
 const attn=el("div","attn");
 const ranked=E.filter(e=>e.attention.level!=="CLEAR");
 if(!ranked.length){attn.appendChild(el("div","gap","Nothing needs attention. Every engagement is clean and conserved."));}
 ranked.slice(0,8).forEach(e=>{const r=el("div","attn-row rowlink");
   r.onclick=gotoEstate;
   r.appendChild(el("span","dot "+e.attention.level));
   const mid=el("div");
   mid.appendChild(el("div",null,"<b>"+e.engagement+"</b>"));
   mid.appendChild(el("div","why",e.attention.reason
     +(e.open_suggestions?(" · "+e.open_suggestions+" suggestions"):"")
     +(e.exception_count?(" · "+e.exception_count+" exceptions"):"")));
   r.appendChild(mid);
   const right=el("div","num");right.style.textAlign="right";
   right.innerHTML="<div style='font-weight:600'>"+(e.exposure>0?money(e.exposure,e.currency):"—")+"</div>"
     +"<div class='why'>assurance "+pct(e.assurance==null?null:(e.assurance*100).toFixed(1))+"</div>";
   r.appendChild(right);
   attn.appendChild(r);});
 p.appendChild(attn);
})();

// ---- Page 2: Estate map ----
(function(){const p=document.getElementById("p2");
 p.appendChild(sectionHead("Estate map","One row per engagement. Sortable; click a header. Money is currency-tagged, never blended."));
 const c=el("div","card");c.style.overflowX="auto";
 const t=el("table");
 const cols=[["","attn",false],["Engagement","engagement",false],["Period","period",false],
   ["Assurance","assurance",true],["Exposure","exposure",true],["Suggestions","open_suggestions",true],
   ["Exceptions","exception_count",true],["Unexplained","unexplained_residual",true],
   ["Quarantine","quarantined",true],["Conserv.","conservation_ok",false],["Pack","completeness",false]];
 const thead=el("thead");const htr=el("tr");
 cols.forEach(([lab,key,num])=>{const th=el("th",null,lab);if(num)th.style.textAlign="right";
   th.style.cursor="pointer";th.onclick=()=>sortBy(key,num);htr.appendChild(th);});
 thead.appendChild(htr);t.appendChild(thead);
 const tb=el("tbody");t.appendChild(tb);
 let sortKey="attn",sortNum=false,dir=-1;
 function sortBy(key,num){if(key===sortKey)dir=-dir;else{sortKey=key;sortNum=num;dir=num?-1:1;}render();}
 const rank={CRITICAL:3,REVIEW:2,CLEAR:1};
 function render(){tb.innerHTML="";
   const rows=E.slice().sort((a,b)=>{
     let va,vb;
     if(sortKey==="attn"){va=rank[a.attention.level];vb=rank[b.attention.level];if(va===vb){va=a.exposure;vb=b.exposure;}}
     else{va=a[sortKey];vb=b[sortKey];}
     if(va==null)va=sortNum?-1:"";if(vb==null)vb=sortNum?-1:"";
     if(va<vb)return -1*dir;if(va>vb)return 1*dir;return 0;});
   rows.forEach(e=>{const tr=el("tr");
     const a=(e.assurance==null)?null:(e.assurance*100);
     tr.innerHTML=
       "<td><span class='dot "+e.attention.level+"' title='"+e.attention.reason+"'></span></td>"+
       "<td><b>"+e.country+"</b> · "+e.client+"<div class='why' style='color:var(--tm);font-size:11px'>"+(e.entities.length?e.entities.length+" entities":"")+"</div></td>"+
       "<td class='num'>"+(e.period||"—")+"</td>"+
       "<td class='num' style='text-align:right'>"+(a==null?"—":"<span class='assbar'><i style='width:"+Math.max(3,a)+"%;background:"+assColor(e.assurance)+"'></i></span> "+a.toFixed(1)+"%")+"</td>"+
       "<td class='num' style='text-align:right;"+(e.exposure>0?"color:var(--red);font-weight:600":"")+"'>"+(e.exposure>0?money(e.exposure,e.currency):"—")+"</td>"+
       "<td class='num' style='text-align:right'>"+(e.open_suggestions||"—")+(e.ambiguous_suggestions?" <span class='tag amb'>"+e.ambiguous_suggestions+" amb</span>":"")+"</td>"+
       "<td class='num' style='text-align:right'>"+(e.exception_count||"—")+(e.critical_count?" <span class='tag crit'>"+e.critical_count+"</span>":"")+"</td>"+
       "<td class='num' style='text-align:right'>"+(e.unexplained_residual>0?money(e.unexplained_residual,e.currency):"—")+"</td>"+
       "<td class='num' style='text-align:right'>"+(e.quarantined||"—")+"</td>"+
       "<td>"+(e.conservation_ok?"<span class='tag hi'>✓</span>":"<span class='tag amb'>✗</span>")+"</td>"+
       "<td>"+(e.completeness==="complete"?"<span class='tag hi'>complete</span>":"<span class='tag med'>"+e.completeness+"</span>")+"</td>";
     tb.appendChild(tr);});}
 render();
 c.appendChild(t);p.appendChild(c);
 p.appendChild(el("div",null,"<div style='font-size:12px;color:var(--tm)'>E2 (billed, unreported) and E7 (reported, unbooked) drive exposure. Partial country packs warn rather than assume; treat their assurance as provisional.</div>"));
})();

// ---- Page 3: Risk register ----
(function(){const p=document.getElementById("p3");
 p.appendChild(sectionHead("Risk register","Every open exception across the estate, ranked by severity then value. Full evidence lives in each run's dashboard."));
 if(!DATA.register.length){p.appendChild(el("div","gap","No exceptions anywhere in the estate. Nothing to escalate."));return;}
 // severity summary
 const sev=DATA.severity_totals;const order=["CRITICAL","HIGH","REVIEW","INFO","SUPPRESSED"];
 const sc=el("div","card");sc.appendChild(el("div","eyebrow","Exceptions by severity"));
 const row=el("div");row.style.cssText="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px";
 order.forEach(s=>{if(!sev[s])return;row.appendChild(el("span","cellchip sev-"+s,s+" · "+sev[s]));});
 sc.appendChild(row);p.appendChild(sc);
 const c=el("div","card");c.style.overflowX="auto";
 const t=el("table");
 t.innerHTML="<thead><tr><th>Sev</th><th>Cell</th><th>Engagement</th><th>Bucket</th><th>Diagnosis</th><th>Card.</th><th style='text-align:right'>Value</th></tr></thead>";
 const tb=el("tbody");
 DATA.register.forEach(r=>{const tr=el("tr");
   tr.innerHTML="<td><span class='tag sev-"+r.severity+"'>"+r.severity+"</span></td>"+
     "<td><span class='cellchip sev-"+r.severity+"'>"+r.cell+"</span></td>"+
     "<td>"+r.engagement+"</td>"+
     "<td>"+r.bucket+(r.integrity==="UNEXPLAINED"?" <span class='tag amb'>residual</span>":"")+"</td>"+
     "<td>"+r.diagnosis+"</td>"+
     "<td class='num'>"+r.cardinality+"</td>"+
     "<td class='num' style='text-align:right'>"+money(r.value,r.currency)+"</td>";
   tb.appendChild(tr);});
 t.appendChild(tb);c.appendChild(t);p.appendChild(c);
})();

// ---- Page 4: Suggestion backlog ----
(function(){const p=document.getElementById("p4");
 p.appendChild(sectionHead("Suggestion backlog","T3–T5 correspondence proposals awaiting a human decision. Nothing here is auto-applied; ambiguous units are never auto-accepted."));
 const tot=DATA.headline.open_suggestions;
 if(!tot){p.appendChild(el("div","gap","No open suggestions. All correspondence resolved deterministically at T0–T2 across the estate."));return;}
 const band=n=>({HIGH:0,MEDIUM:0,LOW:0}), b={HIGH:0,MEDIUM:0,LOW:0};let amb=0,heur=0;
 E.forEach(e=>{for(const[k,v]of Object.entries(e.sug_by_band||{}))b[k]=(b[k]||0)+v;amb+=e.ambiguous_suggestions;heur+=e.heuristic_suggestions;});
 const k=el("div","kpis");
 const kpi=(cls,v,l,s)=>{const d=el("div","kpi "+cls);d.appendChild(el("div","l",l));d.appendChild(el("div","v num",v));if(s)d.appendChild(el("div","sub",s));return d;};
 k.appendChild(kpi("",tot,"Open suggestions","across "+E.filter(e=>e.open_suggestions).length+" engagements"));
 k.appendChild(kpi(b.HIGH?"green":"",b.HIGH||0,"High confidence","band ≥ 0.85"));
 k.appendChild(kpi(amb?"red":"green",amb,"Ambiguous","never auto-accepted"));
 k.appendChild(kpi("",heur,"Heuristic search","large blocks, exact search capped"));
 p.appendChild(k);
 const c=el("div","card");c.style.overflowX="auto";
 const t=el("table");
 t.innerHTML="<thead><tr><th>Engagement</th><th style='text-align:right'>Open</th><th>High</th><th>Med</th><th>Low</th><th>Ambiguous</th><th style='text-align:right'>Value awaiting</th></tr></thead>";
 const tb=el("tbody");
 E.filter(e=>e.open_suggestions>0).sort((a,b)=>b.open_suggestions-a.open_suggestions).forEach(e=>{
   const sb=e.sug_by_band||{};const tr=el("tr");
   tr.innerHTML="<td><b>"+e.country+"</b> · "+e.client+(e.period?" · "+e.period:"")+"</td>"+
     "<td class='num' style='text-align:right'>"+e.open_suggestions+"</td>"+
     "<td class='num'>"+(sb.HIGH||0)+"</td><td class='num'>"+(sb.MEDIUM||0)+"</td><td class='num'>"+(sb.LOW||0)+"</td>"+
     "<td class='num'>"+(e.ambiguous_suggestions?"<span class='tag amb'>"+e.ambiguous_suggestions+"</span>":"—")+"</td>"+
     "<td class='num' style='text-align:right'>"+money(e.suggestion_value,e.currency)+"</td>";
   tb.appendChild(tr);});
 t.appendChild(tb);c.appendChild(t);p.appendChild(c);
})();

// ---- Page 5: Operations ----
(function(){const p=document.getElementById("p5");
 p.appendChild(sectionHead("Operations & data health","Conservation, config completeness, warnings and freshness across every run"));
 const h=DATA.headline;
 const grid=el("div","kpis");
 const mk=(cls,v,l,s)=>{const d=el("div","kpi "+cls);d.appendChild(el("div","l",l));d.appendChild(el("div","v num",v));if(s)d.appendChild(el("div","sub",s));return d;};
 grid.appendChild(mk(h.conservation_failures?"red":"green",h.conservation_failures?h.conservation_failures:"PASS","Conservation",h.conservation_failures?"engagement(s) failed":"all engagements balanced"));
 grid.appendChild(mk(h.partial_packs?"amber":"green",h.partial_packs,"Partial country packs","assurance provisional where partial"));
 const totQ=E.reduce((a,e)=>a+(e.quarantined||0),0);
 grid.appendChild(mk(totQ?"amber":"green",totQ,"Quarantined rows","never silently dropped"));
 const vers=[...new Set(E.map(e=>e.engine_version).filter(Boolean))];
 grid.appendChild(mk(vers.length>1?"amber":"",vers.join(", ")||"—","Engine version",vers.length>1?"mixed versions in estate":"consistent"));
 p.appendChild(grid);

 // warnings grouped by engagement
 const warned=E.filter(e=>e.warnings&&e.warnings.length);
 if(warned.length){const c=el("div","card");c.appendChild(el("div","eyebrow","Warnings"));
   warned.forEach(e=>{e.warnings.forEach(w=>{const d=el("div","warn","<b>"+e.engagement+"</b> — "+w);c.appendChild(d);});});
   p.appendChild(c);}

 // freshness table
 const c=el("div","card");c.style.overflowX="auto";c.appendChild(el("div","eyebrow","Run freshness & footprint"));
 const t=el("table");t.style.marginTop="10px";
 t.innerHTML="<thead><tr><th>Engagement</th><th>Run at (UTC)</th><th>Pack</th><th style='text-align:right'>GL</th><th style='text-align:right'>AR</th><th style='text-align:right'>E-inv</th><th>Source</th></tr></thead>";
 const tb=el("tbody");
 E.slice().sort((a,b)=>String(b.timestamp_utc).localeCompare(String(a.timestamp_utc))).forEach(e=>{const tr=el("tr");
   const ts=e.timestamp_utc?e.timestamp_utc.replace("T"," ").slice(0,16):"—";
   tr.innerHTML="<td><b>"+e.country+"</b> · "+e.client+(e.period?" · "+e.period:"")+"</td>"+
     "<td class='num'>"+ts+"</td>"+
     "<td class='num'>"+(e.pack_version||"—")+"</td>"+
     "<td class='num' style='text-align:right'>"+(e.docs.gl||0)+"</td>"+
     "<td class='num' style='text-align:right'>"+(e.docs.ar||0)+"</td>"+
     "<td class='num' style='text-align:right'>"+(e.docs.einv||0)+"</td>"+
     "<td class='num' style='color:var(--tm);font-size:11px'>"+e.run_dir+"</td>";
   tb.appendChild(tr);});
 t.appendChild(tb);c.appendChild(t);p.appendChild(c);

 if(DATA.skipped&&DATA.skipped.length){const s=el("div","card");s.appendChild(el("div","eyebrow","Skipped run directories"));
   s.innerHTML+="<div style='margin-top:8px'>"+DATA.skipped.map(x=>"<span class='tag'>"+x.run_dir+" — "+x.error+"</span>").join(" ")+"</div>";p.appendChild(s);}
})();
</script>
</body></html>
"""
