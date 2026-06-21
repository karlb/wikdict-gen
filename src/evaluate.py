"""Measure the translation-scoring model with held-out direct translations.

The scoring constants live in ``scoring.py``; this harness makes a change to them
measurable instead of eyeballed (architecture.md #4). For a set of language
pairs it asks: if we *hide* a pair's human-curated direct translations and let
inference run through the other languages as pivots, how well does inference
reproduce those held-out edges?

  precision = inferred-good targets that are held-out gold / all inferred-good
  recall    = held-out gold recovered as inferred-good / all held-out gold
  F1        = harmonic mean, at the is_good score threshold

It reads a built ``infer.sqlite3`` and needs no rebuild. Why that is sound: the
indirect (pivot-inferred) paths for A->B are ``A->pivot`` then ``pivot->B`` and
never use the A->B direct edge, so the ``source='indirect'`` rows of
``with_lexentry`` already *are* the held-out inference for A->B -- whether or not
the direct edge is present. We read held-out predictions from those rows and the
gold set from the ``source='direct'`` rows. ``with_lexentry`` is also indexed on
``(from_lang, to_lang)``, so each pair scores in seconds. The combine
(``scoring.COMBINE_DECAY``) is decay-only and applied here, so the same built DB
serves every candidate decay -- the indirect/direct path scores are decay-free.

The ``gehen``/``åka`` probes reconstruct the production ``infer_grouped`` for
de->sv 'gehen' at the candidate decay (direct + indirect, then AggByScore),
mirroring ``tests/test_results.py``.

    uv run src/run.py evaluate                 # default decay/threshold
    uv run src/run.py evaluate --sweep         # grid over decay x threshold
"""

import os
import sqlite3
from contextlib import closing

import scoring
from infer import AggByScore

# Default pairs to score: the gehen triad's pair plus a few well-covered ones.
DEFAULT_EVAL_PAIRS = ["de-sv", "sv-de", "de-fr", "fr-de", "en-sv", "fr-it"]

SWEEP_DECAYS = [0.0, 0.25, 0.5, 0.75, 1.0]
SWEEP_THRESHOLDS = [15, 20, 25, 30]

# Held-out prediction (indirect paths only), combined with the candidate decay
# exactly as infer.sql does, best sense per target.
_PRED_SQL = """
CREATE TEMP TABLE pred AS
WITH per_sense AS (
    SELECT from_vocable, to_vocable,
        max(score) + :decay * (sum(score) - max(score)) AS score
    FROM with_lexentry
    WHERE from_lang = :a AND to_lang = :b AND source = 'indirect'
    GROUP BY from_vocable, to_vocable, lexentry, sense_num, sense
)
SELECT from_vocable, to_vocable, max(score) AS score
FROM per_sense GROUP BY from_vocable, to_vocable
"""

_GOLD_SQL = """
CREATE TEMP TABLE gold AS
SELECT DISTINCT from_vocable, to_vocable
FROM with_lexentry
WHERE from_lang = :a AND to_lang = :b AND source = 'direct'
"""


def _counts(conn, a, b, decay, thresholds):
    """For one held-out pair, return gold_n and (tp, pred_n) per threshold."""
    conn.execute("DROP TABLE IF EXISTS pred")
    conn.execute("DROP TABLE IF EXISTS gold")
    conn.execute(_PRED_SQL, dict(a=a, b=b, decay=decay))
    conn.execute(_GOLD_SQL, dict(a=a, b=b))
    (gold_n,) = conn.execute("SELECT count(*) FROM gold").fetchone()
    per_thr = {}
    for thr in thresholds:
        (tp,) = conn.execute(
            "SELECT count(*) FROM pred JOIN gold USING (from_vocable, to_vocable) "
            "WHERE pred.score >= ?",
            [thr],
        ).fetchone()
        (pred_n,) = conn.execute(
            "SELECT count(*) FROM pred WHERE score >= ?", [thr]
        ).fetchone()
        per_thr[thr] = (tp, pred_n)
    return gold_n, per_thr


