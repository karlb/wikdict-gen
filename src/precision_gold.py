"""Precision gold for the translation-scoring model.

The held-out harness in ``evaluate.py`` measures *recall* (can inference rebuild a
pair's hidden direct edges?) but is blind to precision: every non-gold prediction
counts as a false positive, so it cannot tell a good gap-fill from a hallucination
(scoring-improvement.md #1). The translations inference *exists* to produce are the
ones with no direct edge -- the gap-fills -- and for those there was no ground
truth. This module builds the missing measurement.

A precision gold must be independent of the dbnary translation edges we infer from
(any of our own Wiktionary signals is either absent for a true gap or already feeds
the inference, so it would be circular). The gold therefore comes from an *outside*
judge: an LLM asked "is ``a:X -> b:Y`` a correct translation?", hand-spot-checked.
The judgments are frozen into ``src/tests/data/precision_gold.tsv`` (checked in --
relabelling needs model access, so it is a persistent artifact, not regenerated
each run).

Two halves:
  - ``mine_candidates`` deterministically samples inferred-only ``is_good``
    gap-fills from a built ``infer.sqlite3``, stratified to enrich for the
    suspected false-positive region: near the keep threshold and reached only
    through high-fan-out "hub" pivots -- the ``gehen -> åka`` mechanism, where one
    ambiguous pivot ("go" = walk *and* travel) is replicated across languages.
    ``mine-gold`` writes these as an unlabelled TSV to hand to the judge.
  - ``load_gold`` reads the labelled TSV back; ``evaluate.py`` scores each labelled
    gap-fill against a model variant's recomputed ``pred`` table and reports
    precision and how many labelled-correct gap-fills the variant retains -- the
    precision half of the combined objective.

Mining and labelling are decoupled on purpose: mining is cheap and reproducible,
labelling is the expensive part that must be reused.
"""

import csv
import os
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from random import Random

import scoring

# Pairs the gold covers: all six evaluate.DEFAULT_EVAL_PAIRS (so precision and
# held-out recall measure the same set) plus the flagship de-en. The judge is
# reliable on these (de/en/fr/sv/it); de-sv carries the åka mechanism.
GOLD_PAIRS = ["de-en", "de-fr", "de-sv", "fr-it", "sv-de", "fr-de", "en-sv"]

GOLD_PATH = os.path.join(os.path.dirname(__file__), "tests", "data", "precision_gold.tsv")

# Stratified sample sizes per pair (see mine_candidates). hub/near/high sit at and
# above the is_good keep threshold. The `sub` stratum sampled the just-below band
# to A/B a *lower* threshold (the --sweep blind spot); its uniform [15,20) sample
# measured ~92% correct, which is what justified lowering IS_GOOD_THRESHOLD 20 -> 15.
# Now that the keep threshold *is* SUB_FLOOR, `sub` is empty for fresh mining and
# its frozen rows score the model as ordinary kept gap-fills; drop SUB_FLOOR and
# re-mine to probe an even lower threshold.
#   hub  -- near-threshold, every pivot a high-fan-out "hub" (likely false pos.)
#   near -- the rest of the near-threshold band (mixed; the real precision test)
#   high -- score >= HIGH_CUTOFF (mostly correct; anchors the corroboration thesis)
#   sub  -- [SUB_FLOOR, is_good): below the keep cut (empty once SUB_FLOOR == keep)
N_HUB, N_NEAR, N_HIGH, N_SUB = 35, 30, 15, 20
NEAR_CUTOFF = 45  # score < this is the "at risk" band
HIGH_CUTOFF = 60  # score >= this is the high-corroboration anchor
SUB_FLOOR = 15  # mine down to here; [SUB_FLOOR, is_good) is the sub stratum
SAMPLE_SEED = 20260621  # deterministic mining (no Date/random nondeterminism)

