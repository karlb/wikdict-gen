#!/usr/bin/env python
import sys
from collections import namedtuple
from subprocess import check_call
from datetime import date

split_pos = 4
from_lang, to_lang = sys.argv[1:]


def format_word(word):
    out = word.written
    if word.gender and '|' not in word.gender:
        out += ' {%s}' % word.gender[0]
    if word.pronun and '|' not in word.pronun:
        out += ' ' + word.pronun
    return out


# generate tsv
Translation = namedtuple('Translation', ['written', 'gender', 'pos', 'pronun'])
in_filename = 'dictionaries/raw/{}-{}.tsv'.format(from_lang, to_lang)
out_filename = 'dictionaries/tsv/{}-{}.tsv'.format(from_lang, to_lang)
with open(in_filename) as in_file, open(out_filename, 'w') as out_file:
    for line in in_file:
        fields = line.rstrip().split('\t')
        while len(fields) < split_pos * 2:
            fields.append('')
        words = [
            Translation(*fields[:split_pos]),
            Translation(*fields[split_pos:]),
        ]
        out_file.write('\t'.join(format_word(w) for w in words) + '\n')

# generate quickdict dictionary from tsv
params = dict(
    lang1=from_lang, lang2=to_lang,
    dictOut='dictionaries/quickdict/{}-{}.quickdic'.format(from_lang, to_lang),
    dictInfo='WikDict.com dictionary data from {}'.format(date.today()),
    lang1Stoplist='quickdict/stoplists/{}.txt'.format(from_lang),
    lang2Stoplist='quickdict/stoplists/{}.txt'.format(to_lang),
    input1='dictionaries/tsv/{}-{}.tsv'.format(from_lang, to_lang),
    input1Name='dbnary',
    input1Charset='UTF8',
    input1Format='tab_separated',
)
param_string = ' '.join('--{}={}'.format(key, val)
                        for key, val in params.items())
check_call('java -Xmx512m -jar quickdict/DictionaryBuilder.jar ' + param_string,
           shell=True)
