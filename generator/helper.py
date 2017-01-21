import os
import sys
import sqlite3
from itertools import permutations

supported_langs = [
    'de', 'en', 'fr', 'pl', 'sv', 'es', 'pt', 'fi', 'el', 'ru', 'tr',
]


def make_for_langs(functions, langs, **kwargs):
    """ Executes functions for all given languages

        `langs` can also be "all" to execute on all supported languages.
    """
    if langs == ['all']:
        langs = supported_langs
    for lang in langs:
        for func in functions:
            print(lang, func.__name__)
            func(lang)


def make_for_lang_permutations(functions, langs, **kwargs):
    """ Executes functions for all pairwise combinations of the given langs.

        `langs` can also be "all" to execute on all supported languages.
    """
    if langs == ['all']:
        langs = supported_langs
    assert len(langs) >= 2, 'Need at least two languages'

    for func in functions:
        print('>> ' + func.__name__)
        for from_lang, to_lang in permutations(langs, 2):
            print(from_lang, to_lang)
            func(from_lang, to_lang)


def make_targets(lang, out_path, targets, in_path=None, only=None, sql=None, attach=[]):
    if out_path.endswith('.sqlite3'):
        conn = sqlite3.connect('dictionaries/%s' % out_path)
    else:
        os.makedirs('dictionaries/' + out_path, exist_ok=True)
        conn = sqlite3.connect('dictionaries/%s/%s.sqlite3' % (out_path, lang))
    conn.execute("ATTACH DATABASE 'dictionaries/%s/%s.sqlite3' AS %s"
            % (in_path, lang, in_path))
    for a in attach:
        conn.execute(
            "ATTACH DATABASE " + a)
    conn.enable_load_extension(True)
    conn.load_extension('lib/icu')

    if sql:
        cur = conn.cursor()
        cur.execute(sql)
        print([col[0] for col in cur.description])
        for row in cur.fetchall():
            print(row)
        return

    print('%s/%s:' % (out_path, lang), flush=True, end=' ')
    for name, f in targets:
        if not only or only == name:
            print(name, flush=True, end=' ')
            f(conn, lang)
    conn.commit()
    print()


if __name__ == '__main__':
    if sys.argv[1] == 'all_pairs':
        print(' '.join(
            from_lang + '-' + to_lang
            for from_lang, to_lang in permutations(supported_langs, 2)
        ))
    elif sys.argv[1] == 'all_langs':
        print(' '.join(supported_langs))
    else:
        print('Unknwn command %s' % sys.argv[1])
