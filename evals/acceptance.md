# Acceptance criteria

`python evals/run_evals.py` scores the engine against `ground_truth.csv` for the
B2B and B2C datasets and **fails the build (non-zero exit) if any target is
missed**. It prints a confusion matrix by existence cell and a precision/recall
table by tier.

| Metric | Target | Notes |
|---|---|---|
| T0–T2 precision | 1.000 | Deterministic tiers must never be wrong |
| T3–T5 precision @ High confidence | ≥ 0.95 | |
| T3–T5 recall @ High + Medium | ≥ 0.85 | Excludes ambiguous-by-design scenarios (scored separately) |
| Existence-cell accuracy | ≥ 0.98 | |
| Ambiguity detection recall | 1.000 | Never silently pick from a degenerate set |
| False-positive rate on E6 (cash traffic) | 0.00 | Suppressed, never flagged |
| Conservation check | must pass | Value preserved per plane; each doc in ≤ 1 unit |
| Determinism | identical | Two runs → identical `recon_units` hash |

## Mandatory scenarios

Every scenario in spec §19 is present and labelled in `ground_truth.csv`, in both
the B2B and B2C datasets where applicable:

- **Cardinality**: clean 1:1:1 (T0), cross-family 1:1:1 (T1), the 1:1:2 worked
  example (e-invoice 1000 / AR 1000 with no number match / two GL vouchers of
  500), 1:N split billing, N:1 consolidated (twelve e-invoices → one daily GL
  posting), N:M balanced cluster, and the degenerate 45-alternative set.
- **Existence cells**: E2 (portal rejection and cancelled e-invoice), E3 (cash
  sale), E4 (accrual), E5 (asset disposal and notice-pay to unmapped accounts),
  E6 (receipt/clearing, suppressed), E7 (reported unbooked).
- **Integrity / planes**: WHT, TCS, rounding line, multi-line revenue, wrong tax
  code, inverted credit note, cut-off timing, FX difference, broken original-doc
  reference, proforma exclusion, duplicate e-invoice submission.

## Reproducing

```bash
python evals/gen_data.py     # regenerate datasets (deterministic)
python evals/run_evals.py     # score; exit 0 = all targets met
```

The datasets are generated deterministically, so the ground truth and the engine
output are reproducible across machines.
