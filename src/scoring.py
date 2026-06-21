"""Single source of truth for the translation-scoring model.

The inference pipeline scores each candidate translation, combines the scores of
the different paths that reach the same target, then keeps the good ones. Every
constant of that model lives here so the model is legible in one place and a
change can be measured (see ``src/evaluate.py``) instead of eyeballed.

The per-target combine is a plain ``sum(score)`` over a target's paths (see
infer.sql): corroboration from many pivots is evidence *for* a translation, so
there is deliberately no decay/penalty on extra paths.

Where each constant is used:
- ``src/infer.sql`` reads the edge weights via ``string.Template`` substitution
  done in ``infer.py:render_sql()`` (plain SQL can't import Python).
- ``AggByScore`` (``infer.py``) uses ``AGG_SCORE_STEP``.
- ``generic.py`` uses ``IS_GOOD_THRESHOLD`` for ``is_good``.
- ``tei.py`` uses ``TEI_GOOD_SCORE`` / ``TEI_TARGET_GOOD`` for its adaptive cutoff.

Changing the model means changing it here and re-running ``src/run.py evaluate``.
"""

# --- Edge weights: the raw score of a single translation path ----------------
# A translation stated directly in a source edition is strong evidence.
DIRECT_SCORE = 100
# Only the reverse edge exists (B->A but not A->B): weak evidence.
REVERSE_SCORE = 2
# Per-pivot indirect cap: round(backlink_score^2 * INDIRECT_MULTIPLIER, 1), so a
# perfectly back-linked pivot contributes at most this much. One indirect row is
# produced per pivot *language*.
INDIRECT_MULTIPLIER = 10
# Min indirect score when no backlink validates the pivot at all.
INDIRECT_FLOOR = 1

# --- Keep / group thresholds -------------------------------------------------
# generic.py: score >= this AND has a lexentry => is_good.
IS_GOOD_THRESHOLD = 20
# AggByScore diversity gate: each kept translation raises the bar for the next.
AGG_SCORE_STEP = 20

# --- TEI adaptive threshold (tei.py) -----------------------------------------
TEI_GOOD_SCORE = 100
TEI_TARGET_GOOD = 45000
