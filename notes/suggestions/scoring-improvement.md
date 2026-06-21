# Scoring model: problem statement and improvement plan

## Problem

WikDict infers translations by pivoting through other languages (`A → pivot → B`)
and scoring each candidate; the score decides what ships. Two things are now
clear and unresolved.

**1. We can measure recall but not precision.** `src/evaluate.py` hides a pair's
human-curated direct edges and checks how well inference reconstructs them. That
is a sound *recall* signal. But the translations inference exists to produce are
the ones with *no* direct edge — the gap-fills — and for those we have no ground
truth. The harness counts every non-gold prediction as a false positive, which
understates precision and, worse, makes the metric blind to the harm we care
about most: shipping a *wrong* translation. So we cannot currently tell whether a
scoring change trades good gap-fills for bad ones, or the reverse.

**2. The failure mode is real but rare, and easy to "fix" wrongly.** The
`de→sv gehen→åka` case (German "to walk" → Swedish "to travel by vehicle") came
from a *polysemous pivot*: "go" / "aller" / "ir" each translate the walking sense
of "gehen" yet also mean "travel", so they leak to "åka". A diminishing-returns
combine that penalised having many pivot paths did suppress it — and a
differential sample showed it also dropped ~71% of inferred-only de→en gap-fills,
nearly all correct (`schnell→quickly`, `fliehen→run away`, `Erbschaft→inheritance`).

The lesson is the crux of this document: **corroboration by many independent
pivots is evidence *for* a translation, not against it.** The åka failure is not
"too many paths"; it is "one *ambiguous* pivot replicated across languages." A
principled fix must separate those two cases, and any change must be measured on
precision — not only recall — before it ships.

## Goal

Ship more correct translations and fewer wrong ones: a precision/recall tradeoff
on the *actual output*, precision weighted higher (a wrong dictionary entry is
worse than a missing one — the project uses F0.5). Concretely, raise precision on
inferred-only gap-fills without losing recall, measured rather than eyeballed.

## Principles

- **Measure before shipping.** No scoring change lands without an A/B on a
  held-out objective that includes a *precision* term. The harness already has
  the right shape (recompute scores on a built DB, no full rebuild); it is
  missing a precision gold.
- **Target the right signal.** The discriminating feature for the failure mode is
  per-pivot *ambiguity* and *sense-coherence*, not aggregate path count. Reject
  any signal that penalises corroboration.
- **Be honest about the metric.** Held-out reconstruction is a recall proxy with
  a precision blind spot; say so wherever it is used.
- **Stay minimal.** Prefer signals computable from data already in the store /
  `all_trans`. Keep `scoring.py` the single source of truth; gate each candidate
  behind a constant that defaults to current behaviour.

## Task

### 1. Build a precision gold (the missing measurement)
A precision gold must be **independent of the dbnary translation edges we infer
from**. Our own Wiktionary data can't serve: a gap-fill has no direct edge by
definition, and any related Wiktionary signal (reverse edge, backlink,
cross-edition agreement) is either absent for a true gap or already feeds the
inference we are grading — circular. The gold needs an outside judge.

- **(a) LLM-judged + human-spot-checked labels.** Ask a model "is `de:X → en:Y` a
  correct translation?" over a sample of inferred-only pairs (mine candidates from
  `evaluate` differentials and the high-fan-out "hub" pattern). This is
  independent of dbnary, scales to thousands, and needs no new data pipeline.
  Spot-check by hand, because the judge errs on low-resource pairs and subtle
  senses. A few hundred labelled pairs per major pair is enough to A/B a change;
  keep the confirmed-bad ones next to `expect`/`dont_expect` as regression guards.
- **(b) Manual labelling** for the highest-value cases and to validate the judge.

Note: Wikidata P5137 concept agreement is deliberately **not** the gold here. It
is more valuable as a scoring feature (step 3), and a signal used for scoring
cannot also be the gold that judges it (circular).

### 2. Define the objective
Report Fβ (β = 0.5) measured against **both**:
- held-out direct edges → recall (current harness), and
- the precision gold from step 1 → precision on no-direct gap-fills.

A change ships only if it improves the combined objective and keeps the
`expect`/`dont_expect` probes green.

### 3. Evaluate candidate signals
Ordered by how directly each attacks the failure mode. Each is A/B-able once
step 1 exists.

