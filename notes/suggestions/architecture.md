# Architecture & concept suggestions

Bigger-picture ideas, complementing the tactical notes in the other files.
Roughly ordered by expected payoff. #1 and #5 below have shipped.

## 1. Replace Virtuoso with an embedded RDF store — DONE

Done: the whole Virtuoso stack (Docker, isql, bz2→gz, HTTP paging) was replaced
by an embedded [pyoxigraph](https://pyoxigraph.readthedocs.io/) store that
bulk-loads the TTL dumps, one named graph per edition. The old-bug workarounds
and the split `entry_query` are gone; the pipeline now runs end-to-end on a
laptop. See `notes/oxigraph_spike.md` for the spike and the at-scale migration
measurements (named graphs + per-edition scoping were the key to query speed).

## 2. Partition the inference step (the 47 GB bottleneck)

`dictionaries/infer.sqlite3` is currently 47 GB, built single-threaded by
one `executescript`, and is a global artifact: it depends on *all*
processed DBs and *every* generic/wdweb DB depends on it. Touch one
language and the entire inference re-runs, then everything downstream is
stale.

The math in `infer.sql` doesn't need a global table: every result row is
keyed by `(from_lang, to_lang)`, and computing pair (a→b) needs only
a→\*, \*→b and \*→a translations. Partitioning by `from_lang` (26 shards,
`infer-de.sqlite3` etc.) would:

- let Make parallelize inference across cores (`-j`),
- make rebuilds incremental — changing `sv` only rebuilds shards whose
  inputs include `sv`,
- keep individual files at a size where VACUUM/ANALYZE are feasible.

A shared, cheap-to-rebuild `all_trans.sqlite3` (the collect step) can stay
global as the common input. Also worth checking: the `sources` and
`source_details` columns in the `infer` table look like debug output — if
nothing downstream reads them, dropping them should shrink the database
substantially.

## 3. One place for per-language behavior

Language-specific logic is scattered across the pipeline: inflection-table
selections in `process.py` (de/en/sv), the German display/plural logic in
`wdweb.py make_display`, French dummy-sense detection and the German
inflection cleaner in `parse.py`, the FTS tokenizer choice in `wdweb.py`,
the French gloss postprocessing in `sparql/queries.py`, and
`supported_langs` in `helper.py` next to the separate metadata in
`src/languages/`.

Concept: a per-language config object (dataclass or plain dict) in
`src/languages/`, e.g. `LANG_CONFIG["de"] = LangConfig(tokenizer=...,
inflection_table=..., clean_inflection=..., display_query=...)`, with
defaults for everything. The pipeline modules then ask the config instead
of `if lang == "de"`. Two benefits: "what does it take to add/improve a
language?" has one answer, and the generic pipeline code stops accumulating
special cases. This is a mechanical refactor — no behavior change.

## 4. Make the translation-scoring model explicit and measurable — DONE

The scoring constants used to be spread across four files with no way to
evaluate changes. Both halves of the suggestion are now in place:

1. **Centralized.** `src/scoring.py` is the single source of truth for every
   constant (direct/reverse/indirect weights, the `AggByScore` step, the
   `is_good` and TEI thresholds), substituted into `infer.sql` via
   `infer.py:render_sql()` and imported by `generic.py`/`tei.py`.
2. **Measurable.** `src/evaluate.py` (`uv run src/run.py evaluate [--sweep |
   --experiment]`) holds out each pair's direct translations, lets inference
   reproduce them through the other languages as pivots, and reports
   precision/recall/F0.5 at the `is_good` threshold plus the `gehen` probes. It
   reads a built `infer.sqlite3` and needs no rebuild (the held-out indirect
   paths are already in `with_lexentry`).

What the harness then taught us about `gehen → åka`:

- A **diminishing-returns combine** (`max + decay·(sum − max)`) was tried to stop
  polysemous "hub" pivots from summing a wrong translation past the threshold. It
  fixed `åka` and raised precision — but the harness's recall and a differential
  sample showed it **drops mostly-correct translations** (≈71% of inferred-only
  de→en gap-fills, e.g. `schnell→quickly`, `fliehen→run away`). The premise was
  backwards: many corroborating pivots usually means *right*, not suspicious. So
  it was **reverted**; the combine is a plain `sum` again.
- On current data the regression doesn't even reproduce — `AggByScore`'s
  diversity gate already crowds `åka` out behind a real competitor (`sträcka
  sig`). The `dont_expect` probe guards it against future data shifts.

**The precision measure now exists (scoring-improvement.md).** Held-out
reconstruction scores *recall* but counts every gap-fill as a false positive, so
it was blind to precision. `src/precision_gold.py` adds the missing half: a
checked-in gold of inferred-only gap-fills (`src/tests/data/precision_gold.tsv`),
labelled correct/incorrect by an independent multi-lens LLM judge and
hand-spot-checked — independent of the dbnary edges we infer from, so not
circular. `evaluate` now combines held-out recall with gold precision into one
F0.5 objective, plus a correct-*retention* term.

What it then settled: the **fan-out penalty** (`evaluate --experiment`) is
**measured net-negative and does not ship.** It lifts gold precision 0.91→0.97
but drops ~67% of *correct* gap-fills (retention 1.00→0.33) and recall 0.14→0.11,
so combined F0.5 falls 0.44→0.39 — the same mistake as the reverted decay, now
quantified on precision rather than asserted. The plain `sum` combine wins. The
confirmed-bad rows are the known-false-positive list testing.md asked for. Still
open, the more principled gold: Wikidata P5137 concept pivots (wikidata.md),
which would also be a scoring *feature*, not just a judge.

## 5. A miniature end-to-end fixture — DONE

Done: `src/tests/test_e2e.py` loads the hand-built de/en/sv TTL fixtures in
`src/tests/fixtures/` into a temporary pyoxigraph store and runs the whole
pipeline (raw → processed → infer → generic → wdweb), asserting on the outputs.
Runs on a fresh checkout in seconds with no pre-built database. (TEI is not yet
exercised by the fixture.)

## 6. Join importance through real data instead of `written_rep_guess`

`process.py make_importance` reconstructs the written representation from
the vocable URL (`replace(substr(vocable, 5), '_', ' ')`) — flagged in the
code itself as an ugly hack with known case problems. But the actual
mapping already exists in the raw data: `basic_entry_query` extracts
`?vocable` together with `?written_rep` into `raw.entry`. Importance could
be joined to entries via vocable directly (and to translations via
entry→vocable), eliminating the guess and its silent mismatches. This is a
data-flow fix, not a cleanup: every place that joins on
`written_rep_guess` (`spellfix_entry` ranking, `rel_importance` lookups in
`process.py` and `generic.py`) currently loses rows whenever the guess
doesn't match.

## 7. Record provenance in the published artifacts

Releases are date-stamped directories (`release-*` targets), but the
artifacts themselves don't say what they were built from. A tiny
`metadata` table in every generated SQLite (dbnary dump date per language,
wikdict-gen git revision, build date) — and the same in the TEI header —
would make user reports ("dictionary X is missing word Y") diagnosable
against download.wikdict.com without guessing which dump produced the
file. Cheap to add in `make_targets`, where every output DB already passes
through one function.
