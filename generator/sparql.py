import csv
import urllib2
from urllib import urlencode
import sqlite3
import re
import json
from itertools import chain

from languages import language_codes3

namespace_re = re.compile(r'^(?:http://kaiko.getalp.org/dbnary/|http://.*#)')
fr_sense_re = re.compile(r'^(.*?)[.]?\s*(?:\(\d+\)|\|\d+)?:?$')
sense_num_re = re.compile(r'(\d+)(\w)?')

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
    #'ja': 'gloss',
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
    SELECT ?lexentry ?written_rep ?part_of_speech
           coalesce(?gender1, ?gender2) AS ?gender
           ?pronun_list
    WHERE {
        ?lexform lemon:writtenRep ?written_rep .
        ?lexentry lemon:canonicalForm ?lexform ;
                  dcterms:language lexvo:%(lang3)s .

        ?lexentry lexinfo:partOfSpeech ?part_of_speech
        # I used optional earlier, am now missing some entries, but
        # virtuoso does not return proper ?part_of_speech results in
        # version 07.20.3217, otherwise. At least on my system.
        # See https://github.com/openlink/virtuoso-opensource/issues/575
        #OPTIONAL { ?lexentry lexinfo:partOfSpeech ?part_of_speech }

        OPTIONAL { ?lexform lexinfo:gender ?gender1 }
        OPTIONAL { ?lexentry lexinfo:gender ?gender2 }
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


importance_query = """
    SELECT ?vocable
        bif:sqrt(?translation_count) + bif:sqrt(?synonym_count) AS ?score
    WHERE {
        SELECT ?vocable
            count(DISTINCT ?lexentry) AS ?lexentry_count
            count(DISTINCT ?sense) AS ?sense_count
            count(DISTINCT ?synonym) AS ?synonym_count
            count(DISTINCT ?translation) AS ?translation_count
        WHERE {
            ?vocable dbnary:refersTo ?lexentry .
            ?lexentry dcterms:language lexvo:%(lang3)s .
            OPTIONAL {
                ?synonym dbnary:synonym ?vocable .
            }
            OPTIONAL {
                ?translation dbnary:isTranslationOf ?lexentry.
            }
            OPTIONAL {
                ?lexentry lemon:sense ?sense .
            }
            OPTIONAL {
                ?lexentry lexinfo:partOfSpeech ?pos .
            }
            FILTER (?pos NOT IN (lexinfo:abbreviation, lexinfo:letter))
        }
    }
    ORDER BY DESC(?score)
"""


def make_url(query, **fmt_args):
    assert fmt_args['limit'] <= 1048576, 'Virtuoso does not support more than 1048576 results'
    #server = 'http://kaiko.getalp.org'
    server = 'http://localhost:8890'
    if 'ORDER BY' not in query:
        query += '\nORDER BY 1'
    query = """
        SELECT *
        WHERE {
            %s
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
        'format': 'application/json',
        'timeout': 0,
    })
    #print query % fmt_args
    return url


def normalize_sense_num(c):
    if c == '':
        return 999
    match = sense_num_re.match(c)
    assert match, 'Sense re does not match for %r' % c
    normalized_sense_num = '{:02d}'.format(int(match.group(1)))
    if match.group(2):
        normalized_sense_num += match.group(2)
    return normalized_sense_num


def page_through_results(query, limit, **kwargs):
    offset = 0
    while True:
        url = make_url(query, limit=limit, offset=offset, **kwargs)
        try:
            response = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            print e.read()
            raise
        #raw_json = response.read()
        #with open('debug.json', 'w') as f:
        #    f.write(raw_json)
        #raw_json = raw_json.decode("unicode_escape")
        #raw_json = open('debug.json').read()
        #data = json.loads(raw_json)

        # This should be
        #    data = json.load(response)
        # but virtuoso generates invalid json, so we have to work around it.
        # See https://github.com/dbpedia/extraction-framework/issues/318
        from codecs import raw_unicode_escape_decode
        json_data = raw_unicode_escape_decode(response.read())[0]
        data = json.loads(json_data)

        global cols
        cols = data['head']['vars']
        result = data['results']['bindings']
        yield result
        if len(result) < limit:
            break
        else:
            offset += limit
            print '.'


def create_table(conn, table_name, first_result=None):
    sql_filename = 'sql/sparql/{}.sql'.format(table_name)
    if first_result:
        sql_types = {
            'http://www.w3.org/2001/XMLSchema#integer': 'int',
            'http://www.w3.org/2001/XMLSchema#decimal': 'real',
            'http://www.w3.org/2001/XMLSchema#double': 'real',
            'http://www.w3.org/2001/XMLSchema#string': 'text',
            None: 'text',
        }
        col_types = [
            sql_types[
                first_result.get(col_name, {}).get('datatype')
            ]
            for col_name in cols
        ]
        sql = """
            DROP TABLE IF EXISTS {table_name};
            CREATE TABLE {table_name} ({col_def});
        """.format(table_name=table_name,
                   col_def=', '.join('"%s" %s' % col_desc
                           for col_desc in zip(cols, col_types))
                  )
        # Save definition to file. This is required for cases where the query
        # returns no results, so that we can't determine the columns and types
        # from the result.
        with open(sql_filename, 'w') as f:
            f.write(sql)
    else:
        with open(sql_filename) as f:
            sql = f.read()

    conn.executescript(sql)


def get_query(table_name, query, **kwargs):
    if 'lang' in kwargs:
        lang = kwargs['lang']
        db_name = lang
    else:
        lang = kwargs['from_lang']
        kwargs['lang'] = lang
        db_name = '{}-{}'.format(kwargs['from_lang'], kwargs['to_lang'])

    print 'Executing SPARQL query'
    limit = int(5e5)
    batches = page_through_results(query, limit=limit, **kwargs)
    results = chain.from_iterable(batches)
    conn = sqlite3.connect('dictionaries/sqlite/%s.sqlite3' % db_name)

    try:
        first_result = next(results)
    except StopIteration:
        print 'No results!'
        create_table(conn, table_name)  # create empty table
        return

    # put first result back into iterable
    results = chain([first_result], results)

    create_table(conn, table_name, first_result)

    py_types = {
        'http://www.w3.org/2001/XMLSchema#integer': int,
        'http://www.w3.org/2001/XMLSchema#decimal': float,
        'http://www.w3.org/2001/XMLSchema#double': float,
        'http://www.w3.org/2001/XMLSchema#string': unicode,
    }

    def postprocess_literal(col_name, value, **kwargs):
        # TODO: has this been fixed, so this code can be removed?
        #
        # virtuoso does not properly handle unicode, so we have to decode
        # explicitly, here. See http://stackoverflow.com/a/20422447/114926
        # This cannot be done on the whole json, because it leads to unescaped
        # tabs in json strings, which is not valid json.
        #print repr(value)
        #value = value.decode("unicode_escape")

        if lang == 'fr' and col_name == 'sense':
            # remove sense number references from the end of the gloss
            return fr_sense_re.match(value).group(1)

        if col_name == 'sense_num':
            return normalize_sense_num(value)

        return value

    postprocess = {
        'literal': postprocess_literal,
        'uri':
            lambda col_name, value, **kwargs: namespace_re.sub('', value),
        'typed-literal':
            lambda col_name, value, datatype, **kwargs: py_types[datatype](value)
    }

    def postprocess_row(row):
        for col_name in cols:
            if col_name not in row:
                yield None
                continue
            cell = row[col_name]
            yield postprocess[cell['type']](col_name, **cell)

    print 'Inserting into db'
    cur = conn.cursor()
    cur.executemany("INSERT INTO %s VALUES (%s)" % (
                        table_name, ', '.join(['?'] * len(cols))
                     ),
                     (list(postprocess_row(r)) for r in results))
    print 'Inserted', cur.rowcount, 'rows'

    conn.commit()
    conn.close()


def get_translation(from_lang, to_lang, **kwargs):
    query = translation_query[translation_query_type[from_lang]]
    get_query('translation', query, from_lang=from_lang, to_lang=to_lang)

