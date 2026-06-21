# vim: set fileencoding=utf-8 :
"""Miniature end-to-end test of the whole pipeline.

Loads a tiny hand-built de/en/sv TTL fixture into a temporary pyoxigraph store and
runs raw -> processed -> infer -> generic -> wdweb, then asserts on the outputs.
Everything is built into a temp dir via WIKDICT_DICT_DIR, so the real
``dictionaries/`` (notably the global infer.sqlite3) is never touched. Runs in a few
seconds with no pre-built database, so it works on a fresh checkout / in CI.
"""

import gzip
import os
import shutil
import sqlite3
import tempfile
import unittest

# All output paths resolve WIKDICT_DICT_DIR per call, so importing these before the
# env var is set is fine - it is read when the pipeline functions run.
import generic
import infer
import process
import wdweb
from sparql import run as sparql_run
from sparql import store

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

LANGS = ["de", "en", "sv", "nl"]
# The de/en/sv pairs plus the nl pairs that make the gehen->åka trap a real
# second pivot (de->nl->sv); nl-de supplies the backlink. See the nl fixture and
# test_translation_quality.
PAIRS = ["de-en", "en-de", "de-sv", "sv-de", "en-sv", "sv-en",
         "de-nl", "nl-de", "nl-sv"]


def _build_pipeline(ttl_dir):
    store.build_store(ttl_dir=ttl_dir)
    for lang in LANGS:
        sparql_run.do(lang=lang, only=None)
    for pair in PAIRS:
        sparql_run.do(lang=pair, only=None)
    for lang in LANGS:
        process.do(lang=lang, only=None, sql=None)
    for pair in PAIRS:
        process.do(lang=pair, only=None, sql=None)
    for pair in PAIRS:
        infer.do(lang=pair, sql=None)
    infer.infer()
    for pair in PAIRS:
        generic.do(lang=pair, sql=None, only=None)
    for lang in LANGS:
        wdweb.do(lang=lang, only=None, sql=None)
    for pair in PAIRS:
        wdweb.do(lang=pair, only=None, sql=None)


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wikdict-e2e-")
        cls.dict_dir = os.path.join(cls.tmp, "dictionaries")
        cls._prev_env = os.environ.get("WIKDICT_DICT_DIR")
        os.environ["WIKDICT_DICT_DIR"] = cls.dict_dir

        ttl_dir = os.path.join(cls.tmp, "ttl")
        os.makedirs(ttl_dir)
        for name in os.listdir(FIXTURES):
            if name.endswith(".ttl"):
                with open(os.path.join(FIXTURES, name), "rb") as src, gzip.open(
                    os.path.join(ttl_dir, name + ".gz"), "wb"
                ) as dst:
                    shutil.copyfileobj(src, dst)

        try:
            _build_pipeline(ttl_dir)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls._prev_env is None:
            os.environ.pop("WIKDICT_DICT_DIR", None)
        else:
            os.environ["WIKDICT_DICT_DIR"] = cls._prev_env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def db(self, rel_path):
        conn = sqlite3.connect(os.path.join(self.dict_dir, rel_path))
        self.addCleanup(conn.close)
        return conn

    def test_gender_and_inflection(self):
        """Single-language processing extracts gender and cleaned inflected forms."""
        conn = self.db("processed/de.sqlite3")
        (gender,) = conn.execute(
            "SELECT gender FROM entry WHERE written_rep = 'Haus'"
        ).fetchone()
        self.assertIn("neuter", gender)
        plurals = [
            r[0]
            for r in conn.execute("SELECT other_written FROM form WHERE number = 'Plural'")
        ]
        # "die Häuser" with the German article stripped by the inflection cleaner.
        self.assertIn("Häuser", plurals)

    def test_direct_translation(self):
        """A direct de->en edge survives as a high-scoring 'good' translation."""
        conn = self.db("generic/de-en.sqlite3")
        row = conn.execute(
            "SELECT trans_list, score, is_good FROM translation WHERE written_rep = 'Haus'"
        ).fetchone()
        self.assertIsNotNone(row)
        trans_list, score, is_good = row
        self.assertIn("house", trans_list)
        self.assertGreaterEqual(score, 20)
        self.assertTrue(is_good)

    def test_inferred_translation(self):
        """de->sv "Haus"->"hus" exists only via inference through the en pivot
        "house" (no direct edge in the fixture). A score below the direct weight
        (100) confirms it was inferred rather than copied."""
        conn = self.db("infer.sqlite3")
        row = conn.execute(
            "SELECT trans_list, score FROM infer_grouped "
            "WHERE from_lang = 'de' AND to_lang = 'sv' AND from_vocable = 'Haus'"
        ).fetchone()
        self.assertIsNotNone(row)
        trans_list, score = row
        self.assertIn("hus", trans_list)
        self.assertGreater(score, 0)
        self.assertLess(score, 100)

    def test_translation_quality(self):
        """Fixture-scale version of test_results.py's expect/dont_expect, and the
        regression guard for the diminishing-returns combine.

        de->sv "gehen" reaches "åka" only by inference through two polysemous
        motion-verb pivots (en "go", nl "gaan"), each contributing ~10. Under the
        old sum() combine they add to ~20 and "åka" would ship; the
        diminishing-returns combine (scoring.COMBINE_DECAY=0.5) keeps it ~15, below
        the AggByScore gate, so only the correct "gå" (which also has a direct
        edge) survives. Resetting COMBINE_DECAY to 1.0 makes this assertion fail.
        """
        conn = self.db("infer.sqlite3")
        rows = conn.execute(
            "SELECT trans_list, score FROM infer_grouped "
            "WHERE from_lang = 'de' AND to_lang = 'sv' AND from_vocable = 'gehen'"
        ).fetchall()
        self.assertTrue(rows)
        # expect: gå present in some sense with a good score
        self.assertTrue(any("gå" in tl and sc >= 20 for tl, sc in rows))
        # dont_expect: åka must not survive into any trans_list
        self.assertFalse(any("åka" in tl for tl, _ in rows))

    def test_wdweb_outputs(self):
        """The web format builds its translation table, FTS index and pair stats."""
        pair = self.db("wdweb/de-en.sqlite3")
        row = pair.execute(
            "SELECT trans_list FROM translation WHERE written_rep = 'Haus'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("house", row[0])

        matches = pair.execute(
            "SELECT written_rep FROM search_trans WHERE search_trans MATCH 'Haus'"
        ).fetchall()
        self.assertIn(("Haus",), matches)

        stats = self.db("wdweb/wikdict.sqlite3")
        row = stats.execute(
            "SELECT translations FROM lang_pair WHERE from_lang = 'de' AND to_lang = 'en'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertGreater(row[0], 0)


if __name__ == "__main__":
    unittest.main()
