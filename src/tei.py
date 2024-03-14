#!/usr/bin/env python3
import os
import sys
import sqlite3
import datetime
import codecs
import time
from itertools import groupby, permutations
from xml.etree.cElementTree import (
    Element,
    SubElement,
    tostring,
    XML,
    register_namespace,
)
from collections import OrderedDict

from languages import language_names, language_codes3
from helper import supported_langs


INCLUDE_INFLECTED = True


def indent(elem, level=0):
    i = "\n" + level * "  "
    if elem:
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for e in elem:
            indent(e, level + 1)
        # pylint: disable=undefined-loop-variable
        if not e.tail or not e.tail.strip():
            e.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


CONTROL_CHARS = dict.fromkeys(range(32))
del CONTROL_CHARS[10]  # allow newlines


def remove_control_characters(x):
    """Remove characters with ord(c) < 32

    Those should not be anywhere in a dictionary
    """
    return x.translate(CONTROL_CHARS)


pos_mapping = OrderedDict(
    [
        ("adjective", ("adj", "FreeDict_ontology.xml#f_pos_adj")),
        ("adverb", ("adv", "FreeDict_ontology.xml#f_pos_adv")),
        ("noun", ("n", "FreeDict_ontology.xml#f_pos_noun")),
        ("properNoun", ("pn", "FreeDict_ontology.xml#f_pos_noun")),
        ("verb", ("v", "FreeDict_ontology.xml#f_pos_verb")),
        # other pos from ontology which are not used, yet:
        # <item ana="FreeDict_ontology.xml#f_pos_v-intrans">vi</item>
        # <item ana="FreeDict_ontology.xml#f_pos_v-trans">vt</item>
        # <item ana="FreeDict_ontology.xml#f_pos_num">num</item>
        # <item ana="FreeDict_ontology.xml#f_pos_prep">prep</item>
        # <item ana="FreeDict_ontology.xml#f_pos_int">int</item>
        # <item ana="FreeDict_ontology.xml#f_pos_pron">pron</item>
        # <item ana="FreeDict_ontology.xml#f_pos_conj">conj</item>
        # <item ana="FreeDict_ontology.xml#f_pos_art">art</item>
    ]
)

gender_mapping = {
    "feminine": "fem",
    "masculine": "masc",
    "neuter": "neut",
    "commongender": "ut",
}


tei_template = """
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:wikdict="http://www.wikdict.com/ns/1.0">
  <teiHeader xml:lang="en">
    <fileDesc>
      <titleStmt>
        <title>{from_name}-{to_name} FreeDict+WikDict dictionary</title>
        <respStmt>
          <resp>Maintainer</resp>
          <name xml:id="karlb">Karl Bartel</name>
        </respStmt>
      </titleStmt>
      <editionStmt><edition>{version}</edition></editionStmt>
      <extent>{headwords} headwords</extent>
      <publicationStmt>
        <publisher>Karl Bartel</publisher>
        <availability status="free">
          <p>Licensed under the <ref target="https://creativecommons.org/licenses/by-sa/3.0/legalcode">Creative Commons Attribution-ShareAlike 3.0 Unported</ref> license</p>
        </availability>
        <date>{today}</date>
      </publicationStmt>
      <notesStmt>
        <note type="status">{status}</note>
      </notesStmt>
      <sourceDesc>
        <p>Automatic creation of this bilingual dictionary by <ref target="http://www.wikdict.com/">WikDict</ref>.</p>
        <p>Base data from <ref target="https://www.wiktionary.org/">Wiktionary.org</ref> via <ref target="http://kaiko.getalp.org/about-dbnary/">DBnary</ref>.</p>
      </sourceDesc>
    </fileDesc>
    <encodingDesc>
      <projectDesc>
        <p>
          This dictionary comes to you through nice people
          making it available for free and for good. It is part of
          the FreeDict project, http://www.freedict.org/. This
          project aims to make available many translating
          dictionaries for free. Your contributions are welcome!
        </p>
      </projectDesc>
      <tagsDecl>
        <!-- for each gi, its values are listed, with a pointer to the ontology interface -->
        <namespace name="http://www.tei-c.org/ns/1.0" xml:base="../shared/">
          <tagUsage gi="pos">
            <list n="values" type="bulleted">
              {pos_usage}
            </list>
          </tagUsage>
          <tagUsage gi="gen">
            <list>
              <item ana="FreeDict_ontology.xml#f_gen_fem">fem</item>
              <item ana="FreeDict_ontology.xml#f_gen_masc">masc</item>
              <item ana="FreeDict_ontology.xml#f_gen_neut">neut</item>
            </list>
          </tagUsage>
        </namespace>
      </tagsDecl>
    </encodingDesc>
    <revisionDesc>
      <change when="2018-09-12" who="#karlb">
        Change numbering scheme from YYYY-MM-DD to YYYY.MM.DD
      </change>
      <change when="2018-05-15" who="#karlb">
        Add links to sourceDesc
      </change>
      <change when="2017-12-15" who="#karlb">
        Add changelog
      </change>
      <change when="2017-11-22" who="#karlb">
        Use ref tag to encode license URL
      </change>
    </revisionDesc>
    <wikdict:dummy />
  </teiHeader>
  <text>
    <body xml:lang="{from_lang}">
      {{entries}}
    </body>
  </text>
</TEI>
"""


