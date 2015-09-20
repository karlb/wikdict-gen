#!/usr/bin/env python
import os
import urllib2
from urllib import urlencode
import csv
import sqlite3
import re
import argparse
import codecs
import subprocess
from itertools import permutations

namespace_re = re.compile(r'^(?:http://kaiko.getalp.org/dbnary/|http://.*#)')
fr_sense_re = re.compile(r'^(.*?)[.]?\s*(?:\(\d+\)|\|\d+)?:?$')
sense_num_re = re.compile(r'(\d+)(\w)?')

VIEW_FILENAME = os.path.dirname(os.path.realpath(__file__)) + '/views.sql'

from languages import language_codes3

translation_query_type = {
    'de': 'sense',
    'en': 'gloss',
    'fr': 'gloss',
    'pl': 'sense',
    'sv': 'gloss',
    'es': 'sense',
    'pt': 'gloss',
    'fi': 'sense',
    'el': 'sense',
    'ru': 'sense',
    'tr': 'sense',
}

form_query = """
    SELECT ?lexentry ?other_written ?case ?number ?inflection ?pos
    WHERE {
        ?lexentry lemon:canonicalForm ?canonical_form ;
                lemon:otherForm ?other_form ;
                dcterms:language lexvo:%(lang3)s .
        ?canonical_form lemon:writtenRep ?canonical_written .

        ?other_form lemon:writtenRep ?other_written .
        OPTIONAL { ?other_form olia:hasCase ?case }
        OPTIONAL { ?other_form olia:hasNumber ?number }
        OPTIONAL { ?other_form olia:hasInflectionType ?inflection }

        OPTIONAL { ?lexentry lexinfo:partOfSpeech ?pos }
    }
"""


entry_query = """
    SELECT ?lexentry ?written_rep ?part_of_speech ?gender ?pronun_list
    WHERE {
        ?lexform lemon:writtenRep ?written_rep .
        ?lexentry lemon:canonicalForm ?lexform ;
                  dcterms:language lexvo:%(lang3)s .

        OPTIONAL { ?lexentry lexinfo:partOfSpeech ?part_of_speech }
        OPTIONAL { ?lexform lexinfo:gender ?gender }
        OPTIONAL {
            SELECT ?lexform, group_concat(?pronun, ' | ') AS ?pronun_list
            WHERE {
                ?lexform lexinfo:pronunciation ?pronun .
            }
        }

        #FILTER (str(?written_rep) = 'Haus')  # for tests
    }
"""


translation_query = {
    'sense': """
        SELECT ?lexentry ?sense_num ?def_value AS ?sense
            ?trans AS ?trans_entity
            ?written_trans AS ?trans
        WHERE {
            ?lexentry lemon:canonicalForm ?lexform ;
                      dcterms:language lexvo:%(from_lang3)s ;
                      lemon:sense ?sense .

            ?sense lemon:definition ?def ;
                   dbnary:senseNumber ?sense_num .
            ?def lemon:value ?def_value .

            ?trans dbnary:isTranslationOf ?sense ;
                dbnary:targetLanguage lexvo:%(to_lang3)s ;
                dbnary:writtenForm ?written_trans .
            FILTER (str(?written_trans) != '')

            #FILTER (str(?lexentry) = 'http://kaiko.getalp.org/dbnary/deu/Haus__Substantiv__1')  # for tests
        }
    """,
    'gloss': """
        SELECT ?lexentry '' AS ?sense_num ?gloss AS ?sense
            ?trans AS ?trans_entity
            ?written_trans AS ?trans
        WHERE {
            ?lexentry lemon:canonicalForm ?lexform ;
                      dcterms:language lexvo:%(from_lang3)s .

            ?trans dbnary:isTranslationOf ?lexentry ;
                   dbnary:targetLanguage lexvo:%(to_lang3)s ;
                   dbnary:writtenForm ?written_trans .

            OPTIONAL {?trans dbnary:gloss ?gloss }

          #  FILTER (str(?lexentry) = 'http://kaiko.getalp.org/dbnary/fra/lire__verb__1')  # for tests
        }
    """
}


def make_url(query, **fmt_args):
    assert fmt_args['limit'] <= 1048576, 'Virtuoso does not support more than 1048576 results'
    #server = 'http://kaiko.getalp.org'
    server = 'http://localhost:8890'
    query = """
        SELECT *
        WHERE {
            %s
            ORDER BY 1
        }
        OFFSET %%(offset)s
        LIMIT %%(limit)s
    """ % (query)
    for key, val in fmt_args.items():
        if key.endswith('lang'):
            fmt_args[key + '3'] = language_codes3[val]
    url = server + '/sparql?' + urlencode({
        'default-graph-uri': '',
        'query': query % fmt_args,
        'format': 'text/csv',
        'timeout': 0,
    })
    #print query % fmt_args
    return url


def normalize_sense_num(c):
    match = sense_num_re.match(c)
    assert match
    normalized_sense_num = '{:02d}'.format(int(match.group(1)))
    if match.group(2):
        normalized_sense_num += match.group(2)
    return normalized_sense_num


def get_query(table_name, query, **kwargs):
    if 'lang' in kwargs:
        lang = kwargs['lang']
        db_name = lang
    else:
        lang = kwargs['from_lang']
        kwargs['lang'] = lang
        db_name = '{}-{}'.format(kwargs['from_lang'], kwargs['to_lang'])

    print 'Executing SPARQL query'
    offset = 0
    joined_result = []
    limit = int(1e6)
    while True:
        url = make_url(query, limit=limit, offset=offset, **kwargs)
        try:
            response = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            print e.read()
            raise
        reader = csv.reader(response)
        cols = next(reader)
        result = list(reader)
        joined_result += result
        if len(result) < limit:
            break
        else:
            offset += limit
            print '.'

    conn = sqlite3.connect('dictionaries/sqlite/%s.sqlite3' % db_name)
    conn.execute("DROP TABLE IF EXISTS %s" % table_name)
    conn.execute("CREATE TABLE %s (%s)" % (
            table_name,
            ', '.join('"%s" text' % c for c in cols)
        )
    )

    def postprocess_cell(c, col_name):
        if c == '':
            return None
        c = unicode(c, 'utf-8')

        if lang == 'fr' and col_name == 'sense':
            # remove sense number references from the end of the gloss
            return fr_sense_re.match(c).group(1)

        if col_name == 'sense_num':
            return normalize_sense_num(c)

        return namespace_re.sub('', c)

    def postprocess_row(row):
        for cells in row:
            yield [postprocess_cell(c, col_name)
                   for c, col_name in zip(cells, cols)]

    print 'Inserting into db'
    conn.executemany("INSERT INTO %s VALUES (%s)" % (
                        table_name, ', '.join(['?'] * len(cols))
                     ),
                     postprocess_row(joined_result))
    print 'Inserted', len(joined_result), 'rows'

    conn.commit()
    conn.close()


def get_translations(from_lang, to_lang, **kwargs):
    query = translation_query[translation_query_type[from_lang]]
    get_query('translation', query, from_lang=from_lang, to_lang=to_lang)


def apply_views(conn):
    with open(VIEW_FILENAME) as f:
        f.readline()  # skip first line
        conn.executescript(f.read())


def make_tsv(from_lang, to_lang, **kwargs):
    conn = sqlite3.connect('dictionaries/sqlite/%s.db' % from_lang)
    conn.execute("ATTACH DATABASE 'dictionaries/sqlite/%s.db' AS other" % to_lang)
    apply_views(conn)

    sql = "SELECT written_rep, sense_list, trans_list FROM csv"
    with codecs.open('dictionaries/raw3/%s-%s.tsv' % (from_lang, to_lang), 'w', encoding='utf8') as f:
        for row in conn.execute(sql):
            f.write('\t'.join(cell or '' for cell in row) + '\n')


def search_query(from_lang, to_lang, search_term, **kwargs):
    conn = sqlite3.connect('dictionaries/sqlite/%s.sqlite3' % from_lang)
    conn.execute("ATTACH DATABASE 'dictionaries/sqlite/prod/%s-%s.sqlite3' AS prod" % (from_lang, to_lang))
    for r in conn.execute("""
                SELECT * FROM (
                    SELECT lexentry, written_rep, sense_list, trans_list, prod.translation.rowid
                    FROM (
                            SELECT DISTINCT lexentry
                            FROM prod.search_trans
                            WHERE form MATCH ?
                        )
                        JOIN prod.translation USING (lexentry)
                    ORDER BY prod.translation.rowid
                )
                UNION ALL
                SELECT NULL, written_rep, NULL, trans_list, NULL
                FROM prod.search_reverse_trans
                WHERE written_rep MATCH ?
            """, [search_term, search_term]):
        print '%-40s %-10s %-80s %-20s %s' % r


def make_prod_single(lang, **kwargs):
    conn = sqlite3.connect('dictionaries/sqlite/%s.sqlite3' % lang)
    conn.execute("ATTACH DATABASE 'dictionaries/sqlite/prod/%s.sqlite3' AS prod" % (lang))

    print 'Prepare entry'
    conn.executescript("""
        DROP TABLE IF EXISTS prod.entry;
        CREATE TABLE prod.entry AS
        SELECT *
        FROM entry;

        CREATE INDEX prod.entry_written_rep_idx ON entry(written_rep);
    """)

    conn.close()
    print 'Vacuum'
    sqlite3.connect('dictionaries/sqlite/prod/{}.sqlite3'.format(lang)
                    ).execute('VACUUM')


def interactive(from_lang, to_lang, **kwargs):
    with open('/tmp/attach_dbs.sql', 'w') as f:
        f.write(attach_dbs(from_lang, to_lang))
        f.write('\n.read ' + VIEW_FILENAME)
    subprocess.check_call(
        '/usr/local/Cellar/sqlite/3.8.10.2/bin/sqlite3 -init /tmp/attach_dbs.sql dictionaries/sqlite/%s.sqlite3' % from_lang,
        shell=True)
    #p = subprocess.Popen(['sqlite3', '-interactive'], stdin=subprocess.PIPE)
    #p.communicate(script)


def attach_dbs(from_lang, to_lang):
    return """
        ATTACH DATABASE 'dictionaries/sqlite/{to_lang}.sqlite3' AS other;
        ATTACH DATABASE 'dictionaries/sqlite/{from_lang}-{to_lang}.sqlite3' AS lang_pair;
        ATTACH DATABASE 'dictionaries/sqlite/{to_lang}-{from_lang}.sqlite3' AS other_pair;
        ATTACH DATABASE 'dictionaries/sqlite/prod/{from_lang}-{to_lang}.sqlite3' AS prod;
        ATTACH DATABASE 'dictionaries/sqlite/prod/wikdict.sqlite3' AS wikdict;
    """.format(from_lang=from_lang, to_lang=to_lang)


