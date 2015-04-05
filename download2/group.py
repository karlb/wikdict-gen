#!/usr/bin/env python
import sys
import itertools
from collections import namedtuple
import json

if len(sys.argv) != 3:
    print 'Usage: %s [FROM_LANG] [TO_LANG]' % sys.argv[0]
    sys.exit(-1)
lang1, lang2 = sorted(sys.argv[1:])

Sense = namedtuple('Sense', ['written', 'pos', 'gender', 'sense',
                                   'sense_num', 'trans_list', 'pronun_list'])
Group = namedtuple('Group', ['written', 'pos', 'gender',
                             'sense_list', 'trans_list', 'pronun_list'])


def group_key(trans):
    return (trans.written, trans.pos, trans.gender, trans.trans_list, trans.pronun_list)


def make_group(input_ts):
    input_ts.sort(key=group_key)
    return [
        Group(written, pos, gender, [t.sense for t in ts],
              trans_list, pronun_list)
        for (written, pos, gender, trans_list, pronun_list), ts
        in itertools.groupby(input_ts, key=group_key)
    ]


def make_sense(line):
    while len(line) < len(Sense._fields):
        line.append(None)
    t = Sense(*line)
    trans_list = t.trans_list.split(' | ')
    if '' in trans_list:
        raise Exception('Empty translation %r %r' % (t.written, trans_list))
    if t.written == '':
        raise Exception('Bad headword %r' % t.written)
    return t._replace(
        trans_list=trans_list,
        pronun_list=t.pronun_list.split(' | ') if t.pronun_list else [],
    )


def make_vocable_list(from_lang, to_lang):
    vocables = {}
    filename = '{}-{}.tsv'.format(from_lang, to_lang)
    with open('dictionaries/raw2/' + filename) as in_file:
        lines = (
            line.rstrip().split('\t')
            for line in in_file
        )
        translations = (
            make_sense(l)
            for l in lines
        )
        for written, ts in itertools.groupby(translations,
                                             key=lambda l: l[0].lower()):
            vocable = make_group(list(ts))
            vocables[written] = vocable
            #if written == 'hund':
            #    print written
            #    for t in vocable:
            #        print t
            #    break
    return vocables


def add_fallback_entries(vocables, other_dir):
    add_these = {}
    for voc in other_dir.values():
        for group in voc:
            for trans in group.trans_list:
                current = add_these.setdefault(trans, set())
                current.add(group.written)
            #if group.written == 'Canis Minor':
            #    print '>>>1'
            #    print group
            #    print current
    for written, translations in add_these.items():
        existing_translations = set()
        voc = vocables.setdefault(written.lower(), [])
        for group in voc:
            existing_translations = existing_translations.union(
                group.trans_list
            )
        new_translations = list(translations - existing_translations)
        #if written == 'Kleiner Hund':
        #    print '>>>'
        #    print voc
        #    print existing_translations
        #    print new_translations
        if new_translations:
            voc.append(Group(written, None, None, None, new_translations, None))
        #for trans in translations:
        #    if trans in existing_translations:
        #        continue
        #    voc.append(Group(written, None, None, None, [trans], None))
        #    #print '--->', written, trans


    #print add_these.get('gift')


dir1 = make_vocable_list(lang1, lang2)
dir2 = make_vocable_list(lang2, lang1)
add_fallback_entries(dir1, dir2)
add_fallback_entries(dir2, dir1)

#print '--'
#for x in dir1['hund']:
#    print x
#print '--'
#for x in dir2['boot']:
#    print x


filename = '{}-{}.tsv'.format(lang1, lang2)
with open('dictionaries/raw2/grouped/' + filename, 'w') as out_file:
    for direction, lang_code in zip((dir1, dir2),
                                    (lang1 + '-' + lang2, lang2 + '-' + lang1)
                                   ):
        for key, voc in direction.items():
            json_voc = [g._asdict() for g in voc]
            #for g in voc:
            #    out_file.write('%s\t%s\t%s\n' % (key, lang_code,
            #                                     json.dumps(g._asdict())))
            out_file.write('%s\t%s\t%s\n' % (key, lang_code,
                                                json.dumps(json_voc)))

