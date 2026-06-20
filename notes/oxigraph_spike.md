# pyoxigraph spike — replacing Virtuoso (architecture suggestion #1)

Spike run 2026-06-19 on the `fr` dumps (the second-largest edition), comparing
pyoxigraph 0.5.9 output against the existing Virtuoso-built raw dbs in
`dictionaries/raw/` (both from the Nov-20-2025 dbnary extraction). Scripts:
`notes/oxigraph_spike.py` (load + form/entry), `notes/oxigraph_query.py`
(translation). The 3.8 GB on-disk store they build is throwaway (rebuild in ~90 s).

## Full migration results (2026-06-20, branch `oxigraph-migration`)

Implemented and verified at full scale. Key measured numbers:

- **Store build:** 566,855,781 triples from 81 dumps (27 editions × ontolex +
  exolex_ontolex + morphology), each edition in its own named graph. Load ~78 min,
  `optimize()` ~26 min, **97 GB on disk**, peak RSS only **3.6 GB** (on-disk store;
  an in-memory store OOM-crashed the machine, as the spike warned).
- **The performance trap:** queries on a single *default-graph* union store ran
  ~7–14 min each (warm == cold, oxigraph join-eval bound) — a ~20 h full build.
  Fix = per-edition **named graphs** + scoping single-edition queries to one graph.
- **Query speed after fix:** scoped `fr form` 96 s (was 416 s flat); `fr-en`
  translations 19 s total; cross-edition `fr entry` ~7 min (inherent to the union).
  fr+de full single-language raw in parallel: ~35 min.
- **Two more query gotchas found at scale:** oxigraph's `NOT IN` errors on an
  unbound var (importance `pos` FILTER → guard with `!BOUND`); a **blank node inside
  OPTIONAL** is planned pathologically slowly (translation_gloss timed out → use an
  explicit gloss-node variable, 7 s).
- **Parity vs the old Virtuoso raw dbs (fr & de):** entry/form/pos/gender/pronun/
  nym/importance **match exactly** (importance vocable set exact; scores within the
  translation-drift noise). Translation tables differ only by the upstream dbnary
  model change (bug #6): the new rows are a strict subset of the stale reference.
- **Downstream:** `process` fr/de/fr-de and `search fr de eau` work and look
  correct; 11/12 unit tests pass (the 1 failure is the pre-existing `gehen→åka`
  scoring regression, unrelated).

Tradeoffs to remember: the named-graph store is ~2× the flat store on disk (97 GB
vs ~50 GB) and ~2× slower to load. A full `make raw` (25 langs + 600 pairs) is a
multi-hour batch (cross-edition single-language queries dominate), but unattended
and Docker-free.

## Verdict

**pyoxigraph is viable, but the migration is more than a mechanical port.** Core
feasibility is proven (load works, `form` reproduces exactly), but the spike
surfaced three things that reshape the plan — one of which is a pre-existing
pipeline bug unrelated to the engine.

## What worked

- **Bulk load:** `fr` ontolex (166 MB gz) + morphology (21 MB gz) → 24.06M
  triples into an **on-disk** RocksDB store in **90.8 s**. No Docker, no server.
- **`form` query: 773,721 rows — byte-for-byte the same count as Virtuoso.** The
  star-shaped queries port cleanly once PREFIX declarations are added.
- **Memory:** the on-disk store loads within a normal RAM budget. (An *in-memory*
  `Store()` instead blew past 30 GB on `fr` alone and OOM-crashed the machine —
  the migration MUST use the on-disk store, and any spike should run under a
  `systemd-run --user --scope -p MemoryMax=…G -p MemorySwapMax=0` cap.)

## Finding 1 — union-graph dependency (changes the migration design)

The current SPARQL queries run with `default-graph-uri=""`, i.e. over the **union
of all 27 language graphs**. Proof from the reference `fr` raw db:

- `entry` (2.38M rows): only **548k are `fra/`**; the rest are French-language
  entries contributed by *every other edition's exolex dump* (1.3M Malagasy,
  369k English, 74k Greek, …).
