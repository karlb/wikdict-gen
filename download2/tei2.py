#!/usr/bin/env python
import sys
import glob
import codecs
import subprocess
import datetime
import json
from xml.etree.ElementTree import Element, SubElement, tostring, XML
from languages import language_names, language_codes3


def indent(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


pos_mapping = {
    'adjective': ('adj', 'FreeDict_ontology.xml#f_pos_adj'),
    'adverb': ('adv', 'FreeDict_ontology.xml#f_pos_adv'),
    'noun': ('n', 'FreeDict_ontology.xml#f_pos_noun'),
    'properNoun': ('pn', 'FreeDict_ontology.xml#f_pos_noun'),
    'verb': ('v', 'FreeDict_ontology.xml#f_pos_verb'),
    # other pos from ontology which are not used, yet:
    # <item ana="FreeDict_ontology.xml#f_pos_v-intrans">vi</item>
    # <item ana="FreeDict_ontology.xml#f_pos_v-trans">vt</item>
    # <item ana="FreeDict_ontology.xml#f_pos_num">num</item>
    # <item ana="FreeDict_ontology.xml#f_pos_prep">prep</item>
    # <item ana="FreeDict_ontology.xml#f_pos_int">int</item>
    # <item ana="FreeDict_ontology.xml#f_pos_pron">pron</item>
    # <item ana="FreeDict_ontology.xml#f_pos_conj">conj</item>
    # <item ana="FreeDict_ontology.xml#f_pos_art">art</item>
}


def write_tei_dict(from_lang, to_lang, lines):
    print from_lang, to_lang
    lines = sorted(l for l in lines if l[1] == from_lang + '-' + to_lang)
    out_filename = 'dictionaries/tei2/{}-{}.tei'.format(
                        language_codes3[from_lang],
                        language_codes3[to_lang])
    root = Element('TEI', xmlns="http://www.tei-c.org/ns/1.0")
    headwords = len(lines)
    pos_usage = ''.join('<item ana="{1}">{0}</item>'.format(*pos)
                        for pos in pos_mapping.values())

    with open(out_filename, 'w') as out_file:
        # prepare header
        out_file.write("""
            <?xml version="1.0" encoding="UTF-8"?>
            <?xml-stylesheet type="text/css" href="freedict-dictionary.css"?>
            <?oxygen RNGSchema="freedict-P5.rng" type="xml"?>
            <!DOCTYPE TEI SYSTEM "freedict-P5.dtd">
        """.strip())
        tei_header = XML(u'''
            <teiHeader xml:lang="en">
                <fileDesc>
                    <titleStmt>
                        <title>{from_name}-{to_name} FreeDict+WikDict dictionary</title>
                        <respStmt>
                            <resp>Maintainer</resp>
                            <name>Karl Bartel</name>
                        </respStmt>
                    </titleStmt>
                    <editionStmt><edition>{today}</edition></editionStmt>
                    <extent>{headwords} headwords</extent>
                    <publicationStmt>
                        <publisher>Karl Bartel</publisher>
                        <availability status="free">
                            <p>Licensed under the Creative Commons Attribution-ShareAlike License</p>
                            <p>See http://creativecommons.org/licenses/by-sa/3.0/ for details</p>
                        </availability>
                        <date>{today}</date>
                    </publicationStmt>
                    <sourceDesc>
                        <p>All entries from Wiktionary.org via DBnary</p>
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
                                </list>
                            </tagUsage>
                        </namespace>
                    </tagsDecl>
                </encodingDesc>
            </teiHeader>
        '''.format(
                from_name=language_names[from_lang],
                to_name=language_names[to_lang], headwords=headwords,
                today=datetime.date.today(), pos_usage=pos_usage
            ).encode('utf-8'))
        root.append(tei_header)

        body = SubElement(SubElement(root, 'text'),
                        'body', {'xml:lang': from_lang})

        for line in lines:
            written_lower, lang_pair, groups_json = line
            groups = json.loads(groups_json)

            for x in groups:
                # entry
                entry = SubElement(body, 'entry')
                form = SubElement(entry, 'form')
                orth = SubElement(form, 'orth')
                if x['pronun_list']:
                    for p in x['pronun_list']:
                        pron = SubElement(form, 'pron')
                        pron.text = p
                is_suffix = (
                    x['pos'] == 'suffix' or
                    (x['pos'] in ('', None) and x['written'].startswith('-'))
                )
                if is_suffix:
                    assert x['written'].startswith('-')
                    orth.text = x['written'][1:]
                    pos_text = 'suffix'
                else:
                    orth.text = x['written']
                    pos_text = pos_mapping.get(x['pos'], (x['pos'], None))[0]

                # gramGrp
                if pos_text:
                    gram_grp = SubElement(entry, 'gramGrp')
                    pos = SubElement(gram_grp, 'pos')
                    pos.text = pos_text

                # sense
                for i, s in enumerate(x.get('sense_list') or [None]):
                    sense = SubElement(entry, 'sense', {'n': str(i + 1)})
                    if s is not None:
                        sense_def = SubElement(sense, 'usg', {'type': 'hint'})
                        sense_def.text = s

                    # translation
                    cit = SubElement(sense, 'cit',
                                    {'type': 'trans', 'xml:lang': to_lang})
                    for trans in x['trans_list']:
                        quote = SubElement(cit, 'quote')
                        if is_suffix:
                            trans = trans[1:]
                        quote.text = trans

        # format xml output
        indent(root)
        out_file.write(tostring(root, 'utf-8'))


def write_dict_pair(from_lang, to_lang):
    in_filename = 'dictionaries/raw2/grouped/{}-{}.tsv'.format(from_lang, to_lang)
    with codecs.open(in_filename, 'r', 'utf-8') as in_file:
        lines = [line.rstrip().split('\t') for line in in_file]
        write_tei_dict(from_lang, to_lang, lines)
        write_tei_dict(to_lang, from_lang, lines)


if len(sys.argv) == 2 and sys.argv[1] == 'all':
    for path in glob.glob('dictionaries/raw2/grouped/*.tsv'):
        filename = path.split('/')[-1]
        from_lang, to_lang = filename.replace('.tsv', '').split('-')
        write_dict_pair(from_lang, to_lang)
elif len(sys.argv) == 3:
    from_lang, to_lang = sys.argv[1:]
    write_dict_pair(from_lang, to_lang)
else:
    print 'Usage: %s [FROM_LANG] [TO_LANG]' % sys.argv[0]
    print '    or %s all' % sys.argv[0]

# validate
# xmllint --noout --dtdvalid freedict-P5.dtd --relaxng freedict-P5.rng.txt --valid *.tei
