"""Render the GCC eInvoicing Command Center as one self-contained HTML file.

Consumes the computed dataset (compute.build_dataset) and emits a single file
with the two-dimensional navigation the skill prescribes: a scope switcher
(three GCC country cards) plus a persona / perspective tab bar, an Executive
and a Tax and Compliance view, the AR and AP pipeline and reconciliation
metric families, plain-English labels, Level 3 / 2 / 1 severity, and gap cards
where a question matters but the data is not tracked.

No cross-currency sums. No internal codes on the surface. No em dashes.
"""
from __future__ import annotations

import json
import os

from .compute import build_dataset


def build(out_path: str) -> str:
    data = build_dataset()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(data))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GCC eInvoicing Command Center</title>
<style>
:root{
  --chrome-bg:#0E1420;--chrome-text:#E6EAF2;--chrome-muted:#8A97A8;--chrome-line:#2A374C;--navy:#22304A;
  --surface:#F6F7F9;--card:#FFFFFF;--border:#E3E7EE;--border-strong:#D3D9E2;--hover:#F0F4F9;
  --tp:#16202E;--ts:#5B6B7F;--tm:#8A97A8;--green:#1E9E6A;--amber:#D98E04;--red:#C6373C;
  --govern:#6C5AC2;--risk:#D98E04;--compliance:#1E9E6A;--cat-1:#4A90A4;--cat-2:#B87333;--cat-3:#5A6E8C;--cat-4:#7A5E8A;
}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--surface);color:var(--tp);font-size:13px;line-height:1.5}
#app{max-width:1220px;margin:0 auto}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
.eyebrow{font-size:10.5px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--tm)}
/* chrome */
.chrome{background:var(--chrome-bg);color:var(--chrome-text);padding:14px 32px 0}
.chrome-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.brand{font-size:15px;font-weight:600}
.brand small{display:block;font-size:10.5px;font-weight:400;color:var(--chrome-muted);letter-spacing:.05em;text-transform:uppercase;margin-top:2px}
.chrome-controls{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.csearch{background:#1A2333;border:1px solid var(--chrome-line);border-radius:20px;padding:6px 12px;color:var(--chrome-text);font:400 11px Inter;width:190px}
.csearch::placeholder{color:#66748A}
.viewas{background:#1A2333;border:1px solid var(--chrome-line);padding:6px 30px 6px 12px;border-radius:20px;font:500 11px Inter;color:var(--chrome-text);cursor:pointer;-webkit-appearance:none;appearance:none;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' stroke='%238A97A8' stroke-width='1.2' fill='none' stroke-linecap='round'/></svg>");background-repeat:no-repeat;background-position:right 11px center}
.cpill{background:#1A2333;border:1px solid var(--chrome-line);padding:6px 12px;border-radius:20px;font:500 11px Inter;color:var(--chrome-text)}
.freshness{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:10.5px;color:var(--chrome-muted)}
.freshness b{color:#C7D2E2;font-weight:500}
.tabbar{display:flex;gap:4px;margin-top:12px;border-bottom:1px solid var(--chrome-line);flex-wrap:wrap}
.tab{background:transparent;border:none;color:#9FB0C6;padding:10px 16px;font:500 12.5px Inter;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab:hover{color:#E6EAF2}.tab.on{color:#fff;border-bottom-color:#fff}
/* briefing */
.briefing{background:var(--navy);color:#EAF0F8;padding:24px 32px;border-bottom:1px solid #1A2438}
.briefing-inner{max-width:1220px;margin:0 auto}
.briefing-label{font-size:10.5px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:#8FA3C0;margin-bottom:12px}
.briefing-lead{font-size:16px;line-height:1.5;color:#F5F8FC;font-weight:400;margin:0 0 14px;max-width:880px}
.briefing-list{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.briefing-list li{font-size:13px;color:#C9D6E8;padding-left:14px;position:relative}
.briefing-list li::before{content:"·";position:absolute;left:4px;color:#5F7085;font-weight:700;font-size:18px;line-height:1}
/* main */
.main{padding:26px 32px 44px}
.scope-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:28px}
.ccard{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 18px;cursor:pointer;transition:border-color .12s}
.ccard:hover{border-color:var(--border-strong)}
.ccard.sel{border-color:var(--tp);box-shadow:0 0 0 1px var(--tp)}
.cc-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:2px}
.cc-name{font-size:13.5px;font-weight:600}
.cc-auth{font-size:10px;color:var(--tm);letter-spacing:.05em;text-transform:uppercase}
.cc-sub{font-size:11px;color:var(--tm);margin-bottom:10px}
.cc-adh{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
.cc-adh b{font-size:23px;font-weight:600;letter-spacing:-.01em}
.cc-adh span{font-size:11px;color:var(--tm)}
.splitbar{display:flex;height:8px;border-radius:4px;overflow:hidden;border:1px solid var(--border);margin-bottom:8px}
.splitbar i{display:block}
.cc-foot{display:flex;justify-content:space-between;font-size:11.5px;color:var(--ts);border-top:1px solid var(--border);padding-top:9px}
.cc-foot b{color:var(--tp);font-weight:600}
.cc-risk{color:var(--red);font-weight:600}
/* sections */
.section{margin-bottom:36px}
.section-eyebrow{display:flex;align-items:center;gap:8px;font-size:10.5px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--tm);margin-bottom:10px}
.section-mark{width:8px;height:8px;border-radius:2px;display:inline-block}
.section-mark.govern{background:var(--govern)}.section-mark.risk{background:var(--risk)}.section-mark.compliance{background:var(--compliance)}
.section-headline{font-size:19px;font-weight:500;line-height:1.4;margin:0 0 8px;max-width:880px;letter-spacing:-.005em}
.section-sub{font-size:13px;color:var(--ts);margin:0 0 18px;max-width:820px}
.grid{display:grid;gap:16px}
.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
.span2{grid-column:span 2}
@media(max-width:900px){.g3,.g4,.g2,.scope-row{grid-template-columns:1fr}.span2{grid-column:span 1}}
.mcard{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:10px;transition:border-color .12s}
.mcard:hover{border-color:var(--border-strong)}
.mcard-label{font-size:10.5px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--tm)}
.mcard-value{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.25}
.mcard-value small{font-size:12px;font-weight:500;color:var(--tm)}
.mcard-note{font-size:12px;color:var(--ts);margin-top:auto;line-height:1.5}
.mcard.gap{border-style:dashed;border-color:var(--border-strong);background:transparent}
.mcard.gap .mcard-value{font-size:14.5px;font-weight:400;font-style:italic;color:var(--tm)}
.gap-tag{display:inline-block;font-size:9.5px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--tm);background:#EDF0F4;padding:2px 8px;border-radius:10px;align-self:flex-start}
.chart-title-row{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:2px}
.chart-title{font-size:14px;font-weight:600;margin:0}
.chart-sub{font-size:11.5px;color:var(--tm);margin:0}
.chart-headline{font-size:13px;font-weight:500;margin:6px 0 12px;line-height:1.4;color:var(--tp)}
/* funnel */
.funnel{display:grid;gap:8px;margin-top:6px}
.funnel-item{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}
.funnel-lab{font-size:11px;color:var(--tm);font-weight:500;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px}
.funnel-bar{background:var(--surface);border-radius:4px;overflow:hidden;height:26px;position:relative}
.funnel-fill{height:100%;background:var(--navy);opacity:.9;display:flex;align-items:center;padding-left:10px;color:#fff;font:600 11.5px Inter}
.funnel-side{font-size:11px;color:var(--ts);font-variant-numeric:tabular-nums;text-align:right;min-width:120px}
.funnel-side b{color:var(--red)}
/* findings list */
.flist{display:grid;gap:1px;margin-top:6px}
.frow{display:grid;grid-template-columns:auto 1fr auto auto;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--surface)}
.frow:last-child{border-bottom:none}
.sev{font-size:9.5px;font-weight:600;padding:2px 7px;border-radius:10px;white-space:nowrap}
.sev.L3{background:#F9E4E5;color:var(--red)}.sev.L2{background:#FBF0DA;color:#9A6503}.sev.L1{background:#E3F4EC;color:var(--green)}
.fname{font-size:12.5px;color:var(--tp)}
.fparent{font-size:10.5px;color:var(--tm)}
.fcount{font-size:12px;color:var(--ts);text-align:right;font-variant-numeric:tabular-nums}
.frisk{font-size:12.5px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums;min-width:120px}
.team{display:inline-block;font-size:9.5px;font-weight:500;color:var(--ts);background:var(--hover);padding:1px 6px;border-radius:8px;margin-left:6px}
/* bars */
.bars{display:grid;gap:9px;margin-top:8px}
.bar-item{display:grid;grid-template-columns:120px 1fr auto;gap:12px;align-items:center;font-size:12px}
.bar-lab{color:var(--tp);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-wrap{display:block;height:11px;background:var(--surface);border-radius:6px;overflow:hidden}
.bar-fill{display:block;height:100%;border-radius:6px}
.bar-val{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;min-width:110px}
/* table */
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;font-weight:500;color:var(--tm);font-size:10px;text-transform:uppercase;letter-spacing:.05em;padding:8px 10px;border-bottom:1px solid var(--border)}
td{padding:10px;border-bottom:1px solid var(--surface)}
tr:last-child td{border-bottom:none}
.legend{margin-top:14px;padding-top:16px;border-top:1px solid var(--border);font-size:11.5px;color:var(--tm);display:flex;gap:22px;flex-wrap:wrap}
.legend-item{display:flex;align-items:center;gap:7px}
.legend-sw{width:9px;height:9px;border-radius:2px}
.legend-dash{width:16px;height:10px;border:1px dashed var(--tm);border-radius:2px}
.foot{padding:18px 32px;color:var(--tm);font-size:11px;border-top:1px solid var(--border)}
.pill-row{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px}
.mini{font-size:10px;font-weight:500;padding:2px 7px;border-radius:6px;background:var(--hover);color:var(--ts)}
</style></head>
<body><div id="app">
  <div id="chrome"></div>
  <div id="briefing"></div>
  <div class="main" id="main"></div>
  <div class="foot">Figures derived from the GCC recon output (UAE, KSA, Oman workbooks). Every amount is shown in its own currency and never summed across currencies. Plain-English findings, Level 3 / 2 / 1 severity. Prepared to inform the VAT return draft, never to file it.</div>
</div>
<script>
const DATA = /*__DATA__*/;
const C = {};
DATA.countries.forEach(c=>C[c.code]=c);
const CCOL={UAE:'var(--cat-1)',KSA:'var(--cat-2)',OMN:'var(--cat-3)'};
const S={scope:'portfolio',tab:'posture',persona:'exec'};

const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const esc=s=>String(s==null?'':s);
function money(v,ccy,dec){if(v==null)return 'n/a';return ccy+' '+Number(v).toLocaleString(undefined,{minimumFractionDigits:dec,maximumFractionDigits:dec});}
function mny(c,v){return money(v,c.currency,c.decimals);}
function sevClass(s){return s==='Level 3'?'L3':s==='Level 2'?'L2':'L1';}
function sevShort(s){return s==='Level 3'?'L3 · Non-compliant':s==='Level 2'?'L2 · Needs review':'L1 · Info';}
function findByLabel(list,lbl){return list.find(f=>f.label===lbl)||{count:0,risk:0};}
function scopeCountries(){return S.scope==='portfolio'?DATA.countries:[C[S.scope]];}

/* ---------- chrome ---------- */
function renderChrome(){
  const tabs=[['posture','Compliance posture'],['exceptions','Exceptions and aging'],['recon','Reconciliation']];
  const fresh=DATA.meta.generated_utc?DATA.meta.generated_utc.replace('T',' ').slice(0,16):'n/a';
  document.getElementById('chrome').innerHTML=`
    <div class="chrome">
      <div class="chrome-row">
        <div class="brand">eInvoicing Command Center<small>GCC · UAE · KSA · Oman</small></div>
        <div class="chrome-controls">
          <input class="csearch" placeholder="Search invoice, ERP ref, TRN" oninput="void 0">
          <select class="viewas" onchange="setPersona(this.value)">
            <option value="exec" ${S.persona==='exec'?'selected':''}>View as: Executive</option>
            <option value="tax" ${S.persona==='tax'?'selected':''}>View as: Tax and Compliance</option>
          </select>
          <span class="cpill">${S.scope==='portfolio'?'All countries':S.scope}</span>
        </div>
      </div>
      <div class="freshness">
        <span>E-invoice data as of <b>${fresh} UTC</b></span>
        <span>Integration feeds <b>GL Stream, SFTP fallback</b></span>
        <span>Last recon run <b>${esc(DATA.meta.run_id)}</b></span>
        <span>Reporting <b>per country, native currency</b></span>
      </div>
      <div class="tabbar">
        ${tabs.map(([id,l])=>`<button class="tab ${S.tab===id?'on':''}" onclick="setTab('${id}')">${l}</button>`).join('')}
      </div>
    </div>`;
}

/* ---------- briefing (navy, persona-aware) ---------- */
function worst(c){ // highest-risk AR finding that is an exception
  return c.ar.findings.filter(f=>f.parent!=='Matched'&&f.parent!=='Out of scope').sort((a,b)=>b.risk-a.risk)[0];
}
function renderBriefing(){
  const b=document.getElementById('briefing');
  if(S.tab!=='posture'){b.innerHTML='';return;}
  const cs=scopeCountries();
  let label,lead,items;
  if(S.persona==='exec'){
    label='Executive brief · GCC eInvoicing · '+(S.scope==='portfolio'?'all countries':C[S.scope].name);
    const riskLine=cs.map(c=>mny(c,c.ar.vat_at_risk)).join(' · ');
    lead='On-time adherence sits at '+cs[0].ar.adherence_pct+'% across the live GCC estate. VAT at risk on the sales side is '+riskLine+', held in its own currency and never blended. Penalty exposure is priced where the schedule is public.';
    items=cs.map(c=>{const w=worst(c);return c.name+': '+mny(c,c.ar.vat_at_risk)+' at risk, largest cause '+w.label.toLowerCase()+' at '+mny(c,w.risk)+'.';});
  }else{
    label='Tax and Compliance brief · GCC eInvoicing · '+(S.scope==='portfolio'?'all countries':C[S.scope].name);
    lead='Clearance and reporting is landing for '+cs[0].ar.cleared+' of '+cs[0].ar.applicable+' applicable invoices per country, with '+cs[0].ar.delayed+' reported late and '+cs[0].ar.missed+' never reaching the authority. Reconciliation to the GL surfaces Level 3 findings first, ranked by VAT at risk, each routed to an owning team.';
    items=cs.map(c=>c.name+' ('+c.authority+'): '+c.ar.missed+' not reported, '+(c.ar.gen_failed+c.ar.ing_failed)+' failed in pipeline, '+c.ar.delayed+' late. On-time rule: '+c.on_time_rule+'.');
  }
  b.innerHTML=`<div class="briefing"><div class="briefing-inner">
    <div class="briefing-label">${esc(label)}</div>
    <p class="briefing-lead">${esc(lead)}</p>
    <ul class="briefing-list">${items.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>
  </div></div>`;
}

/* ---------- scope row (country cards) ---------- */
function splitBar(c){
  const a=c.ar,tot=Math.max(1,a.on_time+a.delayed+a.missed+a.gen_failed+a.ing_failed);
  const seg=(n,col)=>n>0?`<i style="width:${100*n/tot}%;background:${col}"></i>`:'';
  return `<div class="splitbar">${seg(a.on_time,'var(--green)')}${seg(a.delayed,'var(--amber)')}${seg(a.missed,'var(--red)')}${seg(a.gen_failed+a.ing_failed,'#9A2E33')}</div>`;
}
function renderScopeRow(){
  return `<div class="scope-row">${DATA.countries.map(c=>`
    <div class="ccard ${S.scope===c.code?'sel':''}" onclick="setScope('${S.scope===c.code?'portfolio':c.code}')">
      <div class="cc-head"><div class="cc-name">${esc(c.name)}</div><div class="cc-auth">${esc(c.authority)}</div></div>
      <div class="cc-sub">${esc(c.status)} · VAT ${(c.vat_rate*100).toFixed(0)}% · ${esc(c.currency)} · ${c.live_entities} entities</div>
      <div class="cc-adh"><b class="num">${c.ar.adherence_pct}%</b><span>on-time adherence</span></div>
      ${splitBar(c)}
      <div class="pill-row" style="margin-bottom:9px">
        <span class="mini">On-time ${c.ar.on_time}</span><span class="mini">Late ${c.ar.delayed}</span>
        <span class="mini">Missed ${c.ar.missed}</span><span class="mini">Failed ${c.ar.gen_failed+c.ar.ing_failed}</span>
      </div>
      <div class="cc-foot"><span>VAT at risk (sales)</span><span class="cc-risk num">${mny(c,c.ar.vat_at_risk)}</span></div>
    </div>`).join('')}</div>`;
}

/* ---------- tiles ---------- */
function tile(label,value,note,cls){return `<div class="mcard"><div class="mcard-label">${esc(label)}</div><div class="mcard-value num ${cls||''}">${value}</div><div class="mcard-note">${note||''}</div></div>`;}
function gapCard(label,note){return `<div class="mcard gap"><div class="mcard-label">${esc(label)}</div><span class="gap-tag">Not tracked yet</span><div class="mcard-note">${esc(note)}</div></div>`;}

/* AR headline tiles for one country */
function arHeadlineTiles(c){
  const a=c.ar;
  const failRisk=findByLabel(a.findings,'Ingestion failed (landing failed)').risk+findByLabel(a.findings,'E-invoice generation failed').risk;
  const missRisk=findByLabel(a.findings,'Invoice not reported to authority').risk;
  return `<div class="grid g4">
    ${tile('E-invoice applicable',a.applicable+' <small>of '+a.gl_docs+' GL docs</small>','In-scope taxable supplies requiring an e-invoice. Out of scope: '+a.out_of_scope+'.')}
    ${tile('E-invoice generated',a.generated+'','On-time '+a.on_time+', delayed '+a.delayed+'. Generated tax '+mny(c,a.generated_tax)+'.')}
    ${tile('Generation and ingestion failed',(a.gen_failed+a.ing_failed)+'','Generation failed '+a.gen_failed+', ingestion failed '+a.ing_failed+'. VAT at risk '+mny(c,failRisk)+'.','')}
    ${tile('Missed, not reported',a.missed+'','Applicable but never reached the authority. VAT at risk '+mny(c,missRisk)+'.')}
  </div>`;
}

/* AR funnel for one country */
function arFunnel(c){
  const a=c.ar;
  const stages=[
    {lab:'Applicable',n:a.applicable,side:''},
    {lab:'Generated',n:a.generated,side:'gen failed '+a.gen_failed+', ingest failed '+a.ing_failed},
    {lab:'Cleared / reported',n:a.cleared,side:'not reported '+a.missed},
    {lab:'On-time',n:a.on_time,side:'delayed '+a.delayed},
  ];
  const max=Math.max(...stages.map(s=>s.n),1);
  return `<div class="funnel">${stages.map(s=>`
    <div><div class="funnel-lab">${s.lab}</div>
    <div class="funnel-item">
      <div class="funnel-bar"><div class="funnel-fill" style="width:${Math.max(8,100*s.n/max)}%">${s.n}</div></div>
      <div class="funnel-side">${s.side?('<b>'+esc(s.side)+'</b>'):''}</div>
    </div></div>`).join('')}</div>`;
}

/* findings list (recon outcomes / exceptions), capped with rollup */
function findingsList(c,findings,riskLabel,cap){
  cap=cap||findings.length;
  const shown=findings.slice(0,cap), rest=findings.slice(cap);
  let html=`<div class="flist">`;
  html+=shown.map(f=>`
    <div class="frow">
      <span class="sev ${sevClass(f.severity)}">${f.severity.replace('Level ','L')}</span>
      <div><div class="fname">${esc(f.label)}</div><div class="fparent">${esc(f.parent)}</div></div>
      <div class="fcount">${f.count} doc${f.count===1?'':'s'}</div>
      <div class="frisk">${f.risk>0?mny(c,f.risk):'<span style="color:var(--tm)">nil</span>'}</div>
    </div>`).join('');
  if(rest.length){const rc=rest.reduce((s,f)=>s+f.count,0),rr=rest.reduce((s,f)=>s+f.risk,0);
    html+=`<div class="frow"><span class="sev L1">·</span><div><div class="fname">Other findings (${rest.length})</div><div class="fparent">rolled up</div></div><div class="fcount">${rc} docs</div><div class="frisk">${rr>0?mny(c,rr):'nil'}</div></div>`;}
  html+=`</div>`;
  return html;
}

/* horizontal bars for a by-X breakdown */
function barList(c,items,color){
  const max=Math.max(...items.map(i=>i.value),1);
  return `<div class="bars">${items.map(i=>`
    <div class="bar-item">
      <span class="bar-lab" title="${esc(i.name)}">${esc(i.name)}</span>
      <span class="bar-wrap"><span class="bar-fill" style="width:${Math.max(3,100*i.value/max)}%;background:${color}"></span></span>
      <span class="bar-val num">${mny(c,i.value)}</span>
    </div>`).join('')}</div>`;
}

function sectionHead(mark,eyebrow,headline,sub){
  return `<div class="section-eyebrow"><span class="section-mark ${mark}"></span>${esc(eyebrow)}</div>
    <h2 class="section-headline">${esc(headline)}</h2>${sub?`<p class="section-sub">${esc(sub)}</p>`:''}`;
}
function legend(){return `<div class="legend">
  <div class="legend-item"><span class="sev L3" style="padding:1px 6px">L3</span>Non-compliant</div>
  <div class="legend-item"><span class="sev L2" style="padding:1px 6px">L2</span>Needs review</div>
  <div class="legend-item"><span class="sev L1" style="padding:1px 6px">L1</span>Info</div>
  <div class="legend-item"><span class="legend-dash"></span>Not tracked yet, needs a metric</div>
</div>`;}

/* ---------- TAB: Compliance posture ---------- */
function renderPosture(){
  const cs=scopeCountries();
  const exec=S.persona==='exec';
  let out=`<div class="section">`;
  out+=sectionHead('compliance', exec?'Compliance posture':'Clearance and reporting',
    exec?'On-time adherence holds at '+cs[0].ar.adherence_pct+'%, but VAT at risk is concentrated in a handful of Level 3 findings.'
        :'Most applicable invoices clear or report, yet a real tail is missed, late, or failing in the pipeline.',
    'The four AR headline tiles per country: what was applicable, what generated, what failed in the pipeline, and what was missed. Each figure carries its own currency.');
  cs.forEach(c=>{
    out+=`<div style="margin-bottom:22px"><div class="chart-title-row"><h3 class="chart-title">${esc(c.name)} · ${esc(c.authority)}</h3><span class="chart-sub">${esc(c.model)} · ${esc(c.on_time_rule)}</span></div>`;
    out+=arHeadlineTiles(c)+`</div>`;
  });
  out+=`</div>`;
  // adherence ranking + funnel of scoped country (or first)
  out+=`<div class="section"><div class="grid g2">
    <div class="mcard span2" style="grid-column:auto"><div class="chart-title-row"><h3 class="chart-title">On-time adherence by country</h3><span class="chart-sub">on-time / (on-time + delayed + missed + failed)</span></div>
      <p class="chart-headline">Adherence is level across the three live jurisdictions this period.</p>
      <div class="bars">${DATA.countries.map(c=>`
        <div class="bar-item"><span class="bar-lab">${c.code}</span>
        <span class="bar-wrap"><span class="bar-fill" style="width:${c.ar.adherence_pct}%;background:${CCOL[c.code]}"></span></span>
        <span class="bar-val num">${c.ar.adherence_pct}%</span></div>`).join('')}</div>
    </div>
    <div class="mcard"><div class="chart-title-row"><h3 class="chart-title">Sales pipeline · ${esc((S.scope==='portfolio'?cs[0]:C[S.scope]).name)}</h3><span class="chart-sub">applicable to on-time</span></div>
      <p class="chart-headline">Where invoices drop out of the flow before they land on time.</p>
      ${arFunnel(S.scope==='portfolio'?cs[0]:C[S.scope])}
    </div>
  </div></div>`;
  // persona lens
  if(exec){
    out+=`<div class="section">${sectionHead('risk','Country health','Exposure and penalty at a glance, per country.','')}
      <div class="grid g3">${cs.map(c=>tile(c.code+' · VAT at risk (sales)',mny(c,c.ar.vat_at_risk),
        'Penalty exposure '+(c.ar.penalty_priced?mny(c,c.ar.penalty_total):'not priced, schedule pending')+'. Adherence '+c.ar.adherence_pct+'%.','cc-risk')).join('')}</div></div>`;
  }else{
    out+=`<div class="section">${sectionHead('compliance','Deadline adherence','The clock each authority runs, and how this period landed against it.','')}
      <div class="grid g3">${cs.map(c=>tile(c.code+' · on-time rule',c.on_time_rule,
        'Reported on time '+c.ar.on_time+', late '+c.ar.delayed+', missed '+c.ar.missed+'.')).join('')}</div></div>`;
  }
  out+=legend();
  return out;
}

/* ---------- TAB: Exceptions and aging ---------- */
function renderExceptions(){
  const cs=scopeCountries();
  let out=`<div class="section">`;
  out+=sectionHead('risk','Exceptions and aging',
    'The failure and gap population, ranked by VAT at risk and routed to an owning team.',
    'Sales and purchase exceptions that need a human. Level 3 first, then value at risk. Matched and out-of-scope lines are excluded.');
  cs.forEach(c=>{
    const arEx=c.ar.findings.filter(f=>f.parent!=='Matched'&&f.parent!=='Out of scope');
    const apEx=c.ap.findings.filter(f=>f.parent!=='Matched'&&f.parent!=='Out of scope');
    out+=`<div class="grid g2" style="margin-bottom:16px">
      <div class="mcard"><div class="chart-title-row"><h3 class="chart-title">${esc(c.name)} · sales exceptions</h3><span class="chart-sub">${arEx.length} findings</span></div>
        <p class="chart-headline">Largest sales exposure: ${esc(worst(c).label.toLowerCase())} at ${mny(c,worst(c).risk)}.</p>
        ${findingsList(c,arEx,'vat',4)}
        <div class="mcard-note">Routing: ${c.ar.var_by_team.map(t=>esc(t.name)+' '+mny(c,t.value)).join(', ')}.</div>
      </div>
      <div class="mcard"><div class="chart-title-row"><h3 class="chart-title">${esc(c.name)} · purchase exceptions</h3><span class="chart-sub">feed: ${esc(c.ap.data_source)}${c.code==='KSA'?' (no ZATCA buyer feed)':''}</span></div>
        <p class="chart-headline">Input VAT at risk ${mny(c,c.ap.input_vat_at_risk)}. ${c.code==='KSA'?'KSA vendor e-invoices are client-provided, so absence is not proof of vendor default.':'Vendor e-invoices received through the accredited service provider.'}</p>
        ${findingsList(c,apEx,'input',4)}
      </div>
    </div>`;
  });
  out+=`</div>`;
  out+=`<div class="section"><div class="grid g2">
    ${gapCard('Invoice-level aging','This recon output carries severity and value at risk per finding, but not per-invoice age buckets (0-1d, 1-5d, 5-30d). Aging needs the issuance and clearance timestamps joined through to each open exception.')}
    ${gapCard('Root cause of authority rejections','No authority rejections landed in this period across the three countries. When they do, the reject reason (buyer TRN, wrong invoice type, missing VAT category, timing) is needed to fix patterns at source.')}
  </div></div>`;
  out+=legend();
  return out;
}

/* ---------- TAB: Reconciliation ---------- */
function penaltyCard(c){
  if(c.ar.penalty_priced){
    return `<div class="mcard"><div class="chart-title-row"><h3 class="chart-title">${esc(c.code)} penalty exposure</h3><span class="chart-sub">instances x statutory rate</span></div>
      <table><thead><tr><th>Violation class</th><th style="text-align:right">Instances</th><th style="text-align:right">Rate</th><th style="text-align:right">Exposure</th></tr></thead>
      <tbody>${c.ar.penalty_rows.map(p=>`<tr><td>${esc(p.cls)}</td><td class="num" style="text-align:right">${p.instances}</td><td class="num" style="text-align:right">${p.rate!=null?mny(c,p.rate):'n/a'}</td><td class="num" style="text-align:right">${p.exposure!=null?mny(c,p.exposure):'n/a'}</td></tr>`).join('')}
      <tr><td style="font-weight:600">Total</td><td></td><td></td><td class="num" style="text-align:right;font-weight:600">${mny(c,c.ar.penalty_total)}</td></tr></tbody></table></div>`;
  }
  const inst=c.ar.penalty_rows.reduce((s,p)=>s+p.instances,0);
  return `<div class="mcard gap"><div class="mcard-label">${esc(c.code)} penalty exposure</div><span class="gap-tag">Rate not tracked yet</span>
    <div class="mcard-note">${inst} penalty-class instances this period (${c.ar.penalty_rows.map(p=>esc(p.cls)+' '+p.instances).join(', ')}). The ${esc(c.authority)} penalty schedule is not parameterised in this dataset, so exposure is not priced. Instances are real; the rate is not invented.</div></div>`;
}
function renderRecon(){
  const cs=scopeCountries();
  let out=`<div class="section">`;
  out+=sectionHead('compliance','Reconciliation',
    'GL to e-invoice tie-out for sales and purchase, ranked by value at risk.',
    'The universal outcomes, in plain English. Sales carries the ten AR outcomes; purchase carries the match and gap set, with the data source labelled honestly per country.');
  cs.forEach(c=>{
    out+=`<div class="grid g2" style="margin-bottom:16px">
      <div class="mcard"><div class="chart-title-row"><h3 class="chart-title">${esc(c.name)} · sales tie-out</h3><span class="chart-sub">${c.ar.findings.length} outcomes</span></div>
        <p class="chart-headline">Matched ${findByLabel(c.ar.findings,'Matched').count}, VAT at risk ${mny(c,c.ar.vat_at_risk)} across the exceptions.</p>
        ${findingsList(c,c.ar.findings,'vat',6)}
      </div>
      <div class="mcard"><div class="chart-title-row"><h3 class="chart-title">${esc(c.name)} · purchase tie-out</h3><span class="chart-sub">${esc(c.ap.data_source)} feed</span></div>
        <p class="chart-headline">Recoverable input VAT ${mny(c,c.ap.eligibility['Recoverable'].tax)}, input VAT at risk ${mny(c,c.ap.input_vat_at_risk)}.</p>
        ${findingsList(c,c.ap.findings,'input',6)}
      </div>
    </div>`;
  });
  out+=`</div>`;
  // VAT at risk by cause / system / entity for scoped country (or first)
  const c=S.scope==='portfolio'?cs[0]:C[S.scope];
  const causeItems=c.ar.findings.filter(f=>f.risk>0).map(f=>({name:f.label,value:f.risk}));
  out+=`<div class="section">${sectionHead('risk','VAT at risk, three ways · '+c.name,'The same sales exposure of '+mny(c,c.ar.vat_at_risk)+' reconciles by cause, by system, and by entity.','These three views sum to the same total within '+c.currency+'.')}
    <div class="grid g3">
      <div class="mcard"><h3 class="chart-title">By cause</h3>${barList(c,causeItems.slice(0,6),'var(--red)')}</div>
      <div class="mcard"><h3 class="chart-title">By source system</h3>${barList(c,c.ar.var_by_system,'var(--cat-3)')}</div>
      <div class="mcard"><h3 class="chart-title">By entity</h3>${barList(c,c.ar.var_by_entity,'var(--cat-1)')}</div>
    </div></div>`;
  // AP top vendors + penalty
  out+=`<div class="section"><div class="grid g2">
    <div class="mcard"><div class="chart-title-row"><h3 class="chart-title">Top vendors by input VAT at risk · ${esc(c.name)}</h3><span class="chart-sub">not reporting or sending incorrect e-invoices</span></div>
      ${barList(c,c.ap.top_vendors,'var(--cat-2)')}</div>
    ${penaltyCard(c)}
  </div></div>`;
  out+=legend();
  return out;
}

/* ---------- render ---------- */
function renderMain(){
  const m=document.getElementById('main');
  let body='';
  if(S.tab==='posture')body=renderPosture();
  else if(S.tab==='exceptions')body=renderExceptions();
  else body=renderRecon();
  m.innerHTML=renderScopeRow()+body;
}
function renderAll(){renderChrome();renderBriefing();renderMain();window.scrollTo(0,0);}
function setTab(t){S.tab=t;renderAll();}
function setScope(s){S.scope=s;renderAll();}
function setPersona(p){S.persona=p;renderAll();}
renderAll();
</script>
</body></html>
"""