def make_prod_pair(from_lang, to_lang, **kwargs):
    conn = sqlite3.connect('dictionaries/sqlite/%s.sqlite3' % from_lang)
    conn.executescript(attach_dbs(from_lang, to_lang))
    apply_views(conn)

    print 'Prepare translation'
    conn.executescript("""
        -- required to get a rowid
        CREATE TEMPORARY TABLE grouped_translation_table
        AS SELECT * FROM grouped_translation;

        DROP TABLE IF EXISTS prod.translation;
        CREATE TABLE prod.translation AS
        SELECT lexentry, written_rep, part_of_speech, sense_list,
               min_sense_num, trans_list
        FROM grouped_translation_table
            JOIN (
                SELECT lexentry, part_of_speech
                FROM entry
            ) USING (lexentry)
        ORDER BY grouped_translation_table.rowid
    """)

    print 'Prepare search index'
    conn.executescript("""
        DROP TABLE IF EXISTS prod.search_trans;
        CREATE VIRTUAL TABLE prod.search_trans USING fts4(
            form, lexentry, tokenize=unicode61, notindexed=lexentry
        );
        INSERT INTO prod.search_trans
        SELECT written_rep, lexentry
        FROM prod.translation
        UNION
        SELECT other_written, lexentry
        FROM form
        WHERE lexentry IN (
            SELECT lexentry FROM prod.translation
        )
    """)

    print 'Prepare search index (reversed translation)'
    conn.executescript("""
        DROP TABLE IF EXISTS prod.search_reverse_trans;
        CREATE VIRTUAL TABLE prod.search_reverse_trans USING fts4(
            written_rep, trans_list, tokenize=unicode61, notindexed=trans_list
        );
        INSERT INTO prod.search_reverse_trans
        SELECT written_rep, trans_list
        FROM grouped_reverse_trans
    """)

    conn.execute("""
        DELETE FROM wikdict.lang_pair WHERE from_lang = ? AND to_lang = ?
    """, [from_lang, to_lang])
    conn.execute("""
        INSERT INTO wikdict.lang_pair
        SELECT ?, ?,
            (SELECT count(*) FROM prod.translation),
            (SELECT count(*) FROM prod.search_reverse_trans),
            (SELECT count(*) FROM form)
    """, [from_lang, to_lang])
    print conn.execute("""
        SELECT * FROM wikdict.lang_pair WHERE from_lang = ? AND to_lang = ?
    """, [from_lang, to_lang]).fetchone()
    conn.commit()

    print 'Optimize'
    conn.execute("INSERT INTO prod.search_trans(search_trans) VALUES('optimize');")
    conn.execute("INSERT INTO prod.search_reverse_trans(search_reverse_trans) VALUES('optimize');")
    conn.close()
    print 'Vacuum'
    sqlite3.connect('dictionaries/sqlite/prod/{}-{}.sqlite3'.format(from_lang, to_lang)
                    ).execute('VACUUM')


def make_complete_lang(langs, **kwargs):
    if langs == ['all']:
        langs = translation_query_type.keys()
    for lang in langs:
        print 'Lang:', lang
        make_form(lang)
        make_entry(lang)
        make_prod_single(lang)


def make_complete_pair(langs, **kwargs):
    if langs == ['all']:
        langs = translation_query_type.keys()
    assert len(langs) >= 2, 'Need at least two languages'
    #for lang in (from_lang, to_lang):
    #    make_complete_lang([lang])
    print 'Get translations'
    for from_lang, to_lang in permutations(langs, 2):
        print from_lang, to_lang
        get_translations(from_lang, to_lang)
    print 'Get translations'
    for from_lang, to_lang in permutations(langs, 2):
        print from_lang, to_lang
        make_prod_pair(from_lang, to_lang)


def make_form(lang, **kwargs):
    get_query('form', form_query, lang=lang)


def make_entry(lang, **kwargs):
    get_query('entry', entry_query, lang=lang)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

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
    translation.set_defaults(func=get_translations)

    gen_tsv = subparsers.add_parser('tsv')
    gen_tsv.add_argument('from_lang')
    gen_tsv.add_argument('to_lang')
    gen_tsv.set_defaults(func=make_tsv)

    search = subparsers.add_parser('search')
    search.add_argument('from_lang')
    search.add_argument('to_lang')
    search.add_argument('search_term')
    search.set_defaults(func=search_query)

    prod_pair = subparsers.add_parser('prod_pair')
    prod_pair.add_argument('from_lang')
    prod_pair.add_argument('to_lang')
    prod_pair.set_defaults(func=make_prod_pair)

    prod_single = subparsers.add_parser('prod')
    prod_single.add_argument('lang')
    prod_single.set_defaults(func=make_prod_single)

    complete_lang = subparsers.add_parser('complete_lang')
    complete_lang.add_argument('langs', nargs='+', metavar='lang')
    complete_lang.set_defaults(func=make_complete_lang)

    complete_pair = subparsers.add_parser('complete_pair')
    complete_pair.add_argument('langs', nargs='+', metavar='lang')
    complete_pair.set_defaults(func=make_complete_pair)

    inter = subparsers.add_parser('interactive')
    inter.add_argument('from_lang')
    inter.add_argument('to_lang')
    inter.set_defaults(func=interactive)

    args = parser.parse_args()
    args.func(**vars(args))
