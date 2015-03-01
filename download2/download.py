#!/usr/bin/env python
import sys
import urllib2
from urllib import urlencode
import csv

from languages import language_codes3

limit = 10000
if len(sys.argv) != 3:
    print 'Usage: %s [FROM_LANG] [TO_LANG]' % sys.argv[0]
    sys.exit(-1)
from_lang, to_lang = sys.argv[1:]
query = """
    SELECT * WHERE {
        SELECT DISTINCT ?written_rep ?pos ?gender
            ?def_value ?sense_num
            ?trans_list ?pronun_list
        WHERE {
            ?lexform lemon:writtenRep ?written_rep .
            ?lexentry lemon:canonicalForm ?lexform ;
                    dcterms:language lexvo:%(from_lang)s ;
                    lemon:sense ?sense .
            ?sense lemon:definition ?def ;
                dbnary:senseNumber ?sense_num .
            ?def lemon:value ?def_value .

            {
                SELECT ?sense,
                       group_concat(?written_trans, ' | ') AS ?trans_list
                WHERE {
                ?trans dbnary:isTranslationOf ?sense ;
                    dbnary:targetLanguage lexvo:%(to_lang)s ;
                    dbnary:writtenForm ?written_trans .
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
        }
        ORDER BY ?lexentry ?sense_num
    }
    OFFSET %(offset)s
    LIMIT %(limit)s
"""


def make_url(**fmt_args):
    #server = 'http://kaiko.getalp.org'
    server = 'http://localhost:8890'
    url = server + '/sparql?' + urlencode({
        'default-graph-uri': '',
        'query': query % fmt_args,
        'format': 'text/tab-separated-values',
        'timeout': 0,
    })
    #print query % fmt_args
    return url

part = 0
with open('dictionaries/raw2/{}-{}.tsv'.format(from_lang, to_lang), 'w') as f:
    while True:
        # download and save
        offset = part * limit
        url = make_url(from_lang=language_codes3[from_lang],
                    to_lang=language_codes3[to_lang],
                    offset=offset, limit=limit)
        try:
            response = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            print e.read()
            raise
        tsv = response.readlines()

        # stop if finished
        if len(tsv) <= 1:
            break

        # write results to file
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
