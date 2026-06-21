# vim: set fileencoding=utf-8 :
"""Unit tests for the precision-gold harness (precision_gold.py + the gold metric
in evaluate.py).

These don't need the 48 GB ``infer.sqlite3``: the scoring math is exercised on a
hand-built in-memory ``with_lexentry`` so the test runs in milliseconds on a fresh
checkout. The scenario is the one the gold exists to catch -- a correct gap-fill
reached through specific pivots and a false positive reached through one ambiguous
high-fan-out "hub" pivot -- and asserts that a fan-out penalty lifts gold precision
while retaining the correct gap-fill.
"""
import os
import sqlite3
import tempfile
import unittest

import evaluate
import precision_gold

WL_COLS = (
    "from_lang", "to_lang", "source", "source_detail",
    "from_vocable", "to_vocable", "lexentry", "sense_num", "sense", "score",
)


def _scenario_conn():
    """de->en with two inferred gap-fills:
      good <- two specific pivots (fan-out 1 each), score 24
      bad  <- one ambiguous hub pivot (fan-out 100), score 25
    """
    conn = sqlite3.connect(":memory:")
    conn.create_function("specificity", 2, lambda fanout, alpha: float(fanout) ** (-alpha))
    conn.execute(
        "CREATE TABLE with_lexentry (%s)" % ", ".join(WL_COLS)
    )
    rows = [
        ("de", "en", "indirect", "fr+:bon", "A", "good", "L1", "01", "s1", 12),
        ("de", "en", "indirect", "es+:bueno", "A", "good", "L1", "01", "s1", 12),
        ("de", "en", "indirect", "it+:hub", "A", "bad", "L1", "01", "s1", 25),
    ]
    conn.executemany(
        "INSERT INTO with_lexentry VALUES (%s)" % ", ".join(["?"] * len(WL_COLS)), rows
    )
    conn.execute("CREATE TABLE fanout (pivot_lang, target_lang, pivot_word, fanout)")
    conn.executemany(
        "INSERT INTO fanout VALUES (?,?,?,?)",
        [("fr", "en", "bon", 1), ("es", "en", "bueno", 1), ("it", "en", "hub", 100)],
    )
    return conn


class TestGoldMetric(unittest.TestCase):
    def test_build_pred_sums_paths(self):
        conn = _scenario_conn()
        evaluate.build_pred(conn, "de", "en", 0.0)
        scores = dict(
            (fv + "/" + tv, round(s, 1))
            for fv, tv, s in conn.execute("SELECT from_vocable, to_vocable, score FROM pred")
        )
        self.assertEqual(scores["A/good"], 24.0)  # 12 + 12, corroborating pivots sum
        self.assertEqual(scores["A/bad"], 25.0)

    def test_fanout_penalty_lifts_precision(self):
        conn = _scenario_conn()
        gold = {("de", "en"): [("A", "good", "correct"), ("A", "bad", "incorrect")]}

        # Production model: both ship, so precision is only 0.5; nothing is dropped.
        p, retain, kept, n_correct, _ = evaluate.gold_report(conn, gold, alpha=0.0, threshold=20)
        self.assertAlmostEqual(p, 0.5)
        self.assertAlmostEqual(retain, 1.0)
        self.assertEqual(kept, 2)

        # A fan-out penalty crushes the hub-pivot FP (25 * 100**-0.5 = 2.5) below the
        # threshold while leaving the specific-pivot gap-fill (fan-out 1) untouched.
        p, retain, kept, n_correct, _ = evaluate.gold_report(conn, gold, alpha=0.5, threshold=20)
        self.assertAlmostEqual(p, 1.0)
        self.assertAlmostEqual(retain, 1.0)
        self.assertEqual(kept, 1)


class TestGoldIO(unittest.TestCase):
    def test_load_gold_and_confirmed_bad(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "gold.tsv")
            with open(path, "w") as f:
                f.write("\t".join(precision_gold.FIELDS) + "\n")
                cols = {c: "" for c in precision_gold.FIELDS}
                def row(**kw):
                    r = dict(cols, **kw)
                    return "\t".join(r[c] for c in precision_gold.FIELDS) + "\n"
                f.write(row(from_lang="de", to_lang="en", from_vocable="Wahrheit",
                            to_vocable="fact", label="incorrect", confidence="high"))
                f.write(row(from_lang="de", to_lang="en", from_vocable="nehmen",
                            to_vocable="grasp", label="incorrect", confidence="med"))
                f.write(row(from_lang="de", to_lang="en", from_vocable="Haus",
                            to_vocable="house", label="correct", confidence="high"))
                f.write(row(from_lang="fr", to_lang="it", from_vocable="nickel",
                            to_vocable="nickelio", label="unsure", confidence="low"))

            gold = precision_gold.load_gold(path)
            # unsure rows are dropped; correct + incorrect kept, keyed by pair
            self.assertEqual(set(gold), {("de", "en")})
            labels = sorted(l for _, _, l in gold[("de", "en")])
            self.assertEqual(labels, ["correct", "incorrect", "incorrect"])

            # high_only guards are the unambiguous sense-leaks only
            self.assertEqual(
                precision_gold.confirmed_bad(path),
                [("de", "en", "Wahrheit", "fact")],
            )
            self.assertEqual(len(precision_gold.confirmed_bad(path, high_only=False)), 2)


if __name__ == "__main__":
    unittest.main()