- `form` (774k) and `translation_sense` (49k): **100 % `fra/`** — single-edition.

So the note's guess that exolex dumps are "loaded for nothing" is **wrong** for
`entry`/`pos`/`gender`/`pronun`/`importance`/`nym`: those depend on the union.
A pyoxigraph design can't load just one language's dumps per raw db — it needs
either all editions in one store, or an explicit redesign of cross-edition entry
collection.

## Finding 2 — Virtuoso-isms must be rewritten for compliant SPARQL

oxigraph is standards-compliant and rejects several Virtuoso extensions the
queries rely on:

- **AS-alias onto a bound variable**: `(?written_trans AS ?trans)` while `?trans`
  is already bound in WHERE → `SyntaxError: SELECT overrides an existing variable`.
  Rename the WHERE variable (`queries.py` translation sense/gloss).
- **`bif:sqrt`** in `importance_query` — no SPARQL-standard equivalent. Compute
  the score in Python/SQL after fetching the counts.
- **Namespace prefixes** are global in Virtuoso (`XML_SET_NS_DECL`); each query
  must now carry explicit `PREFIX` lines.

## Finding 3 — `translation_sense` is already broken on current dbnary (engine-independent)

> **Superseded — see `notes/suggestions/bugs.md` #6 for the corrected analysis.**
> In short: the reference dbs are a *stale older-release* file (not the on-disk
> `20251101` dump), so "a fresh Virtuoso build would also return 0" and "new rows
> are a strict subset of the stale reference" hold only for the editions dbnary has
> migrated (fr, de, …). The model drift is *per-edition*: `pl` is still 100%
> sense-linked and the gloss-`senseNumber` join returns **0** for it, so the proper
> fix runs *both* the gloss-join and the direct-link query and merges them.

The biggest surprise, and **not** a pyoxigraph problem. In the current `fr` dump
**all 1.38M translations link to the lexical entry**, and **zero** link to a
`LexicalSense` (`isTranslationOf fra:accueil__nom__1`, never `…__ws_…`). Each
translation carries a `dbnary:gloss` → `dbnary:Gloss` node that holds the
`senseNumber`.

But `translation_query["sense"]` requires `?trans dbnary:isTranslationOf ?sense`
— so it matches **0 rows today**. The 49,012 rows in the reference db are from an
**older dbnary model**; a fresh Virtuoso build would also return 0 now. This is
the same class of silent per-edition model drift the wikidata note flagged for
Indonesian (#166), surfaced here by the apples-to-apples diff. Worth a separate
issue regardless of the pyoxigraph decision. **(Confirm against a fresh Virtuoso
run — the spike couldn't, no Docker available.)**

The fix is to join sense↔translation on `senseNumber` via the gloss node — which
leads to:

## Finding 4 — oxigraph's query planner needs hand-tuning

The modernized join (sense `senseNumber` = gloss `senseNumber`, scoped per entry)
did not complete under the memory cap. Likely cause: the planner joins the two
`senseNumber` patterns *before* constraining by `?lexentry`, and since
`senseNumber` values are just `"1"`,`"2"`,… shared dataset-wide, that's a near-
cartesian explosion. Virtuoso's planner avoids it. Mitigations: name the gloss
node, force join order, or use a subquery. Means: queries that touch large
intermediate results need profiling/rewriting, not just translation.

## Implications for sequencing

- Spike answers the feasibility question **yes**, with caveats above. A full
  migration is more like the note's "~2–3 weeks" end, not the optimistic end.
- Finding 1 (union graph) and Finding 3 (translation model) are exactly the kind
  of behavior the **end-to-end fixture (#5)** must encode — another argument for
  doing the pyoxigraph work first, then building the fixture on the in-process
  store so it pins down the *current* (correct) translation semantics.
