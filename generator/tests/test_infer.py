# vim: set fileencoding=utf-8 :
import unittest
import sqlite3

from infer import AggByScore


class TestInfer(unittest.TestCase):

    def test_entity(self):
        conn = sqlite3.connect(':memory:')
        conn.create_aggregate("agg_by_score", 2, AggByScore)
        cur = conn.cursor()
        cur.execute("""
            SELECT agg_by_score(trans, score)
            FROM (
                SELECT 'Haus' AS trans, 30 AS score
                UNION ALL
                SELECT 'Hütte' AS trans, 2 AS score
                UNION ALL
                SELECT 'Wohnung' AS trans, 100 AS score
            )
        """)
        self.assertEqual(
            cur.fetchall(),
            [('Wohnung | Haus', )]
        )


if __name__ == '__main__':
    unittest.main()
