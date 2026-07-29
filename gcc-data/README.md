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

## Running the engine on these datasets

The workbooks are doc-level and the engine consumes line-level `gl.csv` plus
`ar.csv` and `einv.csv`, so a converter reshapes the *sales* side (GL_Sales +
Einvoice_Sales) into that contract. The purchase side is a separate input-tax
reconciliation and is out of scope for this engine's R/C/E output-VAT model.

```bash
# reshape every dataset in run_index.json into data/gcc/<ISO3>/{gl,ar,einv}.csv
python gcc-data/to_engine_csv.py            # or --iso3 OMN for one country

# run the engine (country pack <-> dataset: AE/UAE, SA/KSA, OM/OMN)
python run.py --country OM --client gcc-einvoice \
  --gl data/gcc/OMN/gl.csv --ar data/gcc/OMN/ar.csv --einv data/gcc/OMN/einv.csv \
  --out out/gcc-OMN

# open out/gcc-OMN/dashboard.html
```

The reshaping uses the `gcc-einvoice` client profile
(`config/client-profiles/gcc-einvoice.profile.json`), whose `field_mapping`
matches the column names the converter emits. Multi-line invoices (the same
document number across several tax codes) aggregate to one GL document, so the
GL document count is lower than the raw AR row count by design.

## `run_index.json`

Machine-readable index of the datasets in this folder. For each dataset it
records the country and matching engine country pack, the file path and
`sha256`/`bytes` for provenance, currency and tax rates, the entities and
source systems present, per-sheet column lists, data-row counts, date ranges,
and the `recon_state` distribution. Regenerate it after changing any dataset
so the checksums and counts stay accurate.
