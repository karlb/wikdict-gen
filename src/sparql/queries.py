import urllib.request, urllib.error, urllib.parse
from urllib.parse import urlencode
import sqlite3
import re
import os
import json
from itertools import chain

from languages import language_codes3

namespace_re = re.compile(r"^(?:http://kaiko.getalp.org/dbnary/|http://.*#)")
fr_sense_re = re.compile(r"^(.*?)[.]?\s*(?:\(\d+\)|\|\d+)?:?$", re.DOTALL)

translation_query_type = {
    "de": "sense",
    "en": "gloss",
    "fr": "gloss",
    "pl": "sense",
    "sv": "gloss",
    "es": "sense",
    "pt": "gloss",
    "fi": "sense",
    "el": "gloss",
    "ru": "sense",
    "tr": "sense",
    "ja": "gloss",
    "bg": "gloss",
    "it": "gloss",
    "id": "gloss",
    "nl": "gloss",
    "lt": "gloss",
    "la": "gloss",
    "mg": "gloss",
    "no": "gloss",
}

form_query = """
    SELECT ?lexentry ?other_written ?pos
        ?mood ?number ?person ?tense ?voice  # important for verbs
        ?case ?inflection ?definiteness ?gender
    WHERE {
        ?lexentry a ontolex:LexicalEntry ;
                  dct:language lexvo:%(lang3)s ;
                  ontolex:otherForm ?other_form .

        ?other_form ontolex:writtenRep ?other_written .
        OPTIONAL { ?lexentry lexinfo:partOfSpeech ?pos }

        OPTIONAL { ?other_form olia:hasMood ?mood }
        OPTIONAL { ?other_form olia:hasNumber ?number }
        OPTIONAL { ?other_form olia:hasPerson ?person }
        OPTIONAL { ?other_form olia:hasTense ?tense }
        OPTIONAL { ?other_form olia:hasVoice ?voice }

        OPTIONAL { ?other_form olia:hasCase ?case }
        OPTIONAL { ?other_form olia:hasInflectionType ?inflection }
        OPTIONAL { ?other_form olia:hasDefiniteness ?definiteness }
        OPTIONAL { ?other_form olia:hasGender ?gender }
    }
"""


# not used until the virtuoso bug 575 is fixed
entry_query = """
    SELECT ?lexentry ?written_rep ?part_of_speech
           coalesce(?gender1, ?gender2) AS ?gender
           ?pronun_list
    WHERE {
        ?lexform lemon:writtenRep ?written_rep .
        ?lexentry lemon:canonicalForm ?lexform ;
                  dct:language lexvo:%(lang3)s .

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

basic_entry_query = """
    SELECT ?lexentry ?vocable ?written_rep
    WHERE {
        ?lexentry a ontolex:LexicalEntry ;
                  dct:language lexvo:%(lang3)s ;
                  ontolex:canonicalForm [
                      ontolex:writtenRep ?written_rep] .
        ?vocable a dbnary:Page ;
                 dbnary:describes ?lexentry .
    }
"""

basic_entry_pos_query = """
    SELECT ?lexentry ?part_of_speech
    WHERE {
        ?lexentry a ontolex:LexicalEntry ;
                  dct:language lexvo:%(lang3)s ;
                  lexinfo:partOfSpeech ?part_of_speech
    }
"""

basic_entry_gender_query = """
    SELECT ?lexentry
           coalesce(?gender1, ?gender2) AS ?gender
    WHERE {
        ?lexentry a ontolex:LexicalEntry ;
                  dct:language lexvo:%(lang3)s .
        OPTIONAL {
            ?lexentry ontolex:canonicalForm [lexinfo:gender ?gender1]
        }
        OPTIONAL {
            ?lexentry lexinfo:gender ?gender2 .
        }
    }
"""

basic_entry_pronun_query = """
    SELECT ?lexentry ?pronun
    WHERE {
        ?lexentry a ontolex:LexicalEntry ;
                  dct:language lexvo:%(lang3)s ;
                  ontolex:canonicalForm [ontolex:phoneticRep ?pronun]
    }
