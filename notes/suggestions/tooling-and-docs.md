# Tooling, build & docs

## Resolved (pip/venv → uv migration leftovers)

- `Makefile` no longer has the dead `venv` prerequisite — `all: wdweb check`.
- `src/run.py` shebang is `#!/usr/bin/env -S uv run python`.
- `README.md` and `CLAUDE.md` describe the uv + pyoxigraph workflow.
- `pyproject.toml` has a real `description`, and `src/wdweb.py` loads spellfix
  via the `sqlite-spellfix` package (`sqlite_spellfix.extension_path()`)
  instead of the checked-in `lib/spellfix1.so`.
- The hardcoded Virtuoso endpoint is gone with the migration to the embedded
  pyoxigraph store.

## Open

### CI

There is still no CI. A minimal GitHub Actions job could now run the pure unit
tests (`test_parse`, `test_infer`), the end-to-end fixture (`test_e2e`, no
server needed), and a linter (`ruff`, see code-quality.md) on every push — it
would have caught the parse test that was failing at review time.

### Misc

- `src/anki_csv.sh` and `src/sitemap.py` are not mentioned in README or
  Makefile; a one-line comment each on how/when they're run would help.