def list_split(l):
    if l is None:
        return []
    return l.split(" | ")


SHOW_TIMINGS = False


def measured_execute(conn, query, *args, **kwargs):
    start = time.time()
    # for line in conn.execute("EXPLAIN QUERY PLAN " + query, *args, **kwargs):
    #     print(dict(line))
    # return []
    ret_val = conn.execute(query, *args, **kwargs)
    duration = time.time() - start
    timing_dict = query_timings.setdefault(
        query,
        {
            "total_time": 0,
            "max_time": 0,
            "num_calls": 0,
        },
    )
    timing_dict["total_time"] += duration
    timing_dict["num_calls"] += 1
    if duration > timing_dict["max_time"]:
        timing_dict["max_time"] = duration
    return ret_val


def get_translations(from_lang, to_lang):
    global query_timings
    query_timings = {}
    conn = sqlite3.connect(
        "file:dictionaries/wdweb/%s-%s.sqlite3?mode=ro" % (from_lang, to_lang),
        uri=True,
    )
    conn.row_factory = sqlite3.Row

    conn.execute(
        "ATTACH DATABASE 'dictionaries/wdweb/%s.sqlite3' AS prod_lang" % from_lang
    )
    conn.execute(
        "ATTACH DATABASE 'dictionaries/processed/%s.sqlite3' AS from_lang" % from_lang
    )
    good_translations = next(
        conn.execute(
            """
        SELECT count(*) FROM translation WHERE translation_score >= 100
    """
        )
    )[0]
    measured_exec = lambda *args, **kwargs: measured_execute(conn, *args, **kwargs)
    conn.execute("BEGIN")
    measured_exec("CREATE INDEX from_lang.from_lexentry_idx ON form(lexentry)")

    expected_good_translations = 45000
    min_translation_score = round(
        (good_translations - 1000) / expected_good_translations * 100
    )
    min_translation_score = max(min(min_translation_score, 100), 0)
    print(
        "{} good translations, min_score = {}".format(
            good_translations, min_translation_score
        )
    )
    translations = measured_exec(
        """
        SELECT lexentry,
            t.written_rep, t.sense_list, t.trans_list,
            e.gender, e.part_of_speech, e.pronun_list
        FROM translation t
             JOIN prod_lang.entry e USING (lexentry)
        WHERE translation_score >= ?
        ORDER BY t.written_rep, e.part_of_speech, e.gender, e.pronun_list, t.min_sense_num
    """,
        [min_translation_score],
    )
    groups = groupby(
        translations,
        lambda t: (
            t["written_rep"],
            t["part_of_speech"],
            t["gender"],
            t["pronun_list"],
        ),
    )
    for key, translations_for_entry in groups:
        written_rep, part_of_speech, gender, pronun_list = key
        entry = dict(
            written_rep=written_rep,
            part_of_speech=part_of_speech,
            gender=gender,
            pronuns=list_split(pronun_list),
        )
        entry["senses"] = []
        for t in translations_for_entry:
            sense_list = list_split(t["sense_list"])
            if not sense_list:
                sense_list = [None]
            for s in sense_list:
                entry["senses"].append(
                    dict(
                        gloss=s,
                        trans_list=list_split(t["trans_list"]),
                    )
                )

        entry["inflected_forms"] = list(
            measured_exec(
                """
            SELECT other_written, min(rank) AS rank
            FROM form f
            WHERE lexentry = ?
            GROUP BY other_written
            ORDER BY rank;
        """,
                [t["lexentry"]],
            )
        )

        yield entry

    # We create an index and don't want to keep it in the db.
    conn.rollback()

    if SHOW_TIMINGS:
        for query, timing in query_timings.items():
            print(query)
            print(timing | {"avg_time": timing["total_time"] / timing["num_calls"]})


def add_senses(entry, x, to_lang, is_suffix):
    groups = groupby(x["senses"], lambda s: (s["trans_list"]))
    for trans_list, subsenses in groups:
        sense = SubElement(entry, "sense")
        # translation
        cit = SubElement(sense, "cit", {"type": "trans", "xml:lang": to_lang})
        for trans in trans_list:
            assert trans, "empty translation for %r" % x
            quote = SubElement(cit, "quote")
            if is_suffix:
                trans = trans[1:]
            quote.text = trans

        # subsenses
        for s in subsenses:
            if s["gloss"]:
                subsense = SubElement(sense, "sense")
                sense_def = SubElement(subsense, "def")
                sense_def.text = s["gloss"]


