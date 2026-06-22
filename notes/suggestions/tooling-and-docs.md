# Tooling, build & docs

(The pip/venv → uv migration leftovers — the dead `venv` prerequisite, the
`uv run` shebang, the README/CLAUDE docs, the `pyproject` description, the
`sqlite-spellfix` package, the dropped Virtuoso endpoint — have all shipped and
were removed from this list.)

## Open

### CI

There is still no CI. A minimal GitHub Actions job could now run the pure unit
tests (`test_parse`, `test_infer`), the end-to-end fixture (`test_e2e`, no
server needed), and a linter (`ruff`, see code-quality.md) on every push — it
would have caught the parse test that was failing at review time.

### Misc

- `src/anki_csv.sh` and `src/sitemap.py` are not mentioned in README or
  Makefile; a one-line comment each on how/when they're run would help.
