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


class TestAggByScore(unittest.TestCase):
    def agg(self, *pairs):
        a = AggByScore()
        for trans, score in pairs:
            a.step(trans, score)
        return a.finalize()

    def test_empty(self):
        self.assertEqual(AggByScore().finalize(), "")

    def test_boundary_step(self):
        # The diversity gate raises the bar by AGG_SCORE_STEP per kept target
        # (0, then the step, ...). A target scored *exactly* at the bar is kept;
        # the first one below it stops the list.
        step = scoring.AGG_SCORE_STEP
        self.assertEqual(
            self.agg(("a", 100), ("b", step), ("c", step - 1)), "a | b"
        )


class TestRenderSql(unittest.TestCase):
    def test_no_leftover_placeholders(self):
        """infer.sql substitutes cleanly from scoring.py (guards new ${...})."""
        import infer

        sql = infer.render_sql()
        self.assertNotIn("${", sql)
        self.assertIn(f"{scoring.DIRECT_SCORE} AS score", sql)


if __name__ == "__main__":
    unittest.main()
