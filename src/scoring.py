"""Single source of truth for the translation-scoring model.

The inference pipeline scores each candidate translation, combines the scores of
the different paths that reach the same target, then keeps the good ones. Every
constant of that model lives here so the model is legible in one place and a
change can be measured (see ``src/evaluate.py``) instead of eyeballed.

Where each constant is used:
- ``src/infer.sql`` reads the edge weights and the combine via ``string.Template``
  substitution done in ``infer.py:infer()`` (plain SQL can't import Python).
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

# --- Combine: how a target's per-path scores become one score ----------------
# infer.score = max(score) + COMBINE_DECAY * (sum(score) - max(score))
#   COMBINE_DECAY = 1.0  =>  plain sum(score) (the historical behaviour)
#   COMBINE_DECAY = 0.0  =>  max(score) only
# Diminishing returns on extra paths stops a polysemous "hub" pivot word from
# letting many weak indirect paths add up past the threshold (the de->sv
# "gehen" -> "åka" regression: ~6 motion-verb pivots summed to >20). Direct
# (gold) translations score 100 from a single path, so they are unaffected by
# this. Tuned with src/evaluate.py.
COMBINE_DECAY = 0.5

# --- Keep / group thresholds -------------------------------------------------
# generic.py: score >= this AND has a lexentry => is_good.
IS_GOOD_THRESHOLD = 20
# AggByScore diversity gate: each kept translation raises the bar for the next.
AGG_SCORE_STEP = 20

# --- TEI adaptive threshold (tei.py) -----------------------------------------
TEI_GOOD_SCORE = 100
TEI_TARGET_GOOD = 45000
