#!/usr/bin/env python
import sys
import urllib2
from urllib import urlencode
import csv

from languages import language_codes3

limit = 20000
if len(sys.argv) != 3:
    print 'Usage: %s [FROM_LANG] [TO_LANG]' % sys.argv[0]
    sys.exit(-1)
from_lang, to_lang = sys.argv[1:]


query_type = {
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
query_dict = {
    'sense': """
        SELECT DISTINCT ?written_rep ?pos ?gender
            ?def_value ?sense_num
            ?trans_list ?pronun_list
        WHERE {
            ?lexform lemon:writtenRep ?written_rep .
            ?lexentry lemon:canonicalForm ?lexform ;
                    dcterms:language lexvo:%(from_lang3)s ;
                    lemon:sense ?sense .
            ?sense lemon:definition ?def ;
                dbnary:senseNumber ?sense_num .
            ?def lemon:value ?def_value .

            {
                SELECT ?sense,
                       group_concat(DISTINCT ?written_trans, ' | ')
                            AS ?trans_list
                WHERE {
                    ?trans dbnary:isTranslationOf ?sense ;
                        dbnary:targetLanguage lexvo:%(to_lang3)s ;
                        dbnary:writtenForm ?written_trans .
                    FILTER (str(?written_trans) != '')
                }
            }
            OPTIONAL {
                SELECT ?lexform, group_concat(?pronun, ' | ') AS ?pronun_list
                WHERE {
                    ?lexform lexinfo:pronunciation ?pronun .
                }
            }
            OPTIONAL { ?lexentry lexinfo:partOfSpeech ?pos . }
            OPTIONAL { ?lexform lexinfo:gender ?gender . }
            FILTER (str(?written_rep) != '')  # probably not necessary, but
                    # seems to avoid a bug in my local virtuoso for @es data
            #FILTER (?written_rep = 'second'@en)  # for tests
        }
        ORDER BY ?lexentry ?sense_num
    """,
    'gloss': """
        SELECT DISTINCT ?written_rep ?pos ?gender
            ?gloss ?sense_num
            ?trans_list ?pronun_list
        WHERE {
            ?lexform lemon:writtenRep ?written_rep .
            ?lexentry lemon:canonicalForm ?lexform ;
                    dcterms:language lexvo:%(from_lang3)s .

            {
                SELECT ?lexentry
                       ?gloss
                       group_concat(DISTINCT ?written_trans, ' | ')
                            AS ?trans_list
                       min(?sense_num) AS ?sense_num
                       #?written_trans AS ?trans_list
                WHERE {
                    ?trans dbnary:isTranslationOf ?lexentry ;
                        dbnary:targetLanguage lexvo:%(to_lang3)s ;
                        dbnary:writtenForm ?written_trans ;
                        dbnary:gloss ?gloss .
                    ?lexentry lemon:sense ?sense .
                    ?sense dbnary:senseNumber ?sense_num .
                }
            }
            OPTIONAL {
                SELECT ?lexform, group_concat(?pronun, ' | ') AS ?pronun_list
                WHERE {
                    ?lexform lexinfo:pronunciation ?pronun .
                }
            }
            OPTIONAL { ?lexentry lexinfo:partOfSpeech ?pos . }
            OPTIONAL { ?lexform lexinfo:gender ?gender . }
            #FILTER (?written_rep = 'second'@en)  # for tests
            FILTER (str(?written_rep) != '')  # probably not necessary, but
                    # seems to avoid a bug in my local virtuoso for @es data
        }
        ORDER BY ?lexentry ?sense_num ?gloss
    """
}


def make_url(from_lang, to_lang, offset, limit):
    #server = 'http://kaiko.getalp.org'
    server = 'http://localhost:8890'
    query = """
        SELECT * WHERE {
            %s
        }
        OFFSET %s
        LIMIT %s
    """ % (query_dict[query_type[from_lang]], offset, limit)
    fmt_args = {
        'from_lang3': language_codes3[from_lang],
        'to_lang3': language_codes3[to_lang],
    }
    url = server + '/sparql?' + urlencode({
        'default-graph-uri': '',
        'query': query % fmt_args,
        'format': 'text/tab-separated-values',
        'timeout': 0,
    })
    #print query % fmt_args
    return url

part = 0
header_written = False
with open('dictionaries/raw2/{}-{}.tsv'.format(from_lang, to_lang), 'w') as f:
    while True:
        # download and save
        offset = part * limit
        url = make_url(from_lang=from_lang, to_lang=to_lang,
                       offset=offset, limit=limit)
        try:
            response = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            print e.read()
            raise
        tsv = response.readlines()

        # stop if finished
        if len(tsv) <= 1:
            if part == 0:
                print 'WARNING: no results'
            break

        # write results to file
        #if not header_written:
        #    cols = csv.reader(tsv[:1], dialect="excel-tab").next()
        #    f.write('\t'.join(cols) + '\n')
        #    header_written = True
        for cols in csv.reader(tsv[1:], dialect="excel-tab"):
            line = '\t'.join(cols)
            f.write(
                line
                .replace('http://www.lexinfo.net/ontology/2.0/lexinfo#', '')
                .replace('"', '')
                .replace('\n', '')
                + '\n'
            )

        if part >= 20:
            print ('Do we really need to fetch more than {} parts? '
                'Stopping to avoid load.'.format(part + 1))
            sys.exit(-2)

        part += 1
        print '.',
        sys.stdout.flush()
