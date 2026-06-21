# Bugs

Found during a project review on 2026-06-12. **All resolved** as of
2026-06-21 — kept as a log (verified against current code), with the
per-edition `translation_sense` measurements retained below for reference.

## Resolved

1. **`parse()` skipped entity conversion for tag-free input** — the
   `if "<" not in html: return html` short-circuit also skipped entity
   references like `&nbsp;`. Fixed: `src/parse.py` now guards on
   `if "<" not in html and "&" not in html`. (Was the cause of the failing
   `tests.test_parse.TestParseHTML.test_entity`.)
2. **`repeated_sub()` ignored its arguments** — the loop body hardcoded the
   substitution. Fixed: `src/parse.py:90` now applies the passed `regex` /
   `replacement`.
3. **`make_search_by_form` optimized the wrong FTS table** — copy-pasted
   `optimize` ran against `search_trans`. Fixed: `src/wdweb.py:290` now
   optimizes `search_by_form`.
4. **`test_expect` crashed instead of reporting a missing expectation** —
   missing `continue` after appending to `missing`. Fixed:
   `src/tests/test_results.py` now `continue`s.
5. **TEI inflected forms used only one lexentry per entry** — forms of the
   other lexentries in a group were dropped. Fixed: `src/tei.py` collects
   forms for all lexentries in the group.
6. **`translation_sense`: migration dropped the direct-link path** — see the
   detail below; fixed by running both the direct-link and gloss-join queries
   and merging, plus a definition-ratio regression guard. This restores `pl`
   (the only edition still sense-primary today) without regressing the
   entry+gloss editions.
7. **Minor typos** — `to_importance floa` → `float` (`src/infer.py:20`);
   "Unknwn command" → "Unknown command", now also `sys.exit(1)`
   (`src/helper.py:258`).

---

## Reference: the `translation_sense` per-edition drift (bug #6)

The pyoxigraph migration **replaced** the sense query instead of adding to it:
the old direct-link form (`?trans dbnary:isTranslationOf ?sense`) was swapped
for a gloss-`senseNumber` join (`?trans dbnary:gloss [dbnary:senseNumber ?n]`
matched to the entry's `?sense dbnary:senseNumber ?n`). That was *necessary*
for editions dbnary has migrated to the entry+gloss model (fr-en: 0 → 23,798),
but it silently **regressed `pl` to 0**. The fix runs BOTH and merges (then the
sense→gloss backfill in `src/sparql/run.py` proceeds). Neither alone is
correct: gloss-join is 0 for pl, direct-link is 0 for fr/de.

### Three groups, measured on the `20251101` dump (live store + dump grep)

| group | editions | direct-link | gloss-join | definitions recoverable |
|---|---|---|---|---|
| A | de, el, en, es, fi, fr, ja, pt, ru | 0\* | works | yes |
| B | **pl** | **69,382** | **0** | only via direct link |
| C | bg, ca, cs, da, ga, id, it, ku, la, lt, mg, nl, no, sh, sv, tr, zh | 0 | 0 | none from this dump |

\* es is hybrid: gloss-join works *and* a partial direct link exists (1,782,
subsumed by the 12,697 from gloss-join). pl gloss-join fails because pl encodes
the gloss sense number as `"[1.1]"` (bracketed) while the lexical sense uses
`"1.1"`, so the string-equality join never matches; fr uses bare `"1"` on both
sides.

### Notes on the data

- The drift is per-edition and gradual. Only `pl` (100% sense-linked) and `es`
  (hybrid, 7.4%) still carry a direct sense link; the other 25 editions are
  fully entry+gloss.
- Group C is *not* lost data — mostly the normal gloss-only state. These
  editions are full of senses+definitions (ca: 568k `skos:definition`, nl:
  234k, it: 98k); what they lack is any translation→sense *link* in this dump.
  Per the pre-2024 per-language `translation_query_type` map (deleted by
  `c91779b`, 2024-03), most of Group C was already declared `"gloss"`.
- Coverage of *translations* is never at risk — every translation has
  `isTranslationOf → entry`, so `translation_gloss` catches them all in every
  edition. Only the *definition linkage* degraded; the merge backfills the rest.
