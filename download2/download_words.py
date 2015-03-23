#!/usr/bin/env python
import sys
import urllib2
from urllib import urlencode
import csv

from languages import language_codes3

limit = 100000
if len(sys.argv) != 2:
    print 'Usage: %s [LANG]' % sys.argv[0]
    sys.exit(-1)
lang = sys.argv[1]
query = """
    SELECT * WHERE {
        SELECT
            ?written ?pos ?gender
            ?sense_value ?sense_number
            group_concat(DISTINCT ?pronun, ' | ') AS ?pronuns
        WHERE {
            ?vocable dbnary:refersTo ?entry .
            ?entry lemon:canonicalForm ?form ;
                   dcterms:language lexvo:%(lang)s .
            ?form lemon:writtenRep ?written .

            OPTIONAL { ?entry lexinfo:partOfSpeech ?pos . }
            OPTIONAL { ?form lexinfo:gender ?gender . }
            OPTIONAL { ?form lexinfo:pronunciation ?pronun . }
            OPTIONAL {
                ?entry lemon:sense ?sense .
                ?sense lemon:definition ?sense_def ;
                    dbnary:senseNumber ?sense_number .
                ?sense_def lemon:value ?sense_value .
            }
            FILTER (
                #bound(?pos) OR  # commented out to reduce amount of data
                bound(?gender) OR bound(?pronun) OR bound(?sense_def)
            )
        }
        GROUP BY ?entry ?written ?pos ?gender ?sense_value ?sense_number
        ORDER BY ?entry ?sense_number
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
with open('dictionaries/raw2/{}.tsv'.format(lang), 'w') as f:
    while True:
        # download and save
        offset = part * limit
        url = make_url(lang=language_codes3[lang],
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

        if part >= 40:
            print ('Do we really need to fetch more than {} parts? '
                'Stopping to avoid load.'.format(part + 1))
            sys.exit(-2)

        part += 1
        print '.',
        sys.stdout.flush()
