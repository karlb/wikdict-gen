import os
import sqlite3


class PartOfSpeechChooser:

    def __init__(self):
        self.pos_list = []

    def step(self, value):
        self.pos_list.append(value)

    def finalize(self):
        # TODO: proper choosing of pos
        return sorted(self.pos_list)[0]


def make_entry(conn, lang):
    conn.create_aggregate("choose_pos", 1, PartOfSpeechChooser)
    conn.executescript("""
        DROP TABLE IF EXISTS main.entry;
        CREATE TABLE entry AS
        SELECT lexentry, written_rep, choose_pos(part_of_speech) AS part_of_speech,
            CASE
                WHEN min(gender) == max(gender) THEN gender
                ELSE NULL
            END AS gender,
            pronun_list
        FROM raw.entry
        WHERE written_rep is NOT NULL
          AND written_rep != ''
        GROUP BY lexentry;
        CREATE UNIQUE INDEX entry_pkey ON entry(lexentry);
    """)


def make_form(conn, lang):
    conn.executescript("""
        DROP TABLE IF EXISTS main.form;
        CREATE TABLE form AS
        SELECT *
        FROM raw.form
    """)


def make_translation(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS main.translation;
        CREATE TABLE translation AS
        SELECT *
        FROM raw.translation
    """)


def make_process(lang, only=None, **kwargs):
    target_tables = {
            'entry': make_entry,
            'form': make_form,
    }
    os.makedirs('dictionaries/processed', exist_ok=True)
    conn = sqlite3.connect('dictionaries/processed/%s.sqlite3' % lang)
    conn.execute(
        "ATTACH DATABASE 'dictionaries/raw/%s.sqlite3' AS raw" % lang)
    print('processing %s:' % lang, flush=True, end=' ')
    for name, f in target_tables.items():
        if not only or only == name:
            print(name, flush=True, end=' ')
            f(conn, lang=lang)
    conn.commit()
    print()


def make_process_pair(from_lang, to_lang, only=None, **kwargs):
    target_tables = {
            'translation': make_translation,
    }
    os.makedirs('dictionaries/processed', exist_ok=True)
    conn = sqlite3.connect('dictionaries/processed/%s-%s.sqlite3' % (from_lang, to_lang))
    conn.execute(
        "ATTACH DATABASE 'dictionaries/raw/%s-%s.sqlite3' AS raw" % (from_lang, to_lang))
    print('processing %s-%s:' % (from_lang, to_lang), flush=True, end=' ')
    for name, f in target_tables.items():
        if not only or only == name:
            print(name, flush=True, end=' ')
            f(conn)
    conn.commit()
    print()


def add_subparsers(subparsers):
    process = subparsers.add_parser(
        'process', help='process raw db into a new processed db')
    process.add_argument('lang')
    process.set_defaults(func=make_process)
    process.add_argument('--only')

    process_pair = subparsers.add_parser('process_pair',
        help='process raw db into a new processed db for lang pair')
    process_pair.add_argument('from_lang')
    process_pair.add_argument('to_lang')
    process_pair.set_defaults(func=make_process_pair)
    process_pair.add_argument('--only')
