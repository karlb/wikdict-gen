#!/usr/bin/env python3

import sqlite3

from . import queries as sparql
from . import store


def make_raw(lang, only):
    queries = {
        "form": sparql.form_query,
        "entry": sparql.basic_entry_query,
        "pos": sparql.basic_entry_pos_query,
        "gender": sparql.basic_entry_gender_query,
        "pronun": sparql.basic_entry_pronun_query,
        "importance": sparql.importance_query,
        "nym": sparql.nym_query,
    }
    reader = store.open_reader()
    for name, q in queries.items():
        if not only or only == name:
            sparql.get_query(reader, name, q, lang=lang)


def make_raw_pair(from_lang, to_lang, only):
    queries = {
        # Two sense-linking mechanisms; dbnary uses one or the other per edition
        # (see notes/suggestions/bugs.md #6). Extract both and merge below: the
        # gloss-senseNumber join is empty for still-sense-linked editions (pl), the
        # direct sense link is empty for migrated ones (fr/de).
        "translation_sense": sparql.translation_query["sense"],
        "translation_sense_direct": sparql.translation_query["sense_direct"],
        "translation_gloss": sparql.translation_query["gloss"],
    }
    reader = store.open_reader()
    for name, q in queries.items():
        if not only or only == name:
            sparql.get_query(reader, name, q, from_lang=from_lang, to_lang=to_lang)

    conn = sqlite3.connect(f"dictionaries/raw/{from_lang}-{to_lang}.sqlite3")
    conn.executescript(
        """
        -- Fold the direct-link sense rows into translation_sense (dedup): the
        -- gloss-join is empty for still-sense-linked editions (e.g. pl), the direct
        -- link is empty for migrated ones (e.g. fr/de); together they cover both.
        INSERT INTO translation_sense
        SELECT d.* FROM translation_sense_direct d
        WHERE NOT EXISTS (
            SELECT 1 FROM translation_sense s
            WHERE (s.lexentry, s.trans, s.sense_num) = (d.lexentry, d.trans, d.sense_num)
        );
        DROP TABLE translation_sense_direct;

        CREATE INDEX translation_sense_idx ON translation_sense(lexentry, trans);
        DROP TABLE IF EXISTS translation;

        CREATE TABLE translation AS
        SELECT * FROM translation_sense
        UNION ALL
        SELECT g.*
        FROM translation_gloss g
        WHERE NOT EXISTS (
            SELECT 1 FROM translation_sense s
            WHERE (s.lexentry, s.trans) = (g.lexentry, g.trans)
        );
        """
    )


def do(lang, only, **kwargs):
    if "-" not in lang:
        make_raw(lang, only)
    else:
        make_raw_pair(*lang.split("-"), only=only)


def do_load_store(**kwargs):
    store.build_store()


def add_subparsers(subparsers):
    raw = subparsers.add_parser("raw", help="execute sparql queries and create raw db")
    raw.add_argument("lang")
    raw.set_defaults(func=do)
    raw.add_argument("--only")

    load_store = subparsers.add_parser(
        "load-store", help="bulk-load the dbnary TTL dumps into the pyoxigraph store"
    )
    load_store.set_defaults(func=do_load_store)