def single_tei_entry(x, to_lang):
    # entry
    entry = Element("entry")
    form = SubElement(entry, "form")
    orth = SubElement(form, "orth")
    if x["pronuns"]:
        for p in x["pronuns"]:
            pron = SubElement(form, "pron")
            pron.text = p
    is_suffix = x["part_of_speech"] == "suffix" or (
        x["part_of_speech"] in ("", None) and x["written_rep"].startswith("-")
    )
    if is_suffix:
        # assert x['written_rep'].startswith('-')
        orth.text = x["written_rep"][1:]
        pos_text = "suffix"
    else:
        orth.text = x["written_rep"]
        pos_text = pos_mapping.get(x["part_of_speech"], (x["part_of_speech"], None))[0]

    # inflected forms
    if x["inflected_forms"] and INCLUDE_INFLECTED:
        infl_form = SubElement(form, "form", {"type": "infl"})
        for infl_form_row in x["inflected_forms"]:
            attrs = {"wikdict:show": "true"} if infl_form_row["rank"] else {}
            SubElement(infl_form, "orth", attrs).text = infl_form_row["other_written"]

    # gramGrp
    gram_grp = Element("gramGrp")
    if pos_text:
        pos = SubElement(gram_grp, "pos")
        pos.text = pos_text
    if x["gender"]:
        gen = SubElement(gram_grp, "gen")
        gen.text = gender_mapping[x["gender"].lower()]
    if list(gram_grp):
        entry.append(gram_grp)

    add_senses(entry, x, to_lang, is_suffix)

    return entry


def get_tei_entries_as_xml(from_lang, to_lang):
    """Get all entries as xml string

    Keeping them as XML objects would use much more memory
    """
    conn = sqlite3.connect("dictionaries/generic/%s.sqlite3" % from_lang)
    conn.row_factory = sqlite3.Row
    entries_xml_text_list = []
    headwords = 0
    for x in get_translations(from_lang, to_lang):
        entry = single_tei_entry(x, to_lang)

        indent(entry, level=2)
        entries_xml_text_list.append(tostring(entry, "unicode"))
        headwords += 1
        if headwords % 2000 == 0:
            print(".", end="", flush=True)
    print()

    entries_xml_text = remove_control_characters("".join(entries_xml_text_list))
    return entries_xml_text, headwords


def write_tei_dict(from_lang, to_lang):
    print(from_lang, to_lang)
    pos_usage = "".join(
        '<item ana="{1}">{0}</item>'.format(*pos) for pos in list(pos_mapping.values())
    )

    # get entries, this is where most work is done
    entries, headwords = get_tei_entries_as_xml(from_lang, to_lang)
    if headwords == 0:
        return

    if headwords >= 10000:
        status = "big enough to be useful"
    elif headwords < 1000:
        status = "too small"
    else:
        status = "unknown"

    # prepare template
    register_namespace("", "http://www.tei-c.org/ns/1.0")
    register_namespace("wikdict", "http://www.wikdict.com/ns/1.0")
    today = datetime.date.today().isoformat()
    version = today.replace("-", ".")
    tei_template_xml = XML(
        tei_template.format(
            from_name=language_names[from_lang],
            to_name=language_names[to_lang],
            headwords=headwords,
            from_lang=from_lang,
            today=today,
            version=version,
            pos_usage=pos_usage,
            status=status,
        )
    )
    indent(tei_template_xml)

    # render xml and add entries
    rendered_template = tostring(tei_template_xml, "utf-8").decode("utf-8")
    # if we don't add the dummy, the namespace is stripped, since no elements are in the XML, yet
    rendered_template = rendered_template.replace("<wikdict:dummy />", "")
    complete_tei = rendered_template.format(
        entries=entries,
    )

    # write to file and add declarations
    out_dir = "dictionaries/tei" + ("/small" if headwords < 5000 else "")
    os.makedirs(out_dir, exist_ok=True)
    out_filename = "{}/{}-{}.tei".format(
        out_dir, language_codes3[from_lang], language_codes3[to_lang]
    )
    with codecs.open(out_filename, "w", "utf-8") as out_file:
        out_file.write(
            """
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/css" href="freedict-dictionary.css"?>
<?oxygen RNGSchema="freedict-P5.rng" type="xml"?>
<!DOCTYPE TEI SYSTEM "freedict-P5.dtd">
        """.strip()
            + "\n"
        )
        out_file.write(complete_tei)


def write_dict_pair(from_lang, to_lang):
    write_tei_dict(from_lang, to_lang)
    write_tei_dict(to_lang, from_lang)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "all":
        for from_lang, to_lang in permutations(supported_langs, 2):
            write_dict_pair(from_lang, to_lang)
    elif len(sys.argv) == 3:
        from_lang, to_lang = sys.argv[1:]
        # import cProfile
        # cProfile.run('write_dict_pair(from_lang, to_lang)', sort='cumtime')
        # cProfile.run('get_tei_entries_as_xml("de", "fr")', sort='tottime')
        write_dict_pair(from_lang, to_lang)
    else:
        print("Usage: %s [FROM_LANG] [TO_LANG]" % sys.argv[0])
        print("    or %s all" % sys.argv[0])


if __name__ == "__main__":
    main()

# validate
# xmllint --noout --dtdvalid freedict-P5.dtd --relaxng freedict-P5.rng.txt \
#   --valid *.tei