FIELDS = [
    "from_lang", "to_lang", "from_vocable", "to_vocable",
    "score", "min_fanout", "max_fanout", "n_paths", "stratum", "pivots",
    "label", "confidence", "note",
]
LABELS = ("correct", "incorrect", "unsure")


def _field(row, name):
    """A stripped TSV cell, tolerant of a missing key or an empty value."""
    return (row.get(name) or "").strip()


def _candidate_rows(conn, a, b, threshold):
    """All inferred-only ``is_good`` gap-fills for a->b with fan-out stats.

    Inferred-only = the variant's indirect-only score (``pred``, built at the
    production alpha=0) is >= threshold and there is no a->b direct edge. Fan-out
    of each contributing pivot toward the target is joined from the ``fanout``
    temp table; min over a candidate's pivots is high when *every* pivot is an
    ambiguous hub (the åka signature)."""
    import evaluate

    evaluate.build_pred(conn, a, b, 0.0)
    conn.execute("DROP TABLE IF EXISTS cand")
    conn.execute(
        """
        CREATE TEMP TABLE cand AS
        SELECT p.from_vocable, p.to_vocable, p.score
        FROM pred p
        WHERE p.score >= :thr
          AND NOT EXISTS (
              SELECT 1 FROM with_lexentry d
              WHERE d.from_lang = :a AND d.to_lang = :b AND d.source = 'direct'
                AND d.from_vocable = p.from_vocable AND d.to_vocable = p.to_vocable
          )
        """,
        dict(a=a, b=b, thr=threshold),
    )
    conn.execute("CREATE INDEX cand_idx ON cand(from_vocable, to_vocable)")
    rows = conn.execute(
        f"""
        SELECT c.from_vocable, c.to_vocable, c.score,
               min(coalesce(f.fanout, 1)) AS min_fanout,
               max(coalesce(f.fanout, 1)) AS max_fanout,
               count(*) AS n_paths,
               group_concat(DISTINCT w.source_detail) AS pivots
        FROM cand c
        JOIN with_lexentry w
          ON w.from_lang = :a AND w.to_lang = :b AND w.source = 'indirect'
         AND w.from_vocable = c.from_vocable AND w.to_vocable = c.to_vocable
        {evaluate._FANOUT_JOIN}
        GROUP BY c.from_vocable, c.to_vocable, c.score
        """,
        dict(a=a, b=b),
    ).fetchall()
    return rows


def mine_candidates(conn, pairs=None):
    """Deterministically sample inferred-only gap-fills across pairs, stratified
    to enrich for likely false positives. Returns a list of dicts ready to label.

    The partition boundary is the is_good keep threshold, so the hub/near/high
    strata are independent of SUB_FLOOR -- lowering the mining floor only *adds*
    the sub stratum, leaving the others byte-for-byte reproducible (existing labels
    can be reused by key). The fan-out temp table must already be built
    (evaluate.build_fanout)."""
    pairs = pairs or GOLD_PAIRS
    keep = scoring.IS_GOOD_THRESHOLD
    out = []
    for pair in pairs:
        a, b = pair.split("-")
        rows = _candidate_rows(conn, a, b, SUB_FLOOR)
        near = [r for r in rows if keep <= r[2] < NEAR_CUTOFF]
        high = [r for r in rows if r[2] >= HIGH_CUTOFF]
        sub = [r for r in rows if SUB_FLOOR <= r[2] < keep]
        # Hub = near-threshold candidates whose *least* ambiguous pivot is still a
        # big hub. Rank by min_fanout desc and take the top N_HUB.
        near_sorted = sorted(near, key=lambda r: (-r[3], r[0], r[1]))
        hub = near_sorted[:N_HUB]
        hub_keys = {(r[0], r[1]) for r in hub}
        rest = [r for r in near if (r[0], r[1]) not in hub_keys]
        near_sample = Random(f"{SAMPLE_SEED}-{pair}").sample(rest, min(N_NEAR, len(rest)))
        high_sample = Random(f"{SAMPLE_SEED}-{pair}-high").sample(high, min(N_HIGH, len(high)))
        sub_sample = Random(f"{SAMPLE_SEED}-{pair}-sub").sample(sub, min(N_SUB, len(sub)))
        for stratum, sample in (
            ("hub", hub), ("near", near_sample), ("high", high_sample), ("sub", sub_sample)
        ):
            for fv, tv, score, min_fo, max_fo, n_paths, pivots in sample:
                out.append(dict(
                    from_lang=a, to_lang=b, from_vocable=fv, to_vocable=tv,
                    score=round(score, 1), min_fanout=min_fo, max_fanout=max_fo,
                    n_paths=n_paths, stratum=stratum, pivots=pivots or "",
                    label="", confidence="", note="",
                ))
    return out


