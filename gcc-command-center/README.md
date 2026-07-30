# GCC e-invoice command center

A self-contained command-center view over the GCC e-invoice reconciliation
datasets in [`../gcc-data/`](../gcc-data). It answers one question for a group
tax lead: across the live GCC jurisdictions, where do the books and the
authority feeds disagree, and how much tax is at risk because of it.

Open [`index.html`](index.html) directly in a browser. No server, no build
tooling, no external runtime. Every number on the page is derived from the
source files by the build script and embedded into the page, so the artifact is
reproducible: same inputs, same page.

## What it shows

- **Overview** — a group tax briefing plus one card per live country (UAE, KSA,
  OMN) with match rate, VAT at risk and open exceptions, framed as Govern /
  Risk / Compliance.
- **Compliance** — 30-day on-time issuance trend, auto-match rate, and where
  documents land (matched, mismatch, no e-invoice, no GL, out of scope).
- **Risk** — VAT at risk by country and by owning team, open exceptions, and the
  largest single exposures. Values are shown in each country's filing currency
  and never summed or ranked across currencies.
- **Roadmap** — live coverage and the readiness of the three upcoming
  jurisdictions (Bahrain, Qatar, Kuwait) from the country registry.
- **Country deep dive** — pick a country in the scope selector for a focused
  view: KPIs, trend, recon state, largest exposures and per-entity breakdown.

## Data sources

All read from `../gcc-data/`:

- `UAE_einvoice_recon_dataset.xlsx`, `KSA_...`, `OMN_...` — per-country
  workbooks (GL, e-invoice, recon, worklist and daily adherence sheets).
- `country_registry.json` — the six GCC jurisdictions, live and upcoming, with
  authority, model, VAT rate and readiness.
- `run_index.json` — the 14 reconciliation runs (sales and purchase per entity)
  behind the headline match, VAT-at-risk and exception numbers.

## Rebuilding

```bash
pip install openpyxl
python scripts/build_command_center.py
```

This reads `gcc-data/`, recomputes the model, and regenerates `index.html`
(from `_template.html`) and `dashboard_data.json`. No LLM is involved in the
build; the page is deterministic.

## Notes on the numbers

- Match rate is `matched ÷ documents` from the run index. It is low on this
  first pass by design: the first time books meet the authority feed, most
  documents need a human. It is a worklist, not a verdict.
- On-time issuance (daily adherence) is a separate measure from match rate: did
  the e-invoice reach the authority inside the mandate window.
- Cards marked **Not tracked yet** are deliberate gaps: questions that matter
  but that the current dataset cannot answer (root cause of low match, per
  document deadline clock). Making the gap visible is the point.
