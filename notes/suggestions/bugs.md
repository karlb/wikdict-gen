# Bugs

Found during a project review on 2026-06-12, ordered roughly by impact.

## 1. `parse()` skips entity conversion for tag-free input

`src/parse.py:81` short-circuits `if "<" not in html: return html` as a
performance optimization, but that also skips entity references like
`&nbsp;`. This is the cause of the currently failing
`tests.test_parse.TestParseHTML.test_entity`. Fix: also check for `&`,
e.g. `if "<" not in html and "&" not in html`.

## 2. `repeated_sub()` ignores its arguments

`src/parse.py:103` takes `regex` and `replacement` parameters but the loop
body hardcodes `double_brackets.subn(r"\1", ...)`. It works today only
because the single caller happens to pass exactly those values. Either drop
the parameters (rename to `remove_double_brackets`) or use them.

## 3. `make_search_by_form` optimizes the wrong FTS table

`src/wdweb.py:289` runs `INSERT INTO main.search_trans(search_trans)
VALUES('optimize')` — a copy-paste from `make_search_index`. It should
optimize `search_by_form`, so that table is never optimized (and
`search_trans` is optimized twice).

## 4. `test_expect` crashes instead of reporting a missing expectation

`src/tests/test_results.py:53-59`: when `best_match(ex)` returns `None`, the
code appends to `missing` but then still does `score = match[4]`, raising
`TypeError` instead of showing the nice assertion message. Add a `continue`
after the append.

## 5. TEI inflected forms use only one lexentry per entry

`src/tei.py:271-282`: entries are grouped by (written_rep, pos, gender,
pronun_list), which can span several lexentries, but the inflected-forms
query uses `t["lexentry"]` where `t` is whatever row the inner loop ended
on. Forms of the other lexentries in the group are silently dropped. If
intentional (forms should be identical across these lexentries), a comment
would help; otherwise collect forms for all lexentries in the group.

## 6. `translation_sense`: migration dropped the direct-link path, regressing `pl`  [PARTIAL — pl open]

