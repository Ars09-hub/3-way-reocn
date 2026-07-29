# Three-way reconciliation engine

Revenue/Tax GL ↔ Customer GL / AR ↔ E-invoice reconciliation at document level,
with best-fit suggested matching. Deterministic, reproducible, evidence-first.
No LLM anywhere in the matching or bucketing path.

The engine answers four questions:

1. **Completeness** — did every taxable event that hit revenue/tax GL get an e-invoice?
2. **Reverse completeness** — is every e-invoice supported by a booked accounting entry?
3. **Integrity** — within each accounting document, does gross reconcile to net + tax + explained residual?
4. **Correspondence** — where document numbers do not join 1:1, which *combinations* of documents across the three planes most plausibly correspond? This is the differentiating capability.

## Quick start

```bash
pip install -r requirements.txt

# generate the synthetic B2B and B2C datasets with ground truth
python evals/gen_data.py

# run the engine
python run.py \
  --country MY --client demo-b2c-retail-sap \
  --gl data/b2c/gl.csv --ar data/b2c/ar.csv --einv data/b2c/einv.csv \
  --period 2026-06 --out out/b2c --explain

# open out/b2c/dashboard.html

# score against ground truth (fails the build if any target is missed)
python evals/run_evals.py
```

## Portfolio control tower (universal recon)

Each `run.py` invocation produces a per-run `dashboard.html` for one
country / client / period. The **control tower** rolls up many such runs into
a single portfolio view — the view a group controller or GCC (Global
Capability Center) tax lead opens first: which engagements are clean, where the
tax value at risk sits, what is waiting on a human decision, and whether any run
is operationally unhealthy.

```bash
# produce a few runs (one engagement each)
python run.py --country MY --client demo-b2b-sap \
  --gl data/b2b/gl.csv --ar data/b2b/ar.csv --einv data/b2b/einv.csv \
  --period 2026-06 --out out/b2b
python run.py --country SA --client demo-b2b-sap \
  --gl data/b2b/gl.csv --ar data/b2b/ar.csv --einv data/b2b/einv.csv \
  --period 2026-06 --out out/sa-b2b

# roll every completed run under out/ into one control tower
python command_center.py --scan out --out out/command_center.html

# or name the run directories explicitly
python command_center.py --runs out/b2b out/sa-b2b out/b2c \
  --out out/command_center.html --title "GCC Q2 estate"

# open out/command_center.html
```

The Command Center reads only the artifacts a run already writes
(`coverage_summary.json`, `run_manifest.json`, `recon_units.csv`), so it stays
decoupled from the engine and can aggregate historical runs after the fact.
Currency and pack metadata are enriched, best-effort, from `config/`. It carries
the engine's guardrail forward: **monetary value is never summed across
currencies** — portfolio money is reported per-currency, and the only
estate-wide scalars are counts and value-weighted percentages. Five pages,
self-contained, no external runtime dependencies:

1. **Command Center** — estate briefing, portfolio KPIs, posture bar, and a
   "needs attention first" list ranked by posture then value at risk.
2. **Estate map** — one sortable row per engagement (assurance, exposure,
   suggestions, exceptions, unexplained residual, quarantine, conservation, pack
   completeness).
3. **Risk register** — every open exception across the estate, tagged with its
   engagement and ranked by severity then value.
4. **Suggestion backlog** — aggregate T3–T5 queue depth by confidence band, with
   ambiguous and heuristic counts and value awaiting decision.
5. **Operations** — conservation, partial-pack warnings, quarantine, engine
   version drift, and run freshness / footprint.

## GCC eInvoicing Command Center

A separate, GCC-only executive surface built to the `gcc-einvoice-command-center`
skill. Scope is exactly **UAE (FTA, AED, 5%), KSA (ZATCA, SAR, 15%) and Oman
(OTA, OMR, 5%)**. This is an eInvoicing command center, not the universal-recon
control tower above, and it does not share that template.

```bash
# reads the three GCC workbooks under gcc-data/ and writes one self-contained file
python build_gcc_command_center.py --out out/gcc/command_center.html
```

Every figure is derived from the real workbooks in `gcc-data/`
(`{UAE,KSA,OMN}_einvoice_recon_dataset.xlsx`, sheets `GL_Sales`, `GL_Purchase`,
`Einvoice_Sales`, `Einvoice_Purchase`, `Recon_Sales`, `Recon_Purchase`) plus
`run_index.json`. The builder prints the country set and one real headline number
per country in native currency before it renders anything, and a checker pass
re-derives every headline (VAT at risk, adherence, by-system and by-cause splits)
straight from the rows.

House rules, enforced on every build: GCC only (no France, Malaysia, India, EUR
or MYR); amounts are never summed across currencies; plain-English finding labels
only (internal codes such as `MM-VAL` stay in the rulebook); Level 3 / 2 / 1
severity; no em dashes; single self-contained HTML. It carries both metric
families, tied together:

