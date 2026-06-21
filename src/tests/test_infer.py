# vim: set fileencoding=utf-8 :
import unittest
import sqlite3

import scoring
from infer import AggByScore


class TestInfer(unittest.TestCase):
    def test_entity(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.create_aggregate("agg_by_score", 2, AggByScore)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT agg_by_score(trans, score)
            FROM (
                SELECT 'Haus' AS trans, 30 AS score
                UNION ALL
                SELECT 'Hütte' AS trans, 2 AS score
                UNION ALL
                SELECT 'Wohnung' AS trans, 100 AS score
            )
        """
        )
        self.assertEqual(cur.fetchall(), [("Wohnung | Haus",)])


class TestRenderSql(unittest.TestCase):
    def test_no_leftover_placeholders(self):
        """infer.sql substitutes cleanly from scoring.py (guards new ${...})."""
        import infer

        sql = infer.render_sql()
        self.assertNotIn("${", sql)
        self.assertIn(f"{scoring.DIRECT_SCORE} AS score", sql)


def _combine(scores, decay):
    """Run the exact infer.sql combine expression over a list of path scores."""
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE p(score real)")
        conn.executemany("INSERT INTO p VALUES (?)", [(s,) for s in scores])
        (v,) = conn.execute(
            "SELECT max(score) + ? * (sum(score) - max(score)) FROM p", [decay]
        ).fetchone()
    return v


class TestCombineFormula(unittest.TestCase):
    """The diminishing-returns combine (scoring.COMBINE_DECAY) that fixes the
    de->sv 'gehen' -> 'åka' regression. åka is reached only by summing several
    weak motion-verb pivot paths; gå keeps its direct edge."""

    def test_decay_one_is_plain_sum(self):
        # decay=1.0 must reproduce the historical sum(score) exactly.
        self.assertEqual(_combine([10, 10], 1.0), 20)
        self.assertEqual(_combine([100, 10, 10], 1.0), 120)

    def test_diminishing_returns_demotes_hub_target(self):
        # gehen->åka: two pivots of 10. Summed (decay 1.0) it clears the
        # is_good threshold; with diminishing returns (0.5) it does not.
        self.assertGreaterEqual(_combine([10, 10], 1.0), scoring.IS_GOOD_THRESHOLD)
        self.assertLess(_combine([10, 10], 0.5), scoring.IS_GOOD_THRESHOLD)
        # gehen->gå: a direct edge (100) dominates and survives either way.
        self.assertGreaterEqual(_combine([100, 10, 10], 0.5), scoring.IS_GOOD_THRESHOLD)

    def test_aggregate_drops_demoted_target(self):
        # With the decay=0.5 combined scores (gå=110, åka=15), AggByScore keeps
        # only gå -- i.e. åka no longer ships in the trans_list.
        with sqlite3.connect(":memory:") as conn:
            conn.create_aggregate("agg_by_score", 2, AggByScore)
            (trans_list,) = conn.execute(
                """
                SELECT agg_by_score(trans, score) FROM (
                    SELECT 'gå' AS trans, 110 AS score
                    UNION ALL SELECT 'åka', 15
                )
                """
            ).fetchone()
        self.assertEqual(trans_list, "gå")


if __name__ == "__main__":
    unittest.main()
