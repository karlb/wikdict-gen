# Code quality

Smaller cleanups; none urgent, all low-risk. (The 2026-06-12 review's resolved
items — dead `make_for_langs`/`entry_query`, closed connections, the sitemap
import-time guard, `xml.etree.ElementTree`, the SPARQL-paging `global cols` trap
— have shipped and were removed.)

## Open

### Dead / commented code

- Leftover commented-out blocks remain in a few spots (e.g. the commented
  inflection-spec rows and grouping note in `src/process.py make_entry`). Git
  history remembers them — they can go.

### Robustness

- Language codes are interpolated into SQL strings in several places
  (`helper.py make_targets` ATTACH, `generic.py` f-string, `process.py`
  `%`-format). All values come from `supported_langs`, so it's safe today, but
  a brief comment or a `validate_lang()` assert at the entry points would make
  that invariant explicit.
- `src/parse.py`: a single module-level `html_parser` instance with mutable
  state is registered as a SQLite function — fine single-threaded (and
  `parse()` resets its state), but any reentrant/parallel use would corrupt
  results. A per-call parser would be safer.

### Modernization (cosmetic)

- `%`-formatting and `.format()` are still common; f-strings would match the
  newer code (`sparql/run.py` already uses them). `codecs.open` (`tei.py`) →
  `open(..., encoding="utf-8")`.
- `supported_langs` in `helper.py` duplicates knowledge that belongs in
  `src/languages/` (which already has `languages.tsv` and generated metadata);
  one source of truth would prevent drift. (See architecture.md #3.)
- No linter/formatter is configured. The code is mostly Black-formatted
  already; adding `ruff` (lint + format) to `pyproject` and CI would lock that
  in and catch things like the unused-parameter bug that was in `repeated_sub`.
