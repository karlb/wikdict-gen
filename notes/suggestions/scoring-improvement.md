# Scoring model: settled decisions

The measurement infrastructure this plan called for has shipped, and the
candidate scoring signals have been decided. There is no open scoring task left;
this file is kept as the record of *why* the model is what it is, so the same
ideas aren't re-proposed.

## The crux lesson (do not relitigate)

**Corroboration by many independent pivots is evidence *for* a translation, not
against it.** The `de→sv gehen→åka` failure is not "too many paths"; it is "one
*ambiguous* pivot (English "go" = walk/go/travel) replicated across languages." A
principled fix must separate those two cases, and any change must be measured on
precision — not only recall — before it ships. Two schemes that penalised
corroboration were measured net-negative and reverted:

- **Diminishing-returns decay** (`max + decay·(sum − max)`) — dropped ~71% of
  correct de→en gap-fills.
- **Pivot fan-out penalty** (`evaluate --experiment`) — lifted gold precision
  0.91→0.97 but collapsed retention to 0.33 and recall to 0.11, so combined F0.5
  fell 0.44→0.39.

The plain `sum` combine wins; keep these as cautionary baselines.

## Decided / shipped

- **Precision gold** — `src/precision_gold.py` mines inferred-only gap-fills
  (stratified to enrich for false positives), an independent three-lens LLM judge
  labels them, frozen in `src/tests/data/precision_gold.tsv` (697 rows; 62 FPs,
  `confirmed_bad()` = 32 high-confidence). Mining is reproducible; labels are the
  persisted artifact.
- **Combined objective** — `evaluate` folds held-out recall + gold precision into
  one F0.5 plus a correct-*retention* term. `test_precision_gold.py` covers the
  metric without the big DB.
- **Threshold 20 → 15 (shipped)** — the uniform sample of the [15,20) band is
  ~92% correct, so `IS_GOOD_THRESHOLD` dropped to 15: recall 0.142→0.149, F0.5
  0.438→0.450, probes unchanged. Does not touch TEI (its cutoff keys off
  `TEI_TARGET_GOOD`, not `IS_GOOD_THRESHOLD`).
- **Sense-coherent backlink** — turned out *already implemented*: `infer.sql`
  joins `backlink.back_sense = t2.sense`. Can't fix `gehen → åka` because dbnary
  models English "go" as one coarse sense — a data-granularity ceiling, not a
  missing signal.
- **Wikidata P5137 concept agreement — rejected.** It was considered as both a
  scoring feature and a precision gold; we are not taking on a Wikidata
  dependency, so it will not be integrated. (It was also one-sided and sparse:
  a positive signal where present, but it covers a P5137 sense for only ~26–34%
  of gap-fills and can never *veto* a leak like åka — so even on the merits it
  was not a fix for the flagship case.)

## Risks / open questions

- The LLM judge errs on low-resource pairs and subtle senses → the gold needs
  human spot-checks and isn't free to rerun (needs model access).
- dbnary sense granularity is coarse, capping how far sense-coherence reaches
  without external concepts.
