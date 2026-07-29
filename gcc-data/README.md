# GCC e-invoice reconciliation datasets

Source datasets for the three-way reconciliation engine across the GCC
e-invoicing regimes. Each workbook carries the three planes the engine
reconciles — accounting (GL), e-invoice, and the pre-computed recon view —
for both sales and purchase sides.

| Dataset | Country | Country pack | Currency | Tax rate | Entities | Source systems |
|---------|---------|--------------|----------|----------|----------|----------------|
| `UAE_einvoice_recon_dataset.xlsx` | United Arab Emirates | `AE` | AED | 5% | 3 | SAP, Oracle, D365 POS |
| `KSA_einvoice_recon_dataset.xlsx` | Saudi Arabia | `SA` | SAR | 15% | 2 | SAP, Oracle |
| `OMN_einvoice_recon_dataset.xlsx` | Oman | `OM` | OMR | 5% | 2 | SAP |

## Sheets

Each workbook contains six sheets:

- `GL_Sales`, `GL_Purchase` — accounting document lines (revenue/tax and
  expense/input-tax) from the ERP.
- `Einvoice_Sales`, `Einvoice_Purchase` — cleared/reported e-invoices, in the
  jurisdiction's shape (KSA ZATCA clearance fields, UAE Peppol/FTA fields,
  Oman Peppol/OTA fields).
- `Recon_Sales`, `Recon_Purchase` — the reconciliation view keyed by
  `recon_state` / `sub_bucket_code` with per-document deltas and VAT at risk.

## `run_index.json`

Machine-readable index of the datasets in this folder. For each dataset it
records the country and matching engine country pack, the file path and
`sha256`/`bytes` for provenance, currency and tax rates, the entities and
source systems present, per-sheet column lists, data-row counts, date ranges,
and the `recon_state` distribution. Regenerate it after changing any dataset
so the checksums and counts stay accurate.