- **Pipeline (AR and AP):** applicable, generated, generation failed, ingestion
  (landing) failed, cleared / reported, on-time vs delayed, missed / not reported.
- **Reconciliation (AR and AP):** matched, tax / taxable value mismatch, rate /
  category mismatch, customer TIN mismatch, metadata mismatch, status conflict,
  missing in e-invoice, missing in GL, out of scope. KSA AP is labelled
  **client-provided** (no ZATCA buyer feed).

Two-dimensional navigation: three country cards (scope switcher) plus three
perspective tabs (Compliance posture, Exceptions and aging, Reconciliation), with
an **Executive** and a **Tax and Compliance** persona view. Penalty exposure is
priced where the schedule is public (UAE) and shown as a "not tracked yet" gap
card where it is not (KSA, Oman). Code lives in `gcc_command_center/`
(`compute.py` derives the figures, `build.py` renders the HTML).

## How it works

The pipeline is a strict sequence of deterministic stages (see `core/pipeline.py`):

1. **Ingest / normalise / quarantine** (`core/ingest.py`, `core/normalize.py`,
   `core/classify.py`). Raw ERP extracts become one canonical document shape.
   Ingest is the only ERP-aware layer; it is driven entirely by the client
   profile's `field_mapping`. Amounts are stored as integer minor units — all
   arithmetic and all matching run on integers, never floats. Rows that fail
   normalisation (including proformas and cancelled e-invoices) go to
   `quarantine.csv` with a reason and are counted, never silently dropped.
2. **Leg A integrity** (`core/leg_a_integrity.py`). A pure `GROUP BY` (DuckDB)
   over GL lines per accounting document. Uses the signed accounting identity so
   WHT, rounding, discount and freight are absorbed regardless of sign; a
   non-zero residual is exactly the amount left in unclassified accounts.
3. **Existence matrix** (`core/existence.py`). The 7-cell R/C/E classification.
   The customer axis is conditional on `settlement_type`: cash / card / wallet
   sales never touch the customer control account, so E3 is expected and correct,
   not an anomaly. E6 (receivable movement only) is suppressed, not flagged.
4. **Matching ladder** T0–T6 (`core/matcher/`). Deterministic number and
   composite joins first (T0–T2, auto-accepted), then the combinatorial engine:
   1:1 pairwise (T3), subset-sum 1:N / N:1 (T4, meet-in-the-middle exact or
   heuristic for large blocks), and N:M cluster balancing (T5). Matching runs on
   a vector of three planes `[tax, net, gross]`; tax is the primary key.
5. **Ambiguity detection** (`core/matcher/ambiguity.py`). After the best group is
   found, all alternatives within `alternative_epsilon` are enumerated. Ten
   documents of 500 against an e-invoice of 1000 reports *45 equivalent
   combinations*, never picks one. Ambiguous units are never auto-accepted.
6. **Global assignment** (`core/matcher/assignment.py`). Locally-computed links
   conflict; a stable, explicitly-tiebroken greedy pass resolves them so every
   document lands in at most one accepted unit. A conservation check asserts that
   total value per plane is preserved.
7. **Unit assembly** (`core/units.py`). Connected components across planes become
   `ReconUnit` records carrying existence cell, plane diagnosis, integrity,
   confidence, ambiguity, evidence and the rules that produced them.

## Configuration (three axes)

- **Engine config** `config/engine.default.json` — tolerances, weights, caps, seed.
- **Country pack** `config/country-packs/{ISO2}.pack.json` — jurisdiction rules
  (MY, SA, AE, FR). Unknowns are marked `TODO` with `completeness: partial` so the
  engine warns rather than assumes.
- **Client profile** `config/client-profiles/{name}.profile.json` — ERP shape, GL
  account ranges, document-type vocabulary, consolidation grain, field mapping.

A Malaysian client on SAP and a Malaysian client on D365 share a country pack and
share nothing else.

## Outputs (`--out`)

`recon_units.parquet/.csv`, `suggestions.csv`, `exceptions_by_bucket.csv`,
`unmatched_{gl,ar,einv}.csv`, `coverage_summary.json`,
`suggested_account_class_additions.csv` (the E5 self-correction loop),
`doc_number_linkage_report.csv`, `quarantine.csv`, `run_manifest.json` (hashes of
every config and input file for reproducibility), and `dashboard.html`
(self-contained, five pages, no external runtime dependencies).

## Guardrails

No LLM in the matching or bucketing path. Never auto-accept an ambiguous match.
Never net credit notes against invoices in subset-sum. Never sum across currencies
or registrations without a flag. Never silently drop a row. Suppress, don't flag,
E6. Warn on partial country packs. See `core/` — no hardcoded client, country or
dataset references live there.

## Open decisions

Printed at the end of every run and shown on the dashboard's data-quality page
(advance/down-payment treatment, accepted-suggestion persistence, suggestion-queue
confidence floor, and `max_group_cardinality` for retail consolidation). These are
surfaced, never resolved silently.
