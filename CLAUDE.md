# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WikDict-gen is a Python-based dictionary generator that extracts multilingual translation data from dbnary dumps (loaded into an embedded pyoxigraph RDF store) to create various dictionary formats. It supports 25 languages and generates dictionaries in multiple formats (SQLite, TEI XML, Kobo, StarDict).

## Development Commands

### Setup
```bash
make download     # Fetch the dbnary dumps into virtuoso/ttl/
make              # Full build: load the store, generate all dictionaries, run checks
uv sync           # Install dependencies into .venv (done automatically by `uv run`)
```

### Testing
```bash
make test         # Run all unit tests
uv run -m unittest discover -s src
```

### Build Targets
```bash
uv run src/run.py load-store  # Bulk-load the dbnary dumps into the pyoxigraph store
make raw          # Build the store if needed, then query it into raw dictionaries
make processed    # Process raw dictionaries
make generic      # Create generic SQLite dictionaries
make wdweb        # Generate WikDict web format dictionaries
make check        # Check for empty databases
```

### Cleaning
```bash
make clean        # Remove dictionaries directory
make distclean    # Remove dictionaries and venv
```

### Quick Dictionary Lookup
```bash
src/run.py search de en haus  # Search German-English for "haus"
```

## Architecture

### Data Pipeline
1. **pyoxigraph store** (`src/sparql/store.py`): bulk-loads dbnary TTL dumps, each edition into its own named graph, into an embedded on-disk RDF store (`dictionaries/store`)
2. **Raw Extraction** (`src/sparql/`): SPARQL queries (`queries.py`) run against the store via `backend.py`; single-edition queries are scoped to one graph, cross-edition ones query the union. Output goes to raw SQLite databases
3. **Processing** (`src/process.py`): Processes raw data, adds language-specific processing
4. **Inference** (`src/infer.py`): Generates translation inferences between language pairs
5. **Output Generation**: Creates multiple dictionary formats

### Scoring model
All translation-scoring constants live in **`src/scoring.py`** (the single source
of truth): the direct/reverse/indirect path weights, the `COMBINE_DECAY` that sets
how multiple paths to one target are combined, the `AggByScore` step, and the
`is_good`/TEI thresholds. They are substituted into `src/infer.sql` by
`infer.py:render_sql()` (plain SQL can't import Python) and imported by
`generic.py`/`tei.py`. The combine is `max + COMBINE_DECAY·(sum − max)`: at decay
1.0 it is a plain `sum()`; lower decay gives diminishing returns on extra pivot
paths, which stops polysemous "hub" pivots from summing a wrong translation past
the threshold (the former `de→sv "gehen" → "åka"` regression). Change a constant
here, then re-run the evaluation harness.

### Evaluating the scoring model
`src/evaluate.py` measures a scoring change instead of eyeballing it. It holds out
each language pair's human-curated direct translations, lets inference reproduce
them through the other languages as pivots, and reports precision/recall/F1 at the
`is_good` threshold (plus the `gehen → gå`/`gehen → åka` probes). It reads a built
`dictionaries/infer.sqlite3` and needs no rebuild.
```bash
uv run src/run.py evaluate            # default decay/threshold on a few pairs
uv run src/run.py evaluate --sweep    # grid over decay x is_good threshold
make evaluate                         # the --sweep run
```

### Key Components

- **`src/run.py`**: Main entry point with subcommand dispatch
- **`src/helper.py`**: Utilities for language handling and database operations
- **`src/sparql/`**: SPARQL query execution and database extraction
- **`src/process.py`**: Dictionary processing pipeline
- **`src/wdweb.py`**: WikDict web format generation
- **`src/generic.py`**: Generic SQLite dictionary generation
- **`src/languages/`**: Language configuration and metadata
- **`Makefile`**: Build system with complex dependency management

### Database Structure
- **Raw**: Direct SPARQL extraction results
- **Processed**: Cleaned and enhanced dictionaries with language-specific processing
- **Generic**: Standardized format for general use
- **WdWeb**: Optimized format for the WikDict website

### Supported Languages
25 languages: bg, ca, cs, da, de, el, en, es, fi, fr, ga, id, it, ja, ku, la, lt, mg, nl, no, pl, pt, ru, sv, tr, zh

## Important Files

- **`generated.mk`**: Auto-generated Makefile rules for language pairs (update with `uv run src/helper.py makefile > generated.mk`)
- **`src/languages/languages.tsv`**: Language metadata (codes, names)

### Generating the KOReader dictionary list
KOReader ships a downloadable-dictionary list in its `frontend/ui/data/dictionaries.lua`. To
(re)generate the WikDict entries from the built StarDict dictionaries, run:
```bash
uv run src/helper.py koreader > dictionaries_wikdict.lua
```
This reads every `dictionaries/stardict/wikdict-*/stardict.ifo` and prints a self-contained Lua
module (name, ISO 639-3 codes, headword count, license, download URL per pair). Because the list
is large and regenerated, it is kept as a separate file `frontend/ui/data/dictionaries_wikdict.lua`
in KOReader and merged into `dictionaries.lua` with:
```lua
for _, d in ipairs(require("ui/data/dictionaries_wikdict")) do
    table.insert(dictionaries, d)
end
```
Requires `make stardict` to have been built first. The generated file lives at
`misc/dictionaries_wikdict.lua`.
- **`src/sparql/store.py`**: pyoxigraph store loading (`load-store`) and read-only opening
- **`virtuoso/ttl/`**: the downloaded dbnary TTL dumps (directory name is historical; no Virtuoso involved any more)
- **`pyproject.toml`**: Project metadata and dependencies (`pyoxigraph`, `tabulate`, `sqlite-spellfix`), managed with uv

## Testing
Unit tests are in `src/tests/`. The main test files cover:
- `test_infer.py`: Translation inference logic
- `test_parse.py`: Data parsing functionality
- `test_results.py`: Output validation (needs a built `dictionaries/infer.sqlite3`; skipped otherwise)
- `test_e2e.py`: Miniature end-to-end test. Loads the hand-built de/en/sv TTL fixtures
  in `src/tests/fixtures/` into a temporary pyoxigraph store and runs the whole
  pipeline (raw → processed → infer → generic → wdweb), asserting on the outputs.
  Runs on a fresh checkout in seconds with no pre-built database.

### Redirecting the output directory
All generated databases default to `dictionaries/`. Set `WIKDICT_DICT_DIR` to build
into another directory instead (the store follows it unless `WIKDICT_STORE` is also
set). `test_e2e.py` uses this to build into a temp dir without touching the real
`dictionaries/`.