"""Measure the translation-scoring model with held-out direct translations.

The scoring constants live in ``scoring.py``; this harness makes a change to them
measurable instead of eyeballed (architecture.md #4). For a set of language
pairs it asks: if we *hide* a pair's human-curated direct translations and let
inference run through the other languages as pivots, how well does inference
reproduce those held-out edges?

  precision = inferred-good targets that are held-out gold / all inferred-good
  recall    = held-out gold recovered as inferred-good / all held-out gold
  Fbeta     = precision-weighted harmonic mean (beta<1 favours precision),
              at the is_good score threshold

It reads a built ``infer.sqlite3`` and needs no rebuild. Why that is sound: the
indirect (pivot-inferred) paths for A->B are ``A->pivot`` then ``pivot->B`` and
never use the A->B direct edge, so the ``source='indirect'`` rows of
``with_lexentry`` already *are* the held-out inference for A->B. Gold is the
``source='direct'`` rows. ``with_lexentry`` is indexed on ``(from_lang,
to_lang)``, so each pair scores in seconds.

Held-out reconstruction is a *recall* proxy with a precision blind spot: the
gap-fills inference exists to produce have no direct edge, so it counts every one
of them as a false positive. ``precision_gold.py`` supplies the missing precision
term -- a labelled set of inferred-only gap-fills, judged independently of the
dbnary edges. When that gold is present this harness combines the two into one
objective (scoring-improvement.md #2): held-out reconstruction -> recall, the
gold -> precision, and an ``Fbeta`` over the pair. It also reports how many
labelled-correct gap-fills a variant *retains* -- the guardrail that catches the
mistake the reverted diminishing-returns combine made (dropping good gap-fills).

The production combine is a plain ``sum`` of a target's path scores. The harness
keeps one *experimental* knob it can vary without a rebuild:

  - ``fanout_alpha`` -- a per-path penalty for polysemous "hub" pivots:
    ``specificity = pivot_fanout^(-alpha)`` where pivot_fanout is how many
    target-language words the pivot translates to (parsed from ``source_detail``
    and joined to a fan-out table built from ``all_trans``). alpha=0 is the
    production model. This targets pivot *ambiguity* rather than corroboration
    count. The precision gold (``precision_gold.py``) is the known-false-positive
    set that finally lets ``--experiment`` judge it on precision, not just recall:
    each alpha's line shows gold precision and correct-retention. The estimate is
    approximate -- it penalises the max-backlink pivot already chosen per language;
    a faithful test rebuilds ``indirect`` with the factor.

    uv run src/run.py evaluate                 # combined recall + gold precision
    uv run src/run.py evaluate --sweep         # sweep the is_good threshold
    uv run src/run.py evaluate --experiment    # production vs fan-out variants
"""

import os
import sqlite3
from contextlib import closing

import scoring
from infer import AggByScore

# Default pairs to score: the gehen triad's pair plus a few well-covered ones.
DEFAULT_EVAL_PAIRS = ["de-sv", "sv-de", "de-fr", "fr-de", "en-sv", "fr-it"]

EVAL_BETA = 0.5  # precision-weighted: a wrong dictionary entry costs more than a gap.

SWEEP_THRESHOLDS = [15, 20, 25, 30]
EXPERIMENT_ALPHAS = [0.0, 0.5, 1.0]  # fan-out penalty strength (0 = production)

# A with_lexentry row's score, with the optional fan-out penalty on indirect
# paths. The pivot (lang, word) is parsed from source_detail ("en+:go" -> en, go);
# its fan-out toward the target language comes from the `fanout` temp table.
# specificity() is a registered Python function (sqlite3 may lack power()).
_ADJ_INDIRECT_SCORE = """
    w.score * specificity(coalesce(f.fanout, 1), :alpha)
"""
_FANOUT_JOIN = """
    LEFT JOIN fanout f
      ON f.pivot_lang  = rtrim(substr(w.source_detail, 1, instr(w.source_detail, ':') - 1), '+-')
     AND f.target_lang = w.to_lang
     AND f.pivot_word  = substr(w.source_detail, instr(w.source_detail, ':') + 1)
"""


def build_fanout(conn):
    """Pivot fan-out toward each target language: how many target words a word
    translates to. High fan-out == ambiguous "hub" pivot."""
    conn.execute("DROP TABLE IF EXISTS fanout")
    conn.execute(
        """
        CREATE TEMP TABLE fanout AS
        SELECT from_lang AS pivot_lang, to_lang AS target_lang,
               from_vocable AS pivot_word, count(DISTINCT to_vocable) AS fanout
        FROM all_trans GROUP BY from_lang, to_lang, from_vocable
        """
    )
    conn.execute("CREATE INDEX fo_idx ON fanout(pivot_lang, target_lang, pivot_word)")


def build_pred(conn, a, b, alpha):
    """Build temp table ``pred(from_vocable, to_vocable, score)``: each target's
    indirect-only score under the model variant (fan-out ``alpha``), summed over
    its pivot paths, best sense.

    This is exactly the held-out inference for a->b -- the indirect paths are
    ``a->pivot`` then ``pivot->b`` and never use the a->b direct edge -- so it
    serves two callers: the held-out recall counts here, and the precision gold
    (``precision_gold.py``), which scores its labelled gap-fills against the very
    same ``pred`` table so the two measurements use one scoring path."""
    conn.execute("DROP TABLE IF EXISTS pred")
    conn.execute(
        f"""
        CREATE TEMP TABLE pred AS
        WITH per_sense AS (
            SELECT w.from_vocable, w.to_vocable, sum(s) AS score
            FROM (
                SELECT w.from_vocable, w.to_vocable, w.lexentry, w.sense_num, w.sense,
                    {_ADJ_INDIRECT_SCORE} AS s
                FROM with_lexentry w {_FANOUT_JOIN}
                WHERE w.from_lang = :a AND w.to_lang = :b AND w.source = 'indirect'
            ) w
            GROUP BY w.from_vocable, w.to_vocable, w.lexentry, w.sense_num, w.sense
        )
        SELECT from_vocable, to_vocable, max(score) AS score
        FROM per_sense GROUP BY from_vocable, to_vocable
        """,
        dict(a=a, b=b, alpha=alpha),
    )
    conn.execute("CREATE INDEX pred_idx ON pred(from_vocable, to_vocable)")


def _counts(conn, a, b, alpha, threshold):
    """Held-out (tp, pred_n, gold_n) for one pair at a (fanout alpha, threshold).

    Combine is sum over a target's (fan-out-adjusted) pivot paths, best sense."""
    build_pred(conn, a, b, alpha)
    conn.execute("DROP TABLE IF EXISTS gold")
    conn.execute(
        "CREATE TEMP TABLE gold AS SELECT DISTINCT from_vocable, to_vocable "
        "FROM with_lexentry WHERE from_lang = ? AND to_lang = ? AND source = 'direct'",
        [a, b],
    )
    (gold_n,) = conn.execute("SELECT count(*) FROM gold").fetchone()
    (tp,) = conn.execute(
        "SELECT count(*) FROM pred JOIN gold USING (from_vocable, to_vocable) "
        "WHERE pred.score >= ?",
        [threshold],
    ).fetchone()
    (pred_n,) = conn.execute("SELECT count(*) FROM pred WHERE score >= ?", [threshold]).fetchone()
    return tp, pred_n, gold_n


def _fbeta(tp, pred_n, gold_n, beta):
    p = tp / pred_n if pred_n else 0.0
    r = tp / gold_n if gold_n else 0.0
    b2 = beta * beta
    f = (1 + b2) * p * r / (b2 * p + r) if (b2 * p + r) else 0.0
    return p, r, f


def _fbeta_pr(p, r, beta):
    """Fbeta straight from precision and recall (the combined objective combines a
    gold precision with a held-out recall, which come from different populations)."""
    b2 = beta * beta
    return (1 + b2) * p * r / (b2 * p + r) if (b2 * p + r) else 0.0


def _gold_counts(conn, a, b, rows, alpha, threshold):
    """Build ``pred`` for (a, b, alpha) and count the labelled gap-fills.
    Returns (correct_kept, incorrect_kept, base_correct, base_incorrect), where
    *kept* = the variant scores the row >= threshold, and *base* = the production
    (alpha=0, mined) score does -- i.e. what the baseline ships at this threshold.

    The mined-score baseline matters once the gold spans the sub-threshold band:
    a [15,20) row is correctly absent from the retention denominator at threshold
    20 (production never shipped it) but enters it at threshold 15. Since a fan-out
    penalty only lowers scores, a variant-kept correct row is always baseline-kept,
    so retention numerator = correct_kept.

    The gold is independent of the dbnary edges we infer from, so this is a real
    precision signal -- unlike the held-out harness, which counts every non-gold
    prediction as a false positive and so cannot tell a good gap-fill from a
    hallucination (scoring-improvement.md #1)."""
    build_pred(conn, a, b, alpha)
    kept = set(
        conn.execute(
            "SELECT from_vocable, to_vocable FROM pred WHERE score >= ?", [threshold]
        ).fetchall()
    )
    kc = ki = bc = bi = 0
    for fv, tv, label, score in rows:
        base = score >= threshold
        in_kept = (fv, tv) in kept
        if label == "correct":
            bc += base
            kc += in_kept
        elif label == "incorrect":
            bi += base
            ki += in_kept
    return kc, ki, bc, bi


def gold_report(conn, gold, alpha, threshold):
    """Precision and correct-retention on the labelled gap-fill gold for a variant.

    gold: ``{(a, b): [(from_vocable, to_vocable, label, mined_score)]}``.
      precision = labelled-correct kept / all labelled kept  (the FP rate we care
                  about: of the gap-fills the model ships, how many are real)
      retained  = labelled-correct kept / labelled-correct the baseline ships  (the
                  guardrail against the reverted decay, which dropped good gap-fills)
    Returns (precision, retained, n_kept, base_correct, per_pair_rows)."""
    KC = KI = BC = 0
    per = []
    for (a, b), rows in sorted(gold.items()):
        kc, ki, bc, bi = _gold_counts(conn, a, b, rows, alpha, threshold)
        KC += kc
        KI += ki
        BC += bc
        prec = kc / (kc + ki) if (kc + ki) else float("nan")
        ret = kc / bc if bc else float("nan")
        per.append([f"{a}-{b}", bc, bi, kc + ki, f"{prec:.3f}", f"{ret:.3f}"])
    P = KC / (KC + KI) if (KC + KI) else float("nan")
    R = KC / BC if BC else float("nan")
    return P, R, KC + KI, BC, per


def probe(conn, alpha, threshold):
    """Production-output probes (de->sv 'gehen'), like test_results.py: gå
    present with a sense scored >= threshold, åka absent from every trans_list."""
    rows = conn.execute(
        f"""
        SELECT lexentry, sense_num, sense, to_vocable, sum(s) AS s
        FROM (
            SELECT w.lexentry, w.sense_num, w.sense, w.to_vocable,
                w.score * CASE WHEN w.source = 'indirect'
                               THEN specificity(coalesce(f.fanout, 1), :alpha) ELSE 1 END AS s
            FROM with_lexentry w {_FANOUT_JOIN}
            WHERE w.from_lang = 'de' AND w.to_lang = 'sv' AND w.from_vocable = 'gehen'
        ) w
        GROUP BY lexentry, sense_num, sense, to_vocable
        """,
        dict(alpha=alpha),
    ).fetchall()
    groups = {}
    for lexentry, sense_num, sense, to_vocable, s in rows:
        groups.setdefault((lexentry, sense_num, sense), []).append((to_vocable, s))
    found_ga = False
    aka_ok = True
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


def report(conn, eval_pairs, alpha, threshold, beta, gold=None, per_pair=True):
    from tabulate import tabulate

    rows, sum_tp, sum_pred, sum_gold = [], 0, 0, 0
    for pair in eval_pairs:
        a, b = pair.split("-")
        tp, pred_n, gold_n = _counts(conn, a, b, alpha, threshold)
        p, r, f = _fbeta(tp, pred_n, gold_n, beta)
        _, _, f1 = _fbeta(tp, pred_n, gold_n, 1.0)
        rows.append([pair, gold_n, pred_n, tp, f"{p:.3f}", f"{r:.3f}", f"{f:.3f}", f"{f1:.3f}"])
        sum_tp += tp
        sum_pred += pred_n
        sum_gold += gold_n
    mp, mr, mf = _fbeta(sum_tp, sum_pred, sum_gold, beta)
    ga, aka = probe(conn, alpha, threshold)
    head = f"alpha={alpha} thr={threshold}"

    # The combined objective (scoring-improvement.md #2): held-out reconstruction
    # gives recall, the labelled gap-fill gold gives precision. Combine them.
    gp = gr = float("nan")
    gold_per = []
    if gold:
        gp, gr, _, _, gold_per = gold_report(conn, gold, alpha, threshold)
    comb = _fbeta_pr(gp, mr, beta) if gold else float("nan")

    if per_pair:
        rows.append(["MICRO", sum_gold, sum_pred, sum_tp,
                     f"{mp:.3f}", f"{mr:.3f}", f"{mf:.3f}", ""])
        print(f"\n=== {head} ===")
        print("held-out reconstruction (recall signal; P* counts every gap-fill as a FP, so it understates):")
        print(tabulate(rows, ["pair", "gold", "pred", "tp", "P*", "R", f"F{beta}", "F1"]))
        if gold:
            print("\nprecision gold (labelled inferred-only gap-fills the variant keeps):")
            print(tabulate(gold_per, ["pair", "ok", "bad", "kept", "P", "retain"]))
    probes = f"gå:{'P' if ga else 'F'} åka:{'P' if aka else 'F'}"
    if gold:
        print(f"  {head}  recall(held-out)={mr:.3f}  gold P={gp:.3f} retain={gr:.3f}"
              f"  combined F{beta}={comb:.3f}  probes[{probes}]")
        return comb, ga and aka
    print(f"  {head}  micro P*={mp:.3f} R={mr:.3f} F{beta}={mf:.3f}  (no precision gold)  probes[{probes}]")
    return mf, ga and aka


