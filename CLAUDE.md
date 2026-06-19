# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WikDict-gen is a Python-based dictionary generator that extracts multilingual translation data from a Virtuoso database filled with dbnary data to create various dictionary formats. It supports 25 languages and generates dictionaries in multiple formats (SQLite, TEI XML, Kobo, StarDict).

## Development Commands

### Setup
```bash
make              # Full build: generates all dictionaries, runs checks
uv sync           # Install dependencies into .venv (done automatically by `uv run`)
```

### Testing
```bash
make test         # Run all unit tests
uv run -m unittest discover -s src
```

### Build Targets
```bash
make raw          # Generate raw dictionaries from Virtuoso data
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
1. **Virtuoso Database**: Contains dbnary RDF data loaded from TTL files
2. **Raw Extraction** (`src/sparql/`): SPARQL queries extract data to raw SQLite databases
3. **Processing** (`src/process.py`): Processes raw data, adds language-specific processing
4. **Inference** (`src/infer.py`): Generates translation inferences between language pairs
5. **Output Generation**: Creates multiple dictionary formats

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
- **`virtuoso/`**: Virtuoso database setup and data loading scripts
- **`pyproject.toml`**: Project metadata and dependencies (`tabulate`, `sqlite-spellfix`), managed with uv

## Testing
Unit tests are in `src/tests/`. The main test files cover:
- `test_infer.py`: Translation inference logic
- `test_parse.py`: Data parsing functionality
- `test_results.py`: Output validation