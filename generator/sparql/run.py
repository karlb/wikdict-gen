#!/usr/bin/env python3

from . import queries as sparql


def make_translation(from_lang, to_lang, **kwargs):
    sparql.get_query('translation', query, from_lang=from_lang, to_lang=to_lang)


def make_raw(lang, only):
    queries = {
            'form': sparql.form_query,
            'entry': sparql.entry_query,
            'importance': sparql.importance_query,
    }
    for name, q in queries.items():
        if not only or only == name:
            sparql.get_query(name, q, lang=lang)


def make_raw_pair(from_lang, to_lang, only):
    trans_q_type = sparql.translation_query_type[from_lang]
    queries = {
            'translation': sparql.translation_query[trans_q_type]
    }
    for name, q in queries.items():
        if not only or only == name:
            sparql.get_query(name, q, from_lang=from_lang, to_lang=to_lang)


def do(lang, only, **kwargs):
    if '-' not in lang:
        make_raw(lang, only)
    else:
        make_raw_pair(*lang.split('-'), only=only)


def add_subparsers(subparsers):
    raw = subparsers.add_parser(
        'raw', help='execute sparql queries and create raw db')
    raw.add_argument('lang')
    raw.set_defaults(func=do)
    raw.add_argument('--only')
