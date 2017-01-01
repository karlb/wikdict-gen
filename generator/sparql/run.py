#!/usr/bin/env python3

import argparse
import sqlite3

from . import queries as sparql
from helper import make_for_langs


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
