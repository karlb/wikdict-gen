#!venv/bin/python
import os
import argparse
import subprocess
import sqlite3

BASE_PATH = os.path.dirname(os.path.realpath(__file__))


def search_query(from_lang, to_lang, search_term, **kwargs):
    conn = sqlite3.connect(
        'dictionaries/wdweb/%s-%s.sqlite3'
        % (from_lang, to_lang))
    for r in conn.execute("""
                SELECT lexentry, written_rep, sense_list, trans_list
                FROM (
                        SELECT DISTINCT written_rep
                        FROM search_trans
                        WHERE form MATCH :term
                    )
                    JOIN translation USING (written_rep)
                ORDER BY
                    lower(written_rep) LIKE '%'|| lower(:term) ||'%' DESC, length(written_rep),
                    lexentry, coalesce(min_sense_num, '99'), importance * translation_score DESC
                LIMIT 100
            """, dict(term=search_term)):
        print('%-40s %-20s %-80s %s' % r)


def attach_dbs(from_lang, to_lang):
    main_db_filename = 'dictionaries/wdweb/wikdict.sqlite3'
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


if __name__ == '__main__':
    sqlite3.enable_callback_tracebacks(True) 

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='cmd')
    subparsers.required = True

    import sparql.run as sparql_run
    sparql_run.add_subparsers(subparsers)
    import process
    process.add_subparsers(subparsers)
    import wdweb
    wdweb.add_subparsers(subparsers)
    import infer
    infer.add_subparsers(subparsers)
    import generic
    generic.add_subparsers(subparsers)

    search = subparsers.add_parser('search')
    search.add_argument('from_lang')
    search.add_argument('to_lang')
    search.add_argument('search_term')
    search.set_defaults(func=search_query)

    args = parser.parse_args()
    args.func(**vars(args))