The pyoxigraph migration **replaced** the sense query instead of adding to it: the
old direct-link form (`?trans dbnary:isTranslationOf ?sense`) was swapped for a
gloss-`senseNumber` join (`?trans dbnary:gloss [dbnary:senseNumber ?n]` matched to
the entry's `?sense dbnary:senseNumber ?n`). That was *necessary* for editions
dbnary has migrated to the entry+gloss model (fr-en: 0 → 23,798), but it silently
**regressed `pl` to 0** — trading one silent regression for another.

**The fix is to run BOTH and merge** (the direct-link query *and* the gloss-join
query, unioned/deduped into `translation_sense`, then the existing sense→gloss
backfill in `src/sparql/run.py:41` proceeds). Neither alone is correct: gloss-join
is 0 for pl, direct-link is 0 for fr/de. No per-language config needed — this is
just restoring the second half of the "use both" idea at the sense level.

### Three groups, measured on the `20251101` dump (live store + dump grep)

| group | editions | direct-link | gloss-join (current query) | definitions recoverable |
|---|---|---|---|---|
| A | de, el, en, es, fi, fr, ja, pt, ru | 0\* | works | yes — current query OK |
| B | **pl** | **69,382** | **0** | only via direct link — **current query gives 0** |
| C | bg, ca, cs, da, ga, id, it, ku, la, lt, mg, nl, no, sh, sv, tr, zh | 0 | 0 | none from this dump (no link of either kind) |

\* es is hybrid: gloss-join works *and* a partial direct link exists (1,782, fully
subsumed by the 12,697 from gloss-join). pl gloss-join fails because pl encodes the
gloss sense number as `"[1.1]"` (bracketed) while the lexical sense uses `"1.1"`, so
the string-equality join never matches; fr uses bare `"1"` on both sides.

### Corrections to the original report (below)

1. **Reference dbs are a stale older-release file, not the on-disk dump.** The two
   on-disk dump copies (`*.ttl.bz2` Nov 2, `*.ttl.gz` Nov 20) are byte-identical
   (same md5) — one release, Wiktionary dump `20251101`. But the
   `dictionaries/raw/` reference dbs weren't built from it: `ca-en` has 16,573
   `translation_sense` rows and `it-en` 52,068, yet the on-disk `ca`/`it` dumps
   have **zero** sense-linked translations — impossible for the old query to
   produce from this dump. Tables are `DROP`+`CREATE` every run (old and new
   code), so these aren't row leftovers; the whole file predates the on-disk dump
   (Make skip, or a stale Virtuoso load). So the "49,012 vs 23,798" comparison was
   cross-release. (`fr-en` was overwritten to 23,798 by the migration.)

2. **The drift is per-edition and gradual.** Only `pl` (100% sense-linked,
   714,699) and `es` (hybrid, 7.4%) still carry a direct sense link; the other 25
   editions are fully entry+gloss. So "old query returns 0 today" is true for fr +
   24 editions but false for pl.

3. **Group C is *not* lost data — mostly it's the normal gloss-only state.** These
   editions are full of senses+definitions (ca: 568k `skos:definition`, nl: 234k,
   it: 98k); what they lack is any translation→sense *link* in this dump. And per
   the pre-2024 per-language `translation_query_type` map (deleted by `c91779b`,
   2024-03), most of Group C — sv, bg, it, id, nl, lt, la, mg, no — were already
   declared `"gloss"`: gloss was their primary all along. `tr` and `pl` are the
   `"sense"`-era exceptions; `pl` is the only one still sense-primary today and the
   only one the gloss path can't cover for definitions.

4. **Coverage of translations is never at risk** — every translation has
   `isTranslationOf → entry`, so `translation_gloss` catches them all in every
   edition/model. Only the *definition linkage* degrades; the merge backfills the
   rest.

Same class of per-edition drift as Indonesian #166. The original "confirm against a
fresh Virtuoso build" caveat is moot — verified against the dumps and the in-process
store. **Remaining work:** restore the direct-link sense query (UNION both); add a
regression guard that trips when an edition's definition-linked ratio collapses
(empty-db checks don't catch it — gloss keeps the table non-empty).

---

(original report — superseded by the corrections above; kept for history)

`src/sparql/queries.py:86` (`translation_query["sense"]`) requires
`?trans dbnary:isTranslationOf ?sense` where `?sense` is a `LexicalSense`.
But in the current dbnary model translations link to the **lexical entry**, not
to a sense — verified on the 2026-06 `fr` dump: all 1.38M translations are
entry-linked, **zero** are sense-linked. The sense number now lives on the
`dbnary:Gloss` node hanging off each translation (`?trans dbnary:gloss
[dbnary:senseNumber ?n]`). So the query matches **0 rows today**; the
`translation_sense` rows in existing raw dbs (e.g. 49,012 for fr-en) are from an
older extraction. A fresh build silently loses every sense-linked (definition-
bearing) translation, leaving only the lower-quality `translation_gloss` path.

Fix: join the sense to the translation on `senseNumber`, scoped per entry —
match `?lexentry ontolex:sense ?s . ?s dbnary:senseNumber ?n` against
`?trans dbnary:isTranslationOf ?lexentry ; dbnary:gloss [dbnary:senseNumber ?n]`.
Same class of silent per-edition model drift as Indonesian #166. Found during the
pyoxigraph spike (see `notes/oxigraph_spike.md`, Finding 3) via an
apples-to-apples diff; should be confirmed against a fresh Virtuoso build.

## 7. Minor typos

- `src/infer.py:19`: column type `to_importance floa` (harmless in SQLite,
  but clearly meant `float`).
- `src/helper.py:204`: "Unknwn command". Also: an unknown command prints a
  message but exits 0; `sys.exit(1)` would let Make fail properly.
