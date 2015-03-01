#!/usr/bin/env python
import sys
import codecs
import subprocess
import datetime
from collections import namedtuple
from xml.etree.ElementTree import Element, SubElement, tostring, XML
from languages import language_names, language_codes3

from_lang, to_lang = sys.argv[1:]


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


Translation = namedtuple('Translation', ['word', 'pos', 'gender', 'sense',
                                         'sense_num', 'trans_list',
                                         'pronun_list'])
in_filename = 'dictionaries/raw2/{}-{}.tsv'.format(from_lang, to_lang)
out_filename = 'dictionaries/tei/{}-{}.tei'.format(language_codes3[from_lang],
                                                   language_codes3[to_lang])
root = Element('TEI', xmlns="http://www.tei-c.org/ns/1.0")
headwords = int(subprocess.check_output("cut -f 1 -d $'\t' %s | uniq | wc -l"
                                        % in_filename, shell=True))
with codecs.open(in_filename, 'r', 'utf-8') as in_file, \
        open(out_filename, 'w') as out_file:

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
                    <title>WikDict.com {from_name}-{to_name} dictionary</title>
                </titleStmt>
                <editionStmt><p>{today}</p></editionStmt>
                <extent>{headwords} headwords</extent>
                <publicationStmt>
                    <publisher>Karl Bartel</publisher>
                    <availability status="free">
                        <p>Licensed under the Creative Commons Attribution-ShareAlike License</p>
                        <p>See http://creativecommons.org/licenses/by-sa/3.0/ for details</p>
                    </availability>
                </publicationStmt>
                <sourceDesc>
                    <p>All entries from Wiktionary.org via DBnary</p>
                </sourceDesc>
            </fileDesc>
        </teiHeader>
    '''.format(
            from_name=language_names[from_lang], to_name=language_names[to_lang],
            headwords=headwords, today=datetime.date.today()
        ).encode('utf-8'))
    root.append(tei_header)

    body = SubElement(SubElement(root, 'text'),
                      'body', {'xml:lang': from_lang})

    for line in in_file:
        fields = line.rstrip().split('\t')
        while len(fields) < len(Translation._fields):
            fields.append(None)
        x = Translation(*fields)

        # entry
        entry = SubElement(body, 'entry')
        form = SubElement(entry, 'form')
        orth = SubElement(form, 'orth')
        if x.pos == 'suffix' or (x.pos == '' and x.word.startswith('-')):
            assert x.word.startswith('-')
            orth.text = x.word[1:]
            gram_grp = SubElement(entry, 'gramGrp')
            pos = SubElement(gram_grp, 'pos')
            pos.text = 'part'
        else:
            orth.text = x.word + x.pos

        # translation
        cit = SubElement(entry, 'cit',
                         {'type': 'translation', 'xml:lang': to_lang})
        for trans in x.trans_list.split(' | '):
            quote = SubElement(cit, 'quote')
            quote.text = trans

        # sense
        sense = SubElement(entry, 'sense')
        sense_def = SubElement(sense, 'def')
        sense_def.text = x.sense

    # format xml output
    indent(root)
    out_file.write(tostring(root, 'utf-8'))