def _prf(tp, pred_n, gold_n):
    p = tp / pred_n if pred_n else 0.0
    r = tp / gold_n if gold_n else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def probe(conn, decay, threshold):
    """Production-output probes (de->sv 'gehen'), like test_results.py.

    Rebuilds infer_grouped semantics for this one vocable at the candidate decay:
    combine direct+indirect per target, then AggByScore per sense. Returns
    (gehen_ga_ok, gehen_aka_ok): gå present with a sense scored >= threshold,
    åka absent from every trans_list.
    """
    rows = conn.execute(
        """
        SELECT lexentry, sense_num, sense, to_vocable,
            max(score) + :decay * (sum(score) - max(score)) AS s
        FROM with_lexentry
        WHERE from_lang = 'de' AND to_lang = 'sv' AND from_vocable = 'gehen'
        GROUP BY lexentry, sense_num, sense, to_vocable
        """,
        dict(decay=decay),
    ).fetchall()
    groups = {}
    for lexentry, sense_num, sense, to_vocable, s in rows:
        groups.setdefault((lexentry, sense_num, sense), []).append((to_vocable, s))
    ga_ok = aka_ok = True
    found_ga = False
    for targets in groups.values():
        agg = AggByScore()
        for to_vocable, s in targets:
            agg.step(to_vocable, s)
        trans = agg.finalize().split(" | ") if agg.trans_list else []
        if "åka" in trans:
            aka_ok = False
        if "gå" in trans and max(s for _, s in targets) >= threshold:
            found_ga = True
    return found_ga, aka_ok


def report(conn, eval_pairs, decay, threshold):
    from tabulate import tabulate

    table, sum_tp, sum_pred, sum_gold, macro_f = [], 0, 0, 0, 0.0
    for pair in eval_pairs:
        a, b = pair.split("-")
        gold_n, per_thr = _counts(conn, a, b, decay, [threshold])
        tp, pred_n = per_thr[threshold]
        p, r, f = _prf(tp, pred_n, gold_n)
        table.append([pair, gold_n, pred_n, tp, f"{p:.3f}", f"{r:.3f}", f"{f:.3f}"])
        sum_tp += tp
        sum_pred += pred_n
        sum_gold += gold_n
        macro_f += f
    mp, mr, mf = _prf(sum_tp, sum_pred, sum_gold)
    table.append(["MICRO-AVG", sum_gold, sum_pred, sum_tp,
                  f"{mp:.3f}", f"{mr:.3f}", f"{mf:.3f}"])
    print(f"\n=== decay={decay}  is_good_threshold={threshold} ===")
    print(tabulate(table, ["pair", "gold", "pred", "tp", "P", "R", "F1"]))
    ga, aka = probe(conn, decay, threshold)
    print(f"micro-F1={mf:.3f}  macro-F1={macro_f / len(eval_pairs):.3f}  "
          f"| probe gehen->gå present: {'PASS' if ga else 'FAIL'}  "
          f"gehen->åka absent: {'PASS' if aka else 'FAIL'}")
    return mf, ga and aka


def evaluate(infer_db=None, eval_pairs=None, decay=None, threshold=None,
             sweep=False, **kwargs):
    infer_db = infer_db or f"{os.environ.get('WIKDICT_DICT_DIR', 'dictionaries')}/infer.sqlite3"
    if not os.path.exists(infer_db):
        raise SystemExit(f"No {infer_db}; build it with `make infer` first.")
    eval_pairs = eval_pairs.split(",") if eval_pairs else DEFAULT_EVAL_PAIRS
    decay = scoring.COMBINE_DECAY if decay is None else decay
    threshold = scoring.IS_GOOD_THRESHOLD if threshold is None else threshold

    with closing(sqlite3.connect(f"file:{infer_db}?mode=ro", uri=True)) as conn:
        if sweep:
            best = None
            for d in SWEEP_DECAYS:
                for thr in SWEEP_THRESHOLDS:
                    mf, ok = report(conn, eval_pairs, d, thr)
                    if ok and (best is None or mf > best[0]):
                        best = (mf, d, thr)
            if best:
                print(f"\nBest config passing both probes: decay={best[1]} "
                      f"threshold={best[2]} (micro-F1={best[0]:.3f})")
            else:
                print("\nNo config passed both probes.")
        else:
            report(conn, eval_pairs, decay, threshold)


def add_subparsers(subparsers):
    p = subparsers.add_parser(
        "evaluate", help="held-out precision/recall/F1 of the scoring model"
    )
    p.add_argument("--infer-db", dest="infer_db", default=None,
                   help="built infer.sqlite3 to read (default dictionaries/infer.sqlite3)")
    p.add_argument("--eval-pairs", dest="eval_pairs", default=None,
                   help="comma-separated from-to pairs to score")
    p.add_argument("--decay", type=float, default=None)
    p.add_argument("--threshold", type=int, default=None)
    p.add_argument("--sweep", action="store_true", help="grid over decay x threshold")
    p.set_defaults(func=evaluate)
