# Testing

## Resolved (from the 2026-06-12 review)

- `test_parse.TestParseHTML.test_entity` — the underlying `parse()` bug is
  fixed (bugs.md #1), so this passes.
- **Pure unit tests are separated from data tests.** `test_results.py` now
  uses `@unittest.skipUnless(os.path.exists(INFER_DB), ...)`, so the suite is
  runnable on a fresh checkout instead of failing with a confusing
  `OperationalError`.
- The `ResourceWarning: unclosed database` during the test run is gone —
  connections are closed (see code-quality.md, resolved).
- A miniature end-to-end test now exists (`test_e2e.py`, architecture.md #5).

## Open

- **The `de→sv "gehen" → "åka"` data-quality regression.** When a built
  `dictionaries/infer.sqlite3` is present, `test_results.test_dont_expect`
  still trips on this (score 187.7). The real fix is the measurable scoring
  model in architecture.md #4 — today there's no way to tell whether a scoring
  tweak that fixes it makes everything else better or worse.
- **Grow the `expect`/`dont_expect` lists.** They check only one pair each; a
  handful of known-good/known-bad translations per major language pair would
  catch scoring regressions cheaply.
- **`parse.py` cleaning functions are untested for edge cases** the code
  special-cases: `clean_wiki_syntax` brace handling, `is_dummy_sense`, and
  `make_inflection_cleaner("de")` (pronoun/article stripping).
