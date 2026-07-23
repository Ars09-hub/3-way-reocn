"""Dashboard builder (spec §18).

Emits a single self-contained, exec-first HTML file (no external runtime
dependencies) with five pages: Headline, Three-way status, Suggestion queue,
Exceptions, Data quality. Styled with Clear design tokens. Accept / Reject /
Escalate decisions are captured client-side and exportable as decisions.jsonl
so a re-run can honour prior human decisions.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal


def _cur(minor, exp):
    q = Decimal(1).scaleb(-exp)
    return float((Decimal(int(minor)) * q).quantize(q))


def _member_view(u, doc_by_id, exp):
    out = []
    for rid in u["member_ids"]:
        d = doc_by_id.get(rid, {})
        out.append({
            "plane": d.get("plane"),
            "doc": d.get("billing_doc_id") or d.get("accounting_doc_id") or d.get("doc_id_native"),
            "date": d.get("doc_date"),
            "tax": _cur(d.get("tax_minor", 0), exp),
            "net": _cur(d.get("net_minor", 0), exp),
            "gross": _cur(d.get("gross_minor", 0), exp),
            "cp": d.get("counterparty_tin"),
        })
    return out


def _build_data(result, written):
    cfg = result["cfg"]
    exp = cfg.minor_exp
    units = result["units"]
    doc_by_id = {d["row_id"]: d for d in result["docs"]}
    cov = written["coverage"]

    cell_value = {f"E{i}": 0.0 for i in range(1, 8)}
    cell_count = {f"E{i}": 0 for i in range(1, 8)}
    exposure = 0.0
    unexplained = 0.0
    for u in units:
        c = u["existence_cell"]
        if c in cell_value:
            cell_value[c] += _cur(u["value_at_risk_minor"], exp)
            cell_count[c] += 1
        if c in ("E2", "E7"):
            exposure += _cur(u["value_at_risk_minor"], exp)
        if u["integrity"]["status"] == "UNEXPLAINED":
            unexplained += abs(_cur(u["integrity"]["residual_minor"], exp))

    suggestions = []
    for u in units:
        if u["match_tier"] in ("T3", "T4", "T5") and u["match_status"] != "SUPERSEDED":
            suggestions.append({
                "unit_id": u["unit_id"], "cardinality": u["cardinality"],
                "tier": u["match_tier"], "confidence": u["confidence"],
                "band": u["confidence_band"], "cell": u["existence_cell"],
                "bucket": u["bucket"], "diagnosis": u["diagnosis"],
                "is_ambiguous": u["is_ambiguous"], "alternatives": u["alternatives_count"],
                "degeneracy": u["degeneracy_reason"], "search_mode": u["search_mode"],
                "value": _cur(u["value_at_risk_minor"], exp),
                "planes": {p: {k: (_cur(v, exp) if v is not None else None)
                               for k, v in vals.items() if k in ("gl", "ar", "einv")}
                           for p, vals in u["planes"].items()},
                "members": _member_view(u, doc_by_id, exp),
                "alts": u.get("alternatives_top3", []),
            })
    suggestions.sort(key=lambda s: -s["value"])

    exceptions = []
    for u in units:
        if u["existence_cell"] in ("E2", "E4", "E5", "E7") or u["integrity"]["status"] == "UNEXPLAINED":
            exceptions.append({
                "unit_id": u["unit_id"], "cell": u["existence_cell"], "bucket": u["bucket"],
                "severity": u["severity"], "value": _cur(u["value_at_risk_minor"], exp),
                "diagnosis": u["diagnosis"], "integrity": u["integrity"]["status"],
                "members": _member_view(u, doc_by_id, exp),
                "rules": u["rules_fired"],
            })
    exceptions.sort(key=lambda e: (-_sev(e["severity"]), -e["value"]))

    total_units = len([u for u in units if u["existence_cell"] != "E6"])
    assur = cov["assurance_pct_by_plane"]
    assur_val = min([v for v in assur.values() if v is not None] or [0])

    heuristic_blocks = sum(1 for u in units if u["search_mode"] == "heuristic")
    quarantine_reasons = {}
    for q in result["ingest"].quarantine:
        r = q.get("reason", "unknown").split(":")[0]
        quarantine_reasons[r] = quarantine_reasons.get(r, 0) + 1

    return {
        "meta": {
            "country": cfg.country.get("country"),
            "client": cfg.client.get("client"),
            "currency": cfg.country.get("currency"),
            "pack_version": cfg.country.get("pack_version"),
            "completeness": cfg.country.get("completeness"),
            "conservation": result["conservation"]["ok"],
        },
        "headline": {
            "exposure": exposure,
            "assurance_pct": round(assur_val * 100, 1),
            "open_suggestions": len(suggestions),
            "unexplained_residual": unexplained,
        },
        "cells": [
            {"cell": f"E{i}", "value": round(cell_value[f'E{i}'], 2), "count": cell_count[f"E{i}"]}
            for i in range(1, 8)
        ],
        "suggestions": suggestions,
        "exceptions": exceptions,
        "coverage": cov,
        "quarantine_reasons": quarantine_reasons,
        "heuristic_blocks": heuristic_blocks,
        "warnings": cfg.warnings,
        "open_decisions": written["manifest"]["open_decisions"],
    }


def _sev(s):
    return {"SUPPRESSED": 0, "INFO": 1, "REVIEW": 2, "HIGH": 3, "CRITICAL": 4}.get(s, 0)


def build(result, written, out_path, explain=False):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = _build_data(result, written)
    html = _TEMPLATE.replace("__DATA__", json.dumps(data))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Three-way recon</title>
<style>
:root{
  --chrome-bg:#0E1420;--chrome-text:#E6EAF2;--chrome-muted:#8A97A8;--chrome-line:#2A374C;--navy:#22304A;
  --surface:#F6F7F9;--card:#FFFFFF;--border:#E3E7EE;--border-strong:#D3D9E2;--hover:#F0F4F9;
  --tp:#16202E;--ts:#5B6B7F;--tm:#8A97A8;--green:#1E9E6A;--amber:#D98E04;--red:#C6373C;
  --govern:#6C5AC2;--risk:#D98E04;--compliance:#1E9E6A;--cat-1:#4A90A4;--cat-2:#B87333;--cat-3:#5A6E8C;--cat-4:#7A5E8A;
}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--surface);color:var(--tp);font-size:13px;line-height:1.5}
#app{max-width:1200px;margin:0 auto}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
.eyebrow{font-size:10.5px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--tm)}
.chrome{background:var(--chrome-bg);color:var(--chrome-text);padding:14px 32px 0}
.chrome-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.brand{font-size:15px;font-weight:600}
.brand small{display:block;font-size:10.5px;font-weight:400;color:var(--chrome-muted);letter-spacing:.05em;text-transform:uppercase;margin-top:2px}
.chrome-controls{margin-left:auto;display:flex;gap:8px}
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
.kpi.red .v{color:var(--red)}.kpi.green .v{color:var(--green)}.kpi.amber .v{color:var(--amber)}
.section-head{display:flex;align-items:baseline;gap:12px;margin:8px 0 16px}
.section-head h2{font-size:16px;font-weight:600;margin:0}
.section-head .hint{color:var(--tm);font-size:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.flow-row{display:grid;grid-template-columns:70px 1fr 140px 70px;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid var(--border)}
.flow-row:last-child{border-bottom:none}
.cellchip{font:600 12px Inter;padding:3px 8px;border-radius:6px;text-align:center}
.bar{height:10px;border-radius:5px;background:var(--cat-3)}
.sev-CRITICAL{background:#fbe9ea;color:var(--red)}.sev-HIGH{background:#fdf1e0;color:var(--amber)}
.sev-REVIEW{background:#eef1f6;color:var(--ts)}.sev-INFO{background:#e8f3ee;color:var(--green)}.sev-SUPPRESSED{background:#eef1f6;color:var(--tm)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;font-weight:500;color:var(--tm);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;padding:8px 10px;border-bottom:1px solid var(--border)}
td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tag{display:inline-block;font:500 10.5px Inter;padding:2px 7px;border-radius:5px;background:var(--hover);color:var(--ts)}
.tag.hi{background:#e8f3ee;color:var(--green)}.tag.med{background:#fdf1e0;color:var(--amber)}.tag.lo{background:#eef1f6;color:var(--tm)}
.tag.amb{background:#fbe9ea;color:var(--red)}
.btn{border:1px solid var(--border-strong);background:var(--card);border-radius:7px;padding:5px 11px;font:500 11.5px Inter;cursor:pointer;color:var(--tp)}
.btn:hover{background:var(--hover)}
.btn.acc{border-color:#bfe3d2;color:var(--green)}.btn.rej{border-color:#f0cccd;color:var(--red)}
.sug{border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:12px;background:var(--card)}
.sug-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sug-val{margin-left:auto;font-weight:600;font-size:15px}
.plane-row{display:flex;gap:18px;margin-top:10px;flex-wrap:wrap;font-size:12px}
.plane-box{border:1px solid var(--border);border-radius:8px;padding:8px 12px;min-width:150px}
.plane-box .pl{font-size:10px;color:var(--tm);text-transform:uppercase;letter-spacing:.05em}
.delta-break{color:var(--red);font-weight:600}.delta-tie{color:var(--green)}
.exp{margin-top:10px;font-size:12px;color:var(--ts);display:none;border-top:1px dashed var(--border);padding-top:10px}
.members{margin-top:8px;font-size:11.5px;color:var(--ts)}
.members .m{display:inline-block;margin-right:12px}
.gap{border:1px dashed var(--border-strong);border-radius:12px;padding:18px 20px;color:var(--tm);background:repeating-linear-gradient(45deg,#fafbfc,#fafbfc 10px,#f4f6f8 10px,#f4f6f8 20px)}
.warn{background:#fdf1e0;border:1px solid #f3d9a6;border-radius:8px;padding:10px 14px;margin-bottom:10px;color:#8a5a00;font-size:12px}
.foot{padding:20px 32px;color:var(--tm);font-size:11px}
@media(max-width:820px){.kpis{grid-template-columns:repeat(2,1fr)}.flow-row{grid-template-columns:56px 1fr 90px 50px}}
</style></head>
<body><div id="app">
  <div class="chrome">
    <div class="chrome-row">
      <div class="brand">Three-way reconciliation<small id="scope">Revenue/Tax GL · Customer GL · E-invoice</small></div>
      <div class="chrome-controls">
        <span class="chrome-pill" id="pill-country">MY</span>
        <span class="chrome-pill" id="pill-cons">conservation</span>
      </div>
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
  <div class="foot">Deterministic engine · no LLM in the matching path · every suggestion carries evidence and a stable id. Decisions are recorded, never auto-applied.</div>
</div>
<script>
const DATA = __DATA__;
const CUR = DATA.meta.currency || "";
const fmt = n => (n==null?"-":CUR+" "+Number(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}));
const el = (t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const DECISIONS = JSON.parse(localStorage.getItem("recon_decisions")||"{}");
function record(uid,act){DECISIONS[uid]={decision:act,ts:new Date().toISOString(),unit_id:uid};localStorage.setItem("recon_decisions",JSON.stringify(DECISIONS));renderP3();}
function exportDecisions(){const lines=Object.values(DECISIONS).map(d=>JSON.stringify(d)).join("\n");const b=new Blob([lines],{type:"application/x-ndjson"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="decisions.jsonl";a.click();}

document.getElementById("pill-country").textContent = DATA.meta.country+" · "+DATA.meta.client;
const pc=document.getElementById("pill-cons");
pc.textContent = DATA.meta.conservation?"conservation ✓":"conservation ✗";
pc.style.color = DATA.meta.conservation?"#7fd7b0":"#f0a0a2";

const PAGES=[["Headline","p1"],["Three-way status","p2"],["Suggestion queue","p3"],["Exceptions","p4"],["Data quality","p5"]];
const tabs=document.getElementById("tabs");
PAGES.forEach(([name,id],i)=>{const b=el("button","tab"+(i==0?" on":""),name);b.onclick=()=>{document.querySelectorAll(".tab").forEach(t=>t.classList.remove("on"));b.classList.add("on");document.querySelectorAll(".page").forEach(p=>p.classList.remove("on"));document.getElementById(id).classList.add("on");};tabs.appendChild(b);});

// ---- Page 1: Headline ----
(function(){const h=DATA.headline;const p=document.getElementById("p1");
 const exposureTake = h.exposure>0 ? "There is unreported and unbooked exposure to clear." : "No completeness or reverse-completeness exposure detected.";
 const b=el("div","briefing");
 b.appendChild(el("div","briefing-label","Agent briefing · "+DATA.meta.country+" · "+DATA.meta.client));
 b.appendChild(el("h1",null, exposureTake));
 b.appendChild(el("p",null, "Deterministic assurance covers "+h.assurance_pct+"% of tax value at T0 to T2. "+h.open_suggestions+" suggested matches await a human decision. "+(h.unexplained_residual>0?("Unexplained within-document residual totals "+fmt(h.unexplained_residual)+"."):"Within-document integrity is clean.")));
 p.appendChild(b);
 const k=el("div","kpis");
 const kpi=(cls,val,lab)=>{const d=el("div","kpi "+cls);d.appendChild(el("div","l",lab));d.appendChild(el("div","v num",val));return d;};
 k.appendChild(kpi(h.exposure>0?"red":"green",fmt(h.exposure),"Exposure (E2 + E7)"));
 k.appendChild(kpi("green",h.assurance_pct+"%","Assurance at T0-T2"));
 k.appendChild(kpi("amber",h.open_suggestions,"Open suggestions"));
 k.appendChild(kpi(h.unexplained_residual>0?"amber":"green",fmt(h.unexplained_residual),"Unexplained residual"));
 p.appendChild(k);
})();

// ---- Page 2: Three-way status ----
(function(){const p=document.getElementById("p2");
 p.appendChild(sectionHead("Where value lands across the seven existence cells","GL revenue/tax → customer/AR → e-invoice"));
 const meta={E1:["ALIGNED","sev-INFO"],E2:["BILLED, UNREPORTED","sev-CRITICAL"],E3:["NON-CUSTOMER SETTLED","sev-INFO"],E4:["REVENUE, NO RECEIVABLE","sev-REVIEW"],E5:["REPORTED, NO REVENUE","sev-HIGH"],E6:["RECEIVABLE MOVEMENT","sev-SUPPRESSED"],E7:["REPORTED, UNBOOKED","sev-CRITICAL"]};
 const max=Math.max(1,...DATA.cells.map(c=>c.value));
 const card=el("div","card");
 DATA.cells.forEach(c=>{const r=el("div","flow-row");
   const chip=el("div","cellchip "+meta[c.cell][1],c.cell);r.appendChild(chip);
   const barwrap=el("div");const bar=el("div","bar");bar.style.width=Math.max(2,100*c.value/max)+"%";
   if(c.cell=="E2"||c.cell=="E7")bar.style.background="var(--red)";
   else if(c.cell=="E5")bar.style.background="var(--amber)";
   else if(c.cell=="E6")bar.style.background="var(--border-strong)";
   else bar.style.background="var(--cat-3)";
   barwrap.appendChild(bar);barwrap.appendChild(el("div",null,"<span style='font-size:11px;color:var(--tm)'>"+meta[c.cell][0]+"</span>"));r.appendChild(barwrap);
   r.appendChild(el("div","num",fmt(c.value)));
   r.appendChild(el("div","num","<span style='color:var(--tm)'>"+c.count+"</span>"));
   card.appendChild(r);});
 p.appendChild(card);
 p.appendChild(el("div",null,"<div style='font-size:12px;color:var(--tm)'>E3 (non-customer settled sales) is expected and correct for cash, card and wallet settlement. E6 (receivable movement only) is suppressed, not flagged.</div>"));
})();

// ---- Page 3: Suggestion queue ----
function renderP3(){const p=document.getElementById("p3");p.innerHTML="";
 const head=el("div","section-head");
 head.appendChild(el("h2",null,"Suggestion queue"));
 head.appendChild(el("span","hint","T3-T5 proposals, sorted by value at risk. Nothing here is auto-applied."));
 const exp=el("button","btn","Export decisions.jsonl");exp.style.marginLeft="auto";exp.onclick=exportDecisions;head.appendChild(exp);
 p.appendChild(head);
 if(!DATA.suggestions.length){p.appendChild(el("div","gap","No open suggestions. All correspondence resolved deterministically at T0-T2."));return;}
 DATA.suggestions.forEach(s=>{
   const d=DECISIONS[s.unit_id];
   const box=el("div","sug");
   const top=el("div","sug-top");
   top.appendChild(el("span","tag",s.tier));
   top.appendChild(el("span","tag","card "+s.cardinality));
   top.appendChild(el("span","tag "+(s.band=="HIGH"?"hi":s.band=="MEDIUM"?"med":"lo"),s.band+" "+(s.confidence*100).toFixed(0)+"%"));
   if(s.is_ambiguous){const at=(s.degeneracy=="MULTIPLE_VALID_PARTITIONS"&&s.alternatives<=1)?"ambiguous · balanced cluster":("ambiguous · "+s.alternatives+" alternatives");top.appendChild(el("span","tag amb",at));}
   if(s.search_mode=="heuristic")top.appendChild(el("span","tag","heuristic"));
   top.appendChild(el("span","tag",s.diagnosis));
   top.appendChild(el("span","sug-val num",fmt(s.value)));
   box.appendChild(top);
   // planes
   const pr=el("div","plane-row");
   ["tax","net","gross"].forEach(pl=>{const v=s.planes[pl]||{};const bx=el("div","plane-box");
     let inner="";["gl","ar","einv"].forEach(k=>{if(v[k]!=null)inner+=k.toUpperCase()+" <span class='num'>"+fmt(v[k])+"</span><br>";});
     bx.innerHTML= "<div class='pl'>"+pl+"</div>"+inner; pr.appendChild(bx);});
   box.appendChild(pr);
   // members
   const mm=el("div","members");
   mm.innerHTML = s.members.map(m=>"<span class='m'>"+m.plane+" <b>"+(m.doc||"")+"</b> "+fmt(m.tax)+" tax</span>").join("");
   box.appendChild(mm);
   // actions / alternatives
   const act=el("div");act.style.marginTop="12px";act.style.display="flex";act.style.gap="8px";act.style.alignItems="center";
   if(d){act.appendChild(el("span","tag "+(d.decision=="ACCEPT"?"hi":d.decision=="REJECT"?"amb":"med"),"decision: "+d.decision));}
   const acc=el("button","btn acc","Accept");acc.onclick=()=>record(s.unit_id,"ACCEPT");
   const rej=el("button","btn rej","Reject");rej.onclick=()=>record(s.unit_id,"REJECT");
   const esc=el("button","btn","Escalate");esc.onclick=()=>record(s.unit_id,"ESCALATE");
   if(s.is_ambiguous){acc.disabled=true;acc.style.opacity=.4;acc.title="Ambiguous matches are never auto-accepted";}
   act.appendChild(acc);act.appendChild(rej);act.appendChild(esc);
   if(s.alts&&s.alts.length){const t=el("button","btn","Alternatives ("+s.alternatives+")");const ex=el("div","exp");
     ex.innerHTML = s.alts.map(a=>"score "+(a.score).toFixed(3)+" · "+(a.member_ids||[]).join(", ")).join("<br>");
     t.onclick=()=>{ex.style.display=ex.style.display=="block"?"none":"block";};act.appendChild(t);box.appendChild(ex);}
   box.appendChild(act);
   p.appendChild(box);
 });
}
renderP3();

// ---- Page 4: Exceptions ----
(function(){const p=document.getElementById("p4");
 p.appendChild(sectionHead("Exceptions by bucket","E2, E4, E5, E7 and within-document integrity failures, with full evidence"));
 if(!DATA.exceptions.length){p.appendChild(el("div","gap","No exceptions. Nothing to escalate."));return;}
 const c=el("div","card");
 const t=el("table");t.innerHTML="<thead><tr><th>Cell</th><th>Bucket</th><th>Severity</th><th>Diagnosis</th><th>Members</th><th class='num'>Value</th></tr></thead>";
 const tb=el("tbody");
 DATA.exceptions.forEach(e=>{const tr=el("tr");
   tr.innerHTML="<td><span class='cellchip sev-"+e.severity+"'>"+e.cell+"</span></td>"+
     "<td>"+e.bucket+(e.integrity=="UNEXPLAINED"?" <span class='tag amb'>residual</span>":"")+"</td>"+
     "<td><span class='tag sev-"+e.severity+"'>"+e.severity+"</span></td>"+
     "<td>"+e.diagnosis+"</td>"+
     "<td class='members'>"+e.members.map(m=>m.plane+" "+(m.doc||"")).join(", ")+"</td>"+
     "<td class='num'>"+fmt(e.value)+"</td>";
   tb.appendChild(tr);});
 t.appendChild(tb);c.appendChild(t);p.appendChild(c);
})();

// ---- Page 5: Data quality ----
(function(){const p=document.getElementById("p5");const cov=DATA.coverage;
 p.appendChild(sectionHead("Data quality","Coverage, quarantine, linkage and config completeness"));
 DATA.warnings.forEach(w=>p.appendChild(el("div","warn",w)));
 const grid=el("div","kpis");
 const mk=(v,l)=>{const d=el("div","kpi");d.appendChild(el("div","l",l));d.appendChild(el("div","v num",v));return d;};
 grid.appendChild(mk((cov.awkey_coverage*100).toFixed(0)+"%","AR→GL (AWKEY) coverage"));
 grid.appendChild(mk(cov.quarantined,"Quarantined rows"));
 grid.appendChild(mk(DATA.heuristic_blocks,"Heuristic-search units"));
 grid.appendChild(mk(cov.conservation_ok?"PASS":"FAIL","Conservation check"));
 p.appendChild(grid);
 const c=el("div","card");
 c.appendChild(el("div","eyebrow","Documents ingested"));
 c.innerHTML+="<div style='margin:8px 0 16px' class='num'>GL "+cov.docs.gl+" · AR "+cov.docs.ar+" · E-invoice "+cov.docs.einv+" · GL lines "+cov.gl_lines+"</div>";
 c.appendChild(el("div","eyebrow","Units by match tier"));
 c.innerHTML+="<div style='margin-top:8px' class='num'>"+Object.entries(cov.units_by_tier).map(([k,v])=>k+" "+v).join(" · ")+"</div>";
 p.appendChild(c);
 if(Object.keys(DATA.quarantine_reasons).length){const q=el("div","card");
   q.appendChild(el("div","eyebrow","Quarantine reasons"));
   q.innerHTML+="<div style='margin-top:8px'>"+Object.entries(DATA.quarantine_reasons).map(([k,v])=>"<span class='tag'>"+k+" · "+v+"</span>").join(" ")+"</div>";
   p.appendChild(q);}
 const od=el("div","card");od.appendChild(el("div","eyebrow","Open decisions (surfaced, not resolved)"));
 od.innerHTML+="<ul style='margin:8px 0 0;padding-left:18px;color:var(--ts)'>"+DATA.open_decisions.map(d=>"<li><b>"+d.id+"</b>: "+d.text+"</li>").join("")+"</ul>";
 p.appendChild(od);
})();

function sectionHead(h,hint){const d=el("div","section-head");d.appendChild(el("h2",null,h));if(hint)d.appendChild(el("span","hint",hint));return d;}
</script>
</body></html>
"""
