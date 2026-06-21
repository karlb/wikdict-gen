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

## 4. Make the translation-scoring model explicit and measurable

The quality of WikDict's output hinges on a scoring model whose constants
are spread across four files with no way to evaluate changes:
direct = 100 and reverse = 2 and indirect = 10·backlink² in `infer.sql`,
the 20-point step in `AggByScore`, `score >= 20 AS is_good` in
`generic.py`, `translation_score >= 100` and the adaptive threshold
targeting 45,000 entries in `tei.py`.

Two-part suggestion:

1. **Document and centralize** the model: one module (or one SQL file
   header) that defines the constants and explains the intent of each.
2. **Build a small evaluation harness** so changes become measurable
   instead of eyeballed: for a few language pairs, hold out the direct
   translations, run inference without them, and measure how well the
   inferred translations reproduce the held-out direct ones
   (precision/recall at the `is_good` threshold). The existing
   `expect`/`dont_expect` lists in `test_results.py` are the seed of this;
   the held-out approach scales it without manual labeling.

The currently failing `gehen → åka` regression shows the need: today there
is no way to tell whether a scoring tweak that fixes it makes everything
else better or worse.

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
