import math
import os
import sqlite3

from languages import language_codes3

from . import backend
from . import store

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


# The union queries below lead with the selective `dct:language` pattern and omit
# the non-selective `a ontolex:LexicalEntry` / `a dbnary:Page` type scans: in the
# loaded dumps dct:language and dbnary:describes occur only on lexical entries and
# pages respectively, so the types are redundant but cost a full-store scan.
basic_entry_query = """
    SELECT ?lexentry ?vocable ?written_rep
    WHERE {
        ?lexentry dct:language lexvo:%(lang3)s ;
                  ontolex:canonicalForm/ontolex:writtenRep ?written_rep .
        ?vocable dbnary:describes ?lexentry .
    }
"""

basic_entry_pos_query = """
    SELECT ?lexentry ?part_of_speech
    WHERE {
        ?lexentry dct:language lexvo:%(lang3)s ;
                  lexinfo:partOfSpeech ?part_of_speech
    }
"""

basic_entry_gender_query = """
    SELECT ?lexentry
           (COALESCE(?gender1, ?gender2) AS ?gender)
    WHERE {
        ?lexentry dct:language lexvo:%(lang3)s .
        OPTIONAL {
            ?lexentry ontolex:canonicalForm/lexinfo:gender ?gender1
        }
        OPTIONAL {
            ?lexentry lexinfo:gender ?gender2 .
        }
    }
"""

basic_entry_pronun_query = """
    SELECT ?lexentry ?pronun
    WHERE {
        ?lexentry dct:language lexvo:%(lang3)s ;
                  ontolex:canonicalForm/ontolex:phoneticRep ?pronun
    }
"""


translation_query = {
    # dbnary connects a translation to a sense definition two different ways, and
    # which one an edition uses drifts over time, per edition (see
    # notes/suggestions/bugs.md #6). We extract BOTH and merge them in run.py:
    # neither alone is correct (the gloss-join is 0 for still-sense-linked editions
    # like pl; the direct link is 0 for migrated editions like fr/de).
    #
    # Both lead with the selective translation pattern (target language) rather than
    # scanning every LexicalEntry in the edition's graph.
    #
    # "sense": gloss-senseNumber join, for editions on the entry+gloss model. The
    # gloss's senseNumber is joined to the entry's senses to recover the definition;
    # because ?lexentry and ?sense_num are both bound by the translation first, the
    # sense lookup is scoped per entry and can't go cartesian.
    "sense": r"""
        SELECT ?lexentry ?sense_num (?def_value AS ?sense)
            (?trans_node AS ?trans_entity) (?written_trans AS ?trans)
        WHERE {
            ?trans_node dbnary:targetLanguage lexvo:%(to_lang3)s ;
                        dbnary:isTranslationOf ?lexentry ;
                        dbnary:writtenForm ?written_trans ;
                        dbnary:gloss [dbnary:senseNumber ?sense_num] .
            ?lexentry dct:language lexvo:%(from_lang3)s ;
                      ontolex:sense ?sense_ .
            ?sense_ dbnary:senseNumber ?sense_num ;
                    skos:definition [rdf:value ?def_value] .
        }
    """,
    # "sense_direct": the translation links straight to the LexicalSense, for
    # editions still on the old model (pl; partly es). The sense's senseNumber and
    # definition constraints right after isTranslationOf prune the entry-linked
    # binding, so migrated editions return 0 quickly instead of going cartesian.
    "sense_direct": r"""
        SELECT ?lexentry ?sense_num (?def_value AS ?sense)
            (?trans_node AS ?trans_entity) (?written_trans AS ?trans)
        WHERE {
            ?trans_node dbnary:targetLanguage lexvo:%(to_lang3)s ;
                        dbnary:isTranslationOf ?sense_ ;
                        dbnary:writtenForm ?written_trans .
            ?sense_ dbnary:senseNumber ?sense_num ;
                    skos:definition [rdf:value ?def_value] .
            ?lexentry dct:language lexvo:%(from_lang3)s ;
                      ontolex:sense ?sense_ .
        }
    """,
    "gloss": """
        SELECT ?lexentry ("" AS ?sense_num) (?gloss AS ?sense)
            (?trans_node AS ?trans_entity) (?written_trans AS ?trans)
        WHERE {
            ?trans_node dbnary:targetLanguage lexvo:%(to_lang3)s ;
                        dbnary:isTranslationOf ?lexentry ;
                        dbnary:writtenForm ?written_trans .
            ?lexentry dct:language lexvo:%(from_lang3)s .

            # An explicit gloss-node variable, not a blank node [rdf:value ...]:
            # oxigraph plans a blank node inside OPTIONAL pathologically slowly.
            OPTIONAL { ?trans_node dbnary:gloss ?gloss_node . ?gloss_node rdf:value ?gloss }
        }
    """,
}


