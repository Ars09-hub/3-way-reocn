# Three-way sales reconciliation (KSA / ZATCA)

Reconciles a revenue and tax GL against a customer GL (AR) against a ZATCA
e-invoice register, for a KSA entity on Oracle Fusion. Single self-contained
HTML dashboard plus CSV outputs. No database, no build step, deterministic.

## Run

```bash
pip install -r requirements.txt
python run.py \
  --gl   data/gl_register.xlsx \
  --ar   data/sales_register.xlsx \
  --einv data/sales_einvoice__1_.xlsx \
  --out  out/
```

Optional `--period-from` / `--period-to` override the auto-detected window.
Open `out/recon.html` in a browser.

## What it does

1. **Ingest and normalise** the three extracts: clean VAT numbers and string
   arrays, map currencies, convert every amount to integer halalas, dedupe
   e-invoice resubmissions, flag test data.
2. **Scope**: detect the common reconciled window (intersection of the three
   date ranges) and route excluded accounts (interest, forex, intercompany,
   deferred) to an out-of-scope bucket.
3. **Leg 1** (GL vs AR): join on company code, fiscal year, voucher number and
   voucher date, one record per voucher. Five categories.
4. **Leg 2** (e-invoice vs AR): matching ladder (document number, customer VAT
   plus amount, combination search), status ahead of matching.
5. **Three-way** view, **customer** view and **data quality** page, all derived.

## Layout

```
config/   account_scope.json, engine.json, ksa.json
core/     ingest, normalize, scope, sets, leg1, leg2, combination,
          threeway, customer_view, quality, outputs, pipeline
report/   build_html.py  (renders the UI shell with computed values)
tests/    test_acceptance.py  (spec section 7)
data/     the three supplied xlsx files
out/      recon.html and the CSV outputs
```

## Traps handled (spec section 1)

- Document-level tax columns repeat on every voucher line: reduced to one record
  before any aggregation.
- Two sign conventions: GL magnitudes take direction from debit/credit, AR
  document-level amounts are already signed.
- Voucher numbers are not unique: grain key includes voucher date.
- The GL register prefixes credit-note voucher numbers with `CM-`; normalised so
  the grain joins across both registers.
- Presence of an e-invoice row is not compliance: FAILED and NOT_SUBMITTED are
  treated as not reported.
- The three files do not cover the same period: everything outside the reconciled
  window is excluded from exposure and listed separately.

## Known spec deviations (reported, not silently resolved)

- **Excluded-account counts.** Spec section 2.3 / acceptance test 5 state 226 GL
  and 106 AR rows. The supplied files give **276 GL and 143 AR** rows across the
  ten configured excluded codes (every code verified individually). Test 5 asserts
  the real counts; the spec prose does not match the supplied data.
- **Period basis.** The reconciled window follows the accounting date
  (`voucher_date`) by default, an open decision in spec section 9. On a document
  date basis no e-invoice falls out of period, which defeats section 1.6.

See `tests/test_acceptance.py` for the section 7 acceptance suite.
