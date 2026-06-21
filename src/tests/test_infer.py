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


if __name__ == "__main__":
    unittest.main()