# importance returns counts; the score (sqrt sum) is computed in python, since
# SPARQL has no sqrt (Virtuoso used the bif:sqrt extension).
importance_query = """
    SELECT ?vocable
        (COUNT(DISTINCT ?synonym) AS ?synonym_count)
        (COUNT(DISTINCT ?translation) AS ?translation_count)
    WHERE {
        ?vocable dbnary:describes ?lexentry .
        ?lexentry dct:language lexvo:%(lang3)s .
        OPTIONAL {
            ?synonym dbnary:synonym ?vocable .
        }
        OPTIONAL {
            ?translation dbnary:isTranslationOf ?lexentry .
        }
        OPTIONAL {
            ?lexentry lexinfo:partOfSpeech ?pos .
        }
        # Keep entries with no partOfSpeech: oxigraph's NOT IN errors on the unbound
        # ?pos (dropping the row), whereas Virtuoso kept it.
        FILTER (!BOUND(?pos) || ?pos NOT IN (lexinfo:abbreviation, lexinfo:letter))
    }
    GROUP BY ?vocable
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


# Column order of each raw table (matches src/sql/sparql/*.sql). Everything is text
# except importance.score.
COLUMNS = {
    "form": [
        "lexentry",
        "other_written",
        "pos",
        "mood",
        "number",
        "person",
        "tense",
        "voice",
        "case",
        "inflection",
        "definiteness",
        "gender",
    ],
    "entry": ["lexentry", "vocable", "written_rep"],
    "pos": ["lexentry", "part_of_speech"],
    "gender": ["lexentry", "gender"],
    "pronun": ["lexentry", "pronun"],
    "importance": ["vocable", "score"],
    "nym": ["f", "nym", "t_rep"],
    "translation_sense": ["lexentry", "sense_num", "sense", "trans_entity", "trans"],
    "translation_sense_direct": [
        "lexentry",
        "sense_num",
        "sense",
        "trans_entity",
        "trans",
    ],
    "translation_gloss": ["lexentry", "sense_num", "sense", "trans_entity", "trans"],
}
COLUMN_SQL_TYPE = {"score": "real"}

# Queries that only need one edition's data are scoped to that edition's named
# graph (fast); the rest query the union of all editions' graphs.
SINGLE_EDITION = {
    "form",
    "translation_sense",
    "translation_sense_direct",
    "translation_gloss",
}


def create_table(conn, table_name):
    col_def = ", ".join(
        '"%s" %s' % (col, COLUMN_SQL_TYPE.get(col, "text"))
        for col in COLUMNS[table_name]
    )
    conn.executescript(
        "DROP TABLE IF EXISTS {0}; CREATE TABLE {0} ({1});".format(table_name, col_def)
    )


def _importance_rows(reader, query, lang):
    """Yield (vocable, score) where score = sqrt(translations) + sqrt(synonyms)."""
    for sol in backend.query(reader, query, union=True):
        vocable = backend.cell(backend.get(sol, "vocable"), "vocable", lang)
        synonyms = int(sol["synonym_count"].value)
        translations = int(sol["translation_count"].value)
        yield (vocable, math.sqrt(translations) + math.sqrt(synonyms))


def get_query(reader, table_name, query, **kwargs):
    if "lang" in kwargs:
        lang = kwargs["lang"]
        db_name = lang
    else:
        lang = kwargs["from_lang"]
        db_name = "{}-{}".format(kwargs["from_lang"], kwargs["to_lang"])

    fmt_args = dict(kwargs)
    for key, val in list(fmt_args.items()):
        if key.endswith("lang"):
            fmt_args[key + "3"] = language_codes3[val]
    sparql_query = query % fmt_args

    print("Fetch {} (pyoxigraph)".format(table_name))
    columns = COLUMNS[table_name]
    if table_name == "importance":
        rows = _importance_rows(reader, sparql_query, lang)
    elif table_name in SINGLE_EDITION:
        rows = backend.run_query(
            reader, sparql_query, columns, lang, graph=store.edition_graph(lang)
        )
    else:
        rows = backend.run_query(reader, sparql_query, columns, lang, union=True)

    path = "dictionaries/raw"
    os.makedirs(path, exist_ok=True)
    conn = sqlite3.connect("%s/%s.sqlite3" % (path, db_name))
    create_table(conn, table_name)
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO %s VALUES (%s)" % (table_name, ", ".join(["?"] * len(columns))),
        rows,
    )
    print("Inserted", cur.rowcount, "rows")
    conn.commit()
    conn.close()