def evaluate(infer_db=None, eval_pairs=None, threshold=None,
             fanout_alpha=0.0, beta=EVAL_BETA, sweep=False, experiment=False, **kwargs):
    infer_db = infer_db or f"{os.environ.get('WIKDICT_DICT_DIR', 'dictionaries')}/infer.sqlite3"
    if not os.path.exists(infer_db):
        raise SystemExit(f"No {infer_db}; build it with `make infer` first.")
    eval_pairs = eval_pairs.split(",") if eval_pairs else DEFAULT_EVAL_PAIRS
    threshold = scoring.IS_GOOD_THRESHOLD if threshold is None else threshold

    with closing(sqlite3.connect(f"file:{infer_db}?mode=ro", uri=True)) as conn:
        # specificity(fanout, alpha) = fanout^(-alpha); alpha=0 -> 1 (no penalty).
        conn.create_function("specificity", 2,
                             lambda fanout, alpha: float(fanout) ** (-alpha))
        build_fanout(conn)
        import precision_gold

        gold = precision_gold.load_gold()
        if not gold:
            print("(no precision gold at src/tests/data/precision_gold.tsv; "
                  "reporting held-out recall only -- build it with `mine-gold` + labelling)")
        if experiment:
            print(f"Fan-out experiment ({len(eval_pairs)} pairs, beta={beta}, "
                  f"thr={threshold}). alpha=0 is the production model.\n")
            for alpha in EXPERIMENT_ALPHAS:
                report(conn, eval_pairs, alpha, threshold, beta, gold=gold, per_pair=False)
        elif sweep:
            if gold:
                print(f"(caveat: cross-threshold gold P is confounded -- the [{scoring.IS_GOOD_THRESHOLD}+) "
                      f"strata are hub-enriched (over-weighted for FPs) while `sub` "
                      f"[{precision_gold.SUB_FLOOR},{scoring.IS_GOOD_THRESHOLD}) is uniform, so a lower "
                      f"threshold's P is not comparable. Judge a threshold by the admitted "
                      f"stratum's own P; the gold cleanly A/Bs scoring *changes* at a fixed "
                      f"threshold, where enrichment cancels.)\n")
            for thr in SWEEP_THRESHOLDS:
                report(conn, eval_pairs, fanout_alpha, thr, beta, gold=gold, per_pair=False)
        else:
            report(conn, eval_pairs, fanout_alpha, threshold, beta, gold=gold)


def add_subparsers(subparsers):
    p = subparsers.add_parser(
        "evaluate", help="held-out precision/recall/Fbeta of the scoring model"
    )
    p.add_argument("--infer-db", dest="infer_db", default=None,
                   help="built infer.sqlite3 to read (default dictionaries/infer.sqlite3)")
    p.add_argument("--eval-pairs", dest="eval_pairs", default=None,
                   help="comma-separated from-to pairs to score")
    p.add_argument("--threshold", type=int, default=None)
    p.add_argument("--fanout-alpha", dest="fanout_alpha", type=float, default=0.0,
                   help="experimental polysemy penalty: specificity = fanout^(-alpha)")
    p.add_argument("--beta", type=float, default=EVAL_BETA,
                   help="Fbeta weight; <1 favours precision (default 0.5)")
    p.add_argument("--sweep", action="store_true", help="sweep the is_good threshold")
    p.add_argument("--experiment", action="store_true",
                   help="compare the production model vs fan-out (polysemy) variants")
    p.set_defaults(func=evaluate)
