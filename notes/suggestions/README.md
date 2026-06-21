# Improvement suggestions

From a full-project review on 2026-06-12, pruned 2026-06-21 to reflect what
has since shipped. Each file now keeps a short "Resolved" log of completed
items plus the still-open ones in full.

- [architecture.md](architecture.md) — bigger-picture ideas. **Done:** the
  Virtuoso→pyoxigraph migration (#1) and the miniature end-to-end fixture (#5).
  **Open:** partitioning the 47 GB inference step, per-language config, a
  measurable scoring model, the `written_rep_guess` join, provenance metadata.
- [bugs.md](bugs.md) — all seven concrete bugs are fixed; kept as a resolved
  log, with the per-edition `translation_sense` measurements retained for
  reference.
- [testing.md](testing.md) — the two failing tests and the skip-guard are
  handled; the `gehen → åka` scoring regression is the one open data item.
- [tooling-and-docs.md](tooling-and-docs.md) — the uv-migration leftovers are
  cleared. **Open:** still no CI.
- [code-quality.md](code-quality.md) — dead code, the sitemap guard and the
  connection leaks are done; small robustness/modernization nits remain.

What's worth doing next, roughly by payoff:

1. Add CI (pure unit tests + the e2e fixture + a `ruff` lint) — now runnable
   without a server thanks to the pyoxigraph migration (tooling-and-docs.md,
   code-quality.md).
2. Make the translation-scoring model explicit and measurable, which is what
   it takes to settle the `gehen → åka` regression (architecture.md #4,
   testing.md).
3. The larger architecture items: partition the 47 GB inference step (#2),
   per-language config (#3), the `written_rep_guess` join (#6), provenance
   metadata (#7).