"""


translation_query = {
    "sense": r"""
        SELECT ?lexentry
            ?sense_num
            ?def_value AS ?sense
            ?trans AS ?trans_entity
            ?written_trans AS ?trans
        WHERE {
            ?lexentry a ontolex:LexicalEntry ;
                      dct:language lexvo:%(from_lang3)s ;
                      ontolex:sense ?sense .
            ?sense a ontolex:LexicalSense ;
                   dbnary:senseNumber ?sense_num ;
                   skos:definition [rdf:value ?def_value] .
            ?trans dbnary:isTranslationOf ?sense ;
                   dbnary:targetLanguage lexvo:%(to_lang3)s ;
                   dbnary:writtenForm ?written_trans.
            OPTIONAL { ?trans dbnary:gloss [dbnary:senseNumber ?tr_sense_num] }

            # FILTER (str(?lexentry) = 'http://kaiko.getalp.org/dbnary/fra/lire__verb__1')  # for tests
        }
    """,
    "gloss": """
        SELECT ?lexentry
            '' AS ?sense_num
            ?gloss AS ?sense
            ?trans AS ?trans_entity
            ?written_trans AS ?trans
        WHERE {
            ?lexentry a ontolex:LexicalEntry ;
                      dct:language lexvo:%(from_lang3)s .
            ?trans dbnary:isTranslationOf ?lexentry ;
                   dbnary:targetLanguage lexvo:%(to_lang3)s ;
                   dbnary:writtenForm ?written_trans .

            OPTIONAL {?trans dbnary:gloss [rdf:value ?gloss] }
          #  FILTER (str(?lexentry) = 'http://kaiko.getalp.org/dbnary/fra/lire__verb__1')  # for tests
        }
    """,
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
            ?vocable a dbnary:Page ;
                     dbnary:describes ?lexentry .
            ?lexentry dct:language lexvo:%(lang3)s .
            OPTIONAL {
                ?synonym dbnary:synonym ?vocable .
            }
            OPTIONAL {
                ?translation dbnary:isTranslationOf ?lexentry .
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


nym_query = """
SELECT DISTINCT ?f ?nym ?t_rep
  # Don't use ?t but only ?t_rep, since the *nyms don't link to a lexical entry. 
  # ?t ?t_page ?f_rep   # extra columns for debugging
