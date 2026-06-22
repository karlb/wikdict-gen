# Architecture & concept suggestions

Bigger-picture ideas, roughly ordered by expected payoff.

**Shipped (removed from this list):** #1 Virtuoso → embedded pyoxigraph store;
#4 explicit, measurable scoring model (`src/scoring.py` + `src/evaluate.py` +
`src/precision_gold.py`, threshold 20 → 15); #5 the miniature end-to-end fixture
(`src/tests/test_e2e.py`). The scoring lessons that came out of #4 (corroboration
must not be penalised; the reverted decay/fan-out experiments) live in
`scoring-improvement.md`.

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
global as the common input. The `sources` and `source_details` columns in the
`infer` table are confirmed debugging helpers — nothing downstream reads them,
so dropping them (or only populating them under a debug flag) should shrink the
database substantially.

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