def write_tsv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def load_gold(path=GOLD_PATH):
    """Read the labelled gold. Returns
    ``{(from_lang, to_lang): [(fv, tv, label, mined_score)]}`` over only the rows
    with a usable correct/incorrect label. ``mined_score`` is the production
    (alpha=0) score the row was sampled at; the harness uses it as the retention
    baseline so the sub-threshold band doesn't look dropped at a high threshold.
    Returns ``{}`` if the gold file is absent (so the harness still runs before the
    gold is built)."""
    if not os.path.exists(path):
        return {}
    by_pair = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            label = _field(r, "label")
            if label not in ("correct", "incorrect"):
                continue
            key = (r["from_lang"], r["to_lang"])
            by_pair.setdefault(key, []).append(
                (r["from_vocable"], r["to_vocable"], label, float(r["score"]))
            )
    return by_pair


def confirmed_bad(path=GOLD_PATH, high_only=True):
    """The (from_lang, to_lang, from_vocable, to_vocable) tuples labelled
    'incorrect' -- the known-false-positive list (testing.md). With ``high_only``
    (the default), restrict to the unanimous high-confidence judgments, which are
    the unambiguous sense-leaks fit to serve as regression guards once a precision
    fix removes them; the med-confidence ones still feed the precision metric but
    are too borderline to assert on."""
    if not os.path.exists(path):
        return []
    bad = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if _field(r, "label") != "incorrect":
                continue
            if high_only and _field(r, "confidence") != "high":
                continue
            bad.append((r["from_lang"], r["to_lang"], r["from_vocable"], r["to_vocable"]))
    return bad


def mine(infer_db=None, out=None, pairs=None, **kwargs):
    import evaluate

    infer_db = infer_db or f"{os.environ.get('WIKDICT_DICT_DIR', 'dictionaries')}/infer.sqlite3"
    if not os.path.exists(infer_db):
        raise SystemExit(f"No {infer_db}; build it with `make infer` first.")
    pairs = pairs.split(",") if pairs else GOLD_PAIRS
    with closing(sqlite3.connect(f"file:{infer_db}?mode=ro", uri=True)) as conn:
        conn.create_function("specificity", 2, lambda fanout, alpha: float(fanout) ** (-alpha))
        evaluate.build_fanout(conn)
        rows = mine_candidates(conn, pairs)
    if out:
        write_tsv(rows, out)
        strata = Counter(r["stratum"] for r in rows)
        print(f"Wrote {len(rows)} candidates to {out}: {dict(strata)}")
    else:
        w = csv.DictWriter(sys.stdout, fieldnames=FIELDS, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def add_subparsers(subparsers):
    p = subparsers.add_parser(
        "mine-gold", help="sample inferred-only gap-fills to label for the precision gold"
    )
    p.add_argument("--infer-db", dest="infer_db", default=None)
    p.add_argument("--out", default=None, help="write TSV here (default: stdout)")
    p.add_argument("--pairs", default=None, help="comma-separated from-to pairs (default the gold pairs)")
    p.set_defaults(func=mine)
