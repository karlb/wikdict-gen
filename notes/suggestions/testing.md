# Testing

## Resolved (from the 2026-06-12 review)

- `test_parse.TestParseHTML.test_entity` — the underlying `parse()` bug is
  fixed (bugs.md #1), so this passes.
- **Pure unit tests are separated from data tests.** `test_results.py` now
  uses `@unittest.skipUnless(os.path.exists(INFER_DB), ...)`, so the suite is
  runnable on a fresh checkout instead of failing with a confusing
  `OperationalError`.
- The `ResourceWarning: unclosed database` during the test run is gone —
  connections are closed (see code-quality.md, resolved).
- A miniature end-to-end test now exists (`test_e2e.py`, architecture.md #5).
- The `de→sv "gehen" → "åka"` regression no longer reproduces on current data:
  `AggByScore`'s diversity gate crowds `åka` out behind a real competitor. It is
  guarded by `test_results.test_dont_expect` (real data) and the e2e
  `dont_expect` assertion. A diminishing-returns combine that targeted it was
  tried and reverted (architecture.md #4) — it dropped mostly-correct
  translations.

## Resolved (cont.)

- **A known-false-positive list now exists** (scoring-improvement.md). `mine-gold`
  samples inferred-only gap-fills (stratified to enrich for the high-fan-out "hub"
  pattern), an independent multi-lens LLM judge labels them correct/incorrect, and
  the hand-spot-checked result is frozen in `src/tests/data/precision_gold.tsv`
  (697 rows over all six `evaluate` recall pairs plus de-en; 62 confirmed false
  positives). `precision_gold.confirmed_bad()` exposes the 32 high-confidence ones.
  `evaluate` uses the gold for a real precision term, and `test_precision_gold.py`
  covers the metric logic without the big DB.
- **`parse.py` special-cased branches now have edge-case coverage** in
  `test_parse.py`: the `clean_wiki_syntax` unclosed-`{{`-template workaround
  (dbnary #25), and the language gates — `is_dummy_sense` is French-only,
  `make_inflection_cleaner` is the identity for non-German. The `AggByScore`
  diversity gate's exact rising-bar boundary is pinned in `test_infer.py`.

## Open

- **Promote confirmed FPs to `dont_expect` guards once a precision fix removes
  them.** The 32 high-confidence FPs (e.g. `de:Wahrheit→fact`, `de:Hund→bitch`,
  `fr-it:Gand→Guanto`, `fr-de:champ→Weide`, `en-sv:regret→sörja`) currently still
  ship, so they can't yet be passing absent-assertions; they wait on a net-positive
  scoring change (the fan-out penalty was measured net-negative — architecture.md
  #4 — so it isn't it).
