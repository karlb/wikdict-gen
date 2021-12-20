# vim: set fileencoding=utf-8 :
import unittest
import sqlite3
from itertools import chain


class TestInferResults(unittest.TestCase):
    def test_dont_expect(self):
        dont_expect = [
            ("de", "sv", "gehen", "åka"),
        ]

        conn = sqlite3.connect("dictionaries/infer.sqlite3")
        cur = conn.cursor()
        where = " OR ".join(
            "(from_lang = ? AND to_lang = ? "
            "AND from_vocable = ? AND trans_list LIKE '%' || ? || '%')"
            for x in dont_expect
        )
        cur.execute(
            "SELECT * FROM infer_grouped WHERE " + where, list(chain(*dont_expect))
        )
        self.assertEqual(cur.fetchall(), [])

    def test_expect(self):
        expect = [
            ("de", "sv", "gehen", "gå"),
            # waiting for https://bitbucket.org/serasset/dbnary/issues/10/
            # ('de', 'en', 'nur', 'only'),
        ]

        conn = sqlite3.connect("dictionaries/infer.sqlite3")
        cur = conn.cursor()
        where = " OR ".join(
            "(from_lang = ? AND to_lang = ? "
            "AND from_vocable = ? AND trans_list LIKE '%' || ? || '%')"
            for x in expect
        )
        cur.execute(
            "SELECT from_lang, to_lang, from_vocable, trans_list, score "
            "FROM infer_grouped WHERE " + where,
            list(chain(*expect)),
        )
        found = cur.fetchall()

        def best_match(ex):
            matches = [f for f in found if f[:3] == ex[:3] and ex[3] in f[3]]
            if not matches:
                return None
            return sorted(matches, key=lambda f: -f[4])[0]

        missing = []
        for ex in expect:
            match = best_match(ex)
            if not match:
                missing.append([ex, "missing"])
            score = match[4]
            if score < 20:
                missing.append([ex, "too low score: {}".format(score)])

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
