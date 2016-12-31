#!/usr/bin/env python3

import argparse
import sqlite3

from . import queries as sparql
from helper import make_for_langs


def make_form(lang, **kwargs):
    sparql.get_query('form', sparql.form_query, lang=lang)


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
    query = sparql.translation_query[sparql.translation_query_type[from_lang]]
    sparql.get_query('translation', query, from_lang=from_lang, to_lang=to_lang)


def make_importance(lang, **kwargs):
    sparql.get_query('importance', sparql.importance_query, lang=lang)


def add_subparsers(subparsers):
    form = subparsers.add_parser(
        'form', help='lemon:otherForm entries for LexicalEntries')
    form.add_argument('lang')
    form.set_defaults(func=make_form)

    entry = subparsers.add_parser('entry', help='lemon:LexicalEntry entries')
    entry.add_argument('lang')
    entry.set_defaults(func=make_entry)

    translation = subparsers.add_parser('translation')
    translation.add_argument('from_lang')
    translation.add_argument('to_lang')
    translation.set_defaults(func=make_translation)

    importance = subparsers.add_parser('importance')
    importance.add_argument('langs', nargs='+', metavar='lang')
    importance.set_defaults(
        func=lambda langs, **kwargs: make_for_langs(
            [make_importance], langs)
    )
