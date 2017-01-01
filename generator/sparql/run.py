#!/usr/bin/env python3

import argparse
import sqlite3

from . import queries as sparql
from helper import make_for_langs


class PartOfSpeechChooser:

    def __init__(self):
        self.pos_list = []

    def step(self, value):
        self.pos_list.append(value)

    def finalize(self):
        # TODO: proper choosing of pos
        return sorted(self.pos_list)[0]


def make_entry(lang, **kwargs):
    sparql.get_query('raw_entry', sparql.entry_query, lang=lang)
    conn = sqlite3.connect('dictionaries/sqlite/%s.sqlite3' % lang)
    conn.create_aggregate("choose_pos", 1, PartOfSpeechChooser)
    conn.executescript("""
        DROP TABLE IF EXISTS entry;
        CREATE TABLE entry AS
        SELECT lexentry, written_rep, choose_pos(part_of_speech) AS part_of_speech,
            CASE
                WHEN min(gender) == max(gender) THEN gender
                ELSE NULL
            END AS gender,
            pronun_list
        FROM raw_entry
        WHERE written_rep is NOT NULL
          AND written_rep != ''
        GROUP BY lexentry;
        -- remove bad entries with mutiple written_rep
        -- see https://forge.imag.fr/tracker/index.php?func=detail&aid=584&group_id=362&atid=1402
        --HAVING count(*) = 1;
        CREATE UNIQUE INDEX entry_pkey ON entry(lexentry);
    """)
    conn.commit()


def make_translation(from_lang, to_lang, **kwargs):
    sparql.get_query('translation', query, from_lang=from_lang, to_lang=to_lang)


def make_raw(lang, only=None, **kwargs):
    queries = {
            'form': sparql.form_query,
            'entry': sparql.entry_query,
            'importance': sparql.importance_query,
    }
    for name, q in queries.items():
        if not only or only == name:
            sparql.get_query(name, q, lang=lang)


def make_raw_pair(from_lang, to_lang,  only=None, **kwargs):
    trans_q_type = sparql.translation_query_type[from_lang]
    queries = {
            'translation': sparql.translation_query[trans_q_type]
    }
    for name, q in queries.items():
        if not only or only == name:
            sparql.get_query(name, q, from_lang=from_lang, to_lang=to_lang)


def add_subparsers(subparsers):
    raw = subparsers.add_parser(
        'raw', help='execute sparql queries and create raw db')
    raw.add_argument('lang')
    raw.set_defaults(func=make_raw)
    raw.add_argument('--only')

    raw_pair = subparsers.add_parser('raw_pair',
        help='execute sparql queries and create raw db for lang pair')
    raw_pair.add_argument('from_lang')
    raw_pair.add_argument('to_lang')
    raw_pair.set_defaults(func=make_raw_pair)
    raw_pair.add_argument('--only')