- **Sense-coherent backlink (second-hop validation).** Today `backlink_score`
  validates hop 1 (source ↔ pivot) but not that the *specific pivot sense*
  reaching the target is the one that links back to the source. Making it
  sense-specific is the most direct attack on the åka mechanism, limited only by
  how fine dbnary's senses are.
- **Concept agreement (P5137).** Boost inferred pairs whose words share a Wikidata
  concept, and/or add concept-pivot pairs as a candidate source inside `infer`.
  It is independent of the dbnary edges and concept-disambiguated, so it attacks
  the åka mechanism at the source — separating "go-walk" from "go-travel" where
  string pivots can't — and fills currently-empty pairs (the wikidata.md
  proposal). This is the strongest principled candidate, but the heaviest to
  integrate (load Wikidata, join on Q-items).
- **Pivot fan-out / specificity.** Down-weight a path by how many target words its
  pivot maps to (prototyped behind `evaluate --experiment`). Targets ambiguity,
  not count. A faithful test rebuilds `indirect` with the factor.
- **Round-trip consistency.** Use B→A evidence as a corroboration feature for
  A→B.
- **AggByScore gate.** Its rising-threshold diversity gate already excludes åka on
  current data. Treat it as a first-class lever — characterise and tune it under
  the objective — rather than only touching the per-path combine.

### 4. Methodology
For each candidate: implement behind a `scoring.py` constant (default = current
behaviour), A/B via the harness against the combined objective, and take a
differential sample (what does it add, what does it drop?). Ship only net-positive
changes; add the newly labelled cases as regression guards.

## Implemented (this plan, steps 1–4 for the tractable signals)
- **Precision gold (step 1).** `src/precision_gold.py` mines inferred-only
  gap-fills from the built `infer.sqlite3`, stratified into hub / near / high to
  enrich for likely false positives; an independent three-lens LLM judge (neutral
  / adversarial sense-leak hunter / full-sense-range, majority vote) labels them
  and the hand-spot-checked result is frozen in
  `src/tests/data/precision_gold.tsv` (320 rows over de-en, de-fr, de-sv, fr-it;
  291 correct, 28 incorrect, 1 unsure). Mining is reproducible (`mine-gold`);
  labels are the persisted artifact. `confirmed_bad()` is the known-FP list.
- **Combined objective (step 2).** `evaluate` reports held-out recall *and* gold
  precision and folds them into one F0.5, plus a correct-*retention* term that
  catches the dropping-good-gap-fills failure. `test_precision_gold.py` covers the
  metric logic without the big DB.
- **Signals evaluated (step 3/4).** Production (plain `sum`) micro: recall 0.142,
  gold P 0.912, retain 1.000, **F0.5 0.438**. The **fan-out penalty** lifts gold
  P to 0.97 but collapses retention to 0.33 and recall to 0.11 → **F0.5 0.39**:
  measured net-negative, does not ship (same lesson as the reverted decay, now
  quantified on precision). The åka `dont_expect` probe stays green throughout.

  *Caveat the harness now prints:* the gold is mined at the is_good threshold
  (20), so it cleanly A/Bs score *changes* at a fixed threshold (the fan-out
  experiment) but **not the threshold itself** — the `--sweep` line at thr=15 shows
  a higher F0.5, but that band is unlabelled, so the gain is unmeasured; raising
  the threshold drops gold rows mechanically. To tune the threshold, re-mine the
  gold there. Production threshold 20 is sound; raising it craters recall.

Not done (heaviest, deferred with reason): the **sense-coherent backlink** and
**concept agreement (P5137)** signals both need a rebuild / external data load
(rebuild `indirect`; load Wikidata), out of scope for a no-rebuild harness pass.
They are the principled next candidates now that the precision measure exists.

## Already in place (do not redo)
- `src/scoring.py` — centralized constants.
- `src/evaluate.py` — held-out recall harness plus the fan-out experiment
  scaffold and differential queries.
- `AggByScore` diversity gate; the `dont_expect` seed.
- Plain `sum` combine. The reverted decay is the evidence that corroboration must
  not be penalised — keep it as a cautionary baseline.

## Risks / open questions
- An LLM judge errs on low-resource pairs and subtle senses, so the gold needs
  human spot-checks, and it isn't free to rerun (needs model access).
- Wikidata P5137 coverage is uneven (strong for major pairs, sparse elsewhere),
  which limits how much of the long tail concept agreement can score.
- dbnary sense granularity is coarse ("go" is one sense covering walk and
  travel), which caps how far sense-coherence reaches without external concepts.
