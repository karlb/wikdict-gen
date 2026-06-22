# Improvement suggestions

From a full-project review on 2026-06-12, pruned 2026-06-22: resolved items and
the shipped-migration spike notes have been removed; each file now lists only the
still-open work. (All seven concrete bugs and the Virtuoso→pyoxigraph migration
shipped, so the old `bugs.md` and `oxigraph_spike.md` are gone — git history has
them.)

- [architecture.md](architecture.md) — **Open:** partition the 47 GB inference
  step (#2), per-language config (#3), provenance metadata (#7).
- [scoring-improvement.md](scoring-improvement.md) — no open task; kept as the
  record of the settled scoring decisions (precision gold, combined objective,
  threshold 20→15, reverted decay/fan-out, P5137 rejected) so they aren't
  re-proposed.
- [testing.md](testing.md) — **Open:** promote the 32 confirmed false positives
  to `dont_expect` guards once a net-positive scoring change removes them.
- [tooling-and-docs.md](tooling-and-docs.md) — **Open:** still no CI; document
  `anki_csv.sh` / `sitemap.py`.
- [code-quality.md](code-quality.md) — **Open:** commented-out blocks, a
  `validate_lang()` assert, f-string modernization, a `ruff` config.

What's worth doing next, roughly by payoff:

1. **Add CI** (pure unit tests + the e2e fixture + a `ruff` lint) — now runnable
   without a server thanks to the pyoxigraph migration.
2. **The larger architecture items:** partition the 47 GB inference step (#2),
   per-language config (#3), provenance metadata (#7).
