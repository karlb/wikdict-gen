#!/usr/bin/env python
import sys
import urllib2
from urllib import urlencode

from languages import language_codes3

limit = 10000
if len(sys.argv) != 3:
    print 'Usage: %s [FROM_LANG] [TO_LANG]' % sys.argv[0]
    sys.exit(-1)
from_lang, to_lang = sys.argv[1:]
query = """
        SELECT
            ?a
            group_concat(DISTINCT ?a_pos, ' | ') AS ?a_pos
            group_concat(DISTINCT ?a_gender, ' | ') AS ?a_gender
            group_concat(DISTINCT ?a_pronun, ' | ') AS ?a_pronun
            ?b
            group_concat(DISTINCT ?b_pos, ' | ') AS ?b_pos
            group_concat(DISTINCT ?b_gender, ' | ') AS ?b_gender
            group_concat(DISTINCT ?b_pronun, ' | ') AS ?b_pronun
    WHERE {
        SELECT ?a ?b ?a_pos ?a_gender ?a_pronun ?b_pos ?b_gender ?b_pronun
        WHERE {
            {
                ?a_form lemon:writtenRep ?a .
                ?a_entry lemon:canonicalForm ?a_form ;
                    dcterms:language lexvo:%(from_lang)s .
                ?trans dbnary:isTranslationOf ?a_entry ;
                    dbnary:targetLanguage lexvo:%(to_lang)s ;
                    dbnary:writtenForm ?b .
            }
            UNION {
                ?b_form lemon:writtenRep ?b .
                ?b_entry lemon:canonicalForm ?b_form ;
                    dcterms:language lexvo:%(to_lang)s .
                ?trans dbnary:isTranslationOf ?b_entry ;
                    dbnary:targetLanguage lexvo:%(from_lang)s ;
                    dbnary:writtenForm ?a .
            }
            OPTIONAL {
                ?a_form lemon:writtenRep ?a .
                ?a_entry lemon:canonicalForm ?a_form ;
                        dcterms:language lexvo:%(from_lang)s .
                OPTIONAL { ?a_form lexinfo:gender ?a_gender . }
                OPTIONAL { ?a_form lexinfo:pronunciation ?a_pronun . }
                OPTIONAL { ?a_entry lexinfo:partOfSpeech ?a_pos . }
            }
            OPTIONAL {
                ?b_form lemon:writtenRep ?b .
                ?b_entry lemon:canonicalForm ?b_form ;
                        dcterms:language lexvo:%(to_lang)s .
                OPTIONAL { ?b_form lexinfo:gender ?b_gender . }
                OPTIONAL { ?b_form lexinfo:pronunciation ?b_pronun . }
                OPTIONAL { ?b_entry lexinfo:partOfSpeech ?b_pos . }
            }
        }
    }
    GROUP BY ?a ?b
    OFFSET %(offset)s
    LIMIT %(limit)s
"""


def make_url(**fmt_args):
    url = 'http://kaiko.getalp.org/sparql?' + urlencode({
        'default-graph-uri': '',
        'query': query % fmt_args,
        'format': 'text/tab-separated-values',
        'timeout': 0,
    })
    return url

part = 0
with open('dictionaries/raw/{}-{}.tsv'.format(from_lang, to_lang)) as f:
    while True:
        # download and save
        offset = part * limit
        url = make_url(from_lang=language_codes3[from_lang],
                    to_lang=language_codes3[to_lang],
                    offset=offset, limit=limit)
        response = urllib2.urlopen(url)
        tsv = response.readlines()

        # stop if finished
        if len(tsv) <= 1:
            break

        # write results to file
        for line in tsv[1:]:
            f.write(
                line
                .replace('http://www.lexinfo.net/ontology/2.0/lexinfo#', '')
                .replace('"', '')
            )

        if part >= 20:
            print ('Do we really need to fetch more than {} parts? '
                'Stopping to avoid load.'.format(part))
            sys.exit(-2)

        part += 1
        print '.',
        sys.stdout.flush()
