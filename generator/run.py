#!/usr/bin/env python3
import os
import sqlite3
import argparse
import subprocess
import codecs
import re
import urllib.request, urllib.parse, urllib.error
import json
from itertools import groupby

from parse import html_parser, clean_wiki_syntax
from helper import make_for_langs, make_for_lang_permutations

BASE_PATH = os.path.dirname(os.path.realpath(__file__))


def search_query(from_lang, to_lang, search_term, **kwargs):
    conn = sqlite3.connect(
        'dictionaries/sqlite/prod/%s-%s.sqlite3'
        % (from_lang, to_lang))
    for r in conn.execute("""
                SELECT * FROM (
                    SELECT lexentry, written_rep, sense_list, trans_list
                    FROM (
                            SELECT DISTINCT lexentry
                            FROM search_trans
                            WHERE form MATCH ?
                        )
                        JOIN translation USING (lexentry)
                    ORDER BY translation.rowid
                )
                UNION ALL
                SELECT NULL, written_rep, NULL, trans_list
                FROM search_reverse_trans
                WHERE written_rep MATCH ?
            """, [search_term, search_term]):
        print('%-40s %-20s %-80s %s' % r)


def interactive(from_lang, to_lang, **kwargs):
    with open('/tmp/attach_dbs.sql', 'w') as f:
        f.write(attach_dbs(from_lang, to_lang))
        f.write('\n.read ' + BASE_PATH + '/views.sql\n')
        f.write('.headers on\n.mode column\n.load lib/spellfix1')
    subprocess.check_call(
        #'sqlite3 '
        '/usr/local/Cellar/sqlite/3.8.10.2/bin/sqlite3 '
        '-init /tmp/attach_dbs.sql dictionaries/sqlite/%s.sqlite3' % from_lang,
        shell=True)
    #p = subprocess.Popen(['sqlite3', '-interactive'], stdin=subprocess.PIPE)
    #p.communicate(script)


def attach_dbs(from_lang, to_lang):
    main_db_filename = 'dictionaries/sqlite/prod/wikdict.sqlite3'
    if not os.path.isfile(main_db_filename):
        conn = sqlite3.connect(main_db_filename)
        with open('main.sql') as f:
            conn.executescript(f.read())
    return """
        ATTACH DATABASE 'dictionaries/sqlite/{to_lang}.sqlite3' AS other;
        ATTACH DATABASE 'dictionaries/sqlite/{from_lang}-{to_lang}.sqlite3' AS lang_pair;
        ATTACH DATABASE 'dictionaries/sqlite/{to_lang}-{from_lang}.sqlite3' AS other_pair;
        ATTACH DATABASE 'dictionaries/sqlite/prod/{from_lang}-{to_lang}.sqlite3' AS prod;
        ATTACH DATABASE 'dictionaries/sqlite/prod/wikdict.sqlite3' AS wikdict;
        ATTACH DATABASE 'dictionaries/sqlite/prod/{from_lang}.sqlite3' AS prod_lang;
        ATTACH DATABASE 'dictionaries/sqlite/prod/{to_lang}.sqlite3' AS prod_other;
    """.format(from_lang=from_lang, to_lang=to_lang)


def make_typeahead_single(lang):
    conn = sqlite3.connect('dictionaries/sqlite/%s.sqlite3' % lang)
    apply_views(conn, 'single_views.sql')

    rows = conn.execute("""
        SELECT lower(substr(x, 1, 3)) AS prefix, x, rel_score
        FROM (
            SELECT substr(vocable, 5) AS x, rel_score
            FROM rel_importance
            WHERE lower(substr(vocable, 5)) IN (
                SELECT lower(written_rep) FROM entry
            )
        )
        ORDER BY 1, rel_score DESC
    """)

    # make prefix dir for this language
    path = os.path.expanduser('~/tools/typeahead2/%s' % lang)
    try:
        os.mkdir(path)
    except OSError:
        pass

    def save_typeahead(filename, prefix_rows):
        encoded_prefix = urllib.parse.quote_plus(filename)
        filename = path + '/' + encoded_prefix + '.json'
        with codecs.open(filename, 'w', 'utf8') as f:
            words = [r[1:] for r in prefix_rows]
            f.write(json.dumps(words))

    # save words to [prefix].txt
    #singles = []
    for prefix, prefix_rows in groupby(rows, lambda row: row[0]):
        if len(prefix) < 3:
            # print 'Skip short prefix %s' % prefix
            continue
        prefix_rows = list(prefix_rows)
        #if len(prefix_rows) =< 1:
        #    singles += prefix_rows
        #    continue
        save_typeahead(prefix.encode('utf8'), prefix_rows)
    #save_typeahead('_singles', singles)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='cmd')
    subparsers.required = True

    import sparql.run as sparql_run
    sparql_run.add_subparsers(subparsers)
    import process
    process.add_subparsers(subparsers)
    import wdweb
    wdweb.add_subparsers(subparsers)

    search = subparsers.add_parser('search')
    search.add_argument('from_lang')
    search.add_argument('to_lang')
    search.add_argument('search_term')
    search.set_defaults(func=search_query)

    complete_lang = subparsers.add_parser('complete_lang')
    complete_lang.add_argument('langs', nargs='+', metavar='lang')
    complete_lang.set_defaults(
        func=lambda langs, **kwargs: make_for_langs(
            [make_form, make_entry, make_importance, make_prod_single], langs)
    )

    complete_pair = subparsers.add_parser('complete_pair')
    complete_pair.add_argument('langs', nargs='+', metavar='lang')
    complete_pair.set_defaults(
        func=lambda langs, **kwargs: make_for_lang_permutations(
            [sparql_run.make_translation, make_prod_pair], langs)
    )

    inter = subparsers.add_parser('interactive')
    inter.add_argument('from_lang')
    inter.add_argument('to_lang')
    inter.set_defaults(func=interactive)

    typeahead = subparsers.add_parser('typeahead')
    typeahead.add_argument('langs', nargs='+', metavar='lang')
    typeahead.set_defaults(
        func=lambda lang, **kwargs: make_for_langs(
            [make_typeahead], lang)
    )

    args = parser.parse_args()
    args.func(**vars(args))