WHERE {
  VALUES ?nym {dbnary:synonym dbnary:hypernym dbnary:hyponym}

  ?f ?nym ?t_page;
     dct:language lexvo:%(lang3)s;
     lexinfo:partOfSpeech ?f_pos.
  ?t_page dbnary:describes ?t.
  ?t ontolex:canonicalForm [ontolex:writtenRep ?t_rep];
     lexinfo:partOfSpeech ?t_pos.

  # Synonyms (and other *nyms) go from a lexical entry to a Wiktionary page. Since the target page can contain many different lexical entries, we limit the target entries (?t) to those which have the same part of speech as the source entry (?f)
  FILTER (?f_pos = ?t_pos)

  # For debugging only
  #?f ontolex:canonicalForm [ontolex:writtenRep ?f_rep].
}
"""


def make_url(query, **fmt_args):
    assert (
        fmt_args["limit"] <= 1048576
    ), "Virtuoso does not support more than 1048576 results"
    # server = 'http://kaiko.getalp.org'
    server = "http://localhost:8890"
    if "ORDER BY" not in query:
        query += "\nORDER BY 1"
    query = """
        SELECT *
        WHERE {
            %s
        }
        OFFSET %%(offset)s
        LIMIT %%(limit)s
    """ % (
        query
    )
    for key, val in list(fmt_args.items()):
        if key.endswith("lang"):
            fmt_args[key + "3"] = language_codes3[val]
    url = (
        server
        + "/sparql?"
        + urlencode(
            {
                "default-graph-uri": "",
                "query": query % fmt_args,
                "format": "application/json",
                "timeout": 0,
            }
        )
    )
    # print query % fmt_args
    return url


def page_through_results(query, limit, **kwargs):
    offset = 0
    while True:
        url = make_url(query, limit=limit, offset=offset, **kwargs)
        try:
            response = urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            print(e.read())
            raise

        data = json.load(response)

        global cols
        cols = data["head"]["vars"]
        result = data["results"]["bindings"]
        yield result
        if len(result) < limit:
            break
        else:
            offset += limit
            print(".")


def create_table(conn, table_name, first_result=None):
    sql_filename = "src/sql/sparql/{}.sql".format(table_name)
    if first_result:
        sql_types = {
            "http://www.w3.org/2001/XMLSchema#integer": "int",
            "http://www.w3.org/2001/XMLSchema#decimal": "real",
            "http://www.w3.org/2001/XMLSchema#double": "real",
            "http://www.w3.org/2001/XMLSchema#string": "text",
            None: "text",
        }
        col_types = [
            sql_types[first_result.get(col_name, {}).get("datatype")]
            for col_name in cols
        ]
        sql = """
            DROP TABLE IF EXISTS {table_name};
            CREATE TABLE {table_name} ({col_def});
        """.format(
            table_name=table_name,
            col_def=", ".join(
                '"%s" %s' % col_desc for col_desc in zip(cols, col_types)
            ),
        )
        # Save definition to file. This is required for cases where the query
        # returns no results, so that we can't determine the columns and types
        # from the result.
        with open(sql_filename, "w") as f:
            f.write(sql)
    else:
        with open(sql_filename) as f:
            sql = f.read()

    conn.executescript(sql)


def get_query(table_name, query, **kwargs):
    if "lang" in kwargs:
        lang = kwargs["lang"]
        db_name = lang
    else:
        lang = kwargs["from_lang"]
        kwargs["lang"] = lang
        db_name = "{}-{}".format(kwargs["from_lang"], kwargs["to_lang"])

    print("Fetch {} (SPARQL)".format(table_name))
    limit = int(5e5)
    batches = page_through_results(query, limit=limit, **kwargs)
    results = chain.from_iterable(batches)
    path = "dictionaries/raw"
    os.makedirs(path, exist_ok=True)
    conn = sqlite3.connect("%s/%s.sqlite3" % (path, db_name))

    try:
        first_result = next(results)
    except StopIteration:
        print("No results!")
        create_table(conn, table_name)  # create empty table
        return

    # put first result back into iterable
    results = chain([first_result], results)

    create_table(conn, table_name, first_result)

    py_types = {
        "http://www.w3.org/2001/XMLSchema#integer": int,
        "http://www.w3.org/2001/XMLSchema#decimal": float,
        "http://www.w3.org/2001/XMLSchema#double": float,
        "http://www.w3.org/2001/XMLSchema#string": str,
    }

    def postprocess_literal(col_name, value, **kwargs):
        if lang == "fr" and col_name == "sense":
            # remove sense number references from the end of the gloss
            match = fr_sense_re.match(value)
            assert match, f"malformed gloss: {value!r}"
            return match.group(1)

        return value

    postprocess = {
        "literal": postprocess_literal,
        "uri": lambda col_name, value, **kwargs: namespace_re.sub("", value),
        "typed-literal": lambda col_name, value, datatype, **kwargs: py_types[datatype](
            value
        ),
    }

    def postprocess_row(row):
        for col_name in cols:
            if col_name not in row:
                yield None
                continue
            cell = row[col_name]
            processed = postprocess[cell["type"]](col_name, **cell)
            if isinstance(processed, str):
                # The input contains some badly encoded characters.
                # Replace these with ?-Symbols to avoid later errors
                processed = processed.encode("utf-8", "replace").decode()
            yield processed

    print("Inserting into db")
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO %s VALUES (%s)" % (table_name, ", ".join(["?"] * len(cols))),
        (list(postprocess_row(r)) for r in results),
    )
    print("Inserted", cur.rowcount, "rows")

    conn.commit()
    conn.close()
