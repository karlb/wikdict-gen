import os
import sqlite3
from collections import defaultdict


TOKENIZER = defaultdict(lambda: 'unicode61', {
    'en': 'porter'
})


def remove_formatting(x):
    try:
        if x is None:
            return None
        x = html_parser.parse(x)
        x = clean_wiki_syntax(x)
        return x
    except Exception as e:
        print(e)
        raise


def apply_views(conn, view_file='views.sql'):
    conn.create_function('remove_formatting', 1, remove_formatting)
    with open(view_file) as f:
        f.readline()  # skip first line
        conn.executescript(f.read())


def make_entry(conn, lang):
    conn.load_extension('lib/spellfix1')
    apply_views(conn, 'single_views.sql')
    conn.executescript("""
        DROP TABLE IF EXISTS main.entry;
        CREATE TABLE main.entry AS
        SELECT entry.*, display, display_addition
        FROM processed.entry
             LEFT JOIN lexentry_display USING (lexentry)
        WHERE written_rep IS NOT NULL;

        CREATE INDEX main.entry_written_rep_idx ON entry(written_rep);

        -- spellfix
        --DROP TABLE IF EXISTS main.search_trans_aux;
        --CREATE VIRTUAL TABLE main.search_trans_aux USING fts4aux(search_trans);
        DROP TABLE IF EXISTS main.spellfix_entry;
        CREATE VIRTUAL TABLE main.spellfix_entry USING spellfix1;
        INSERT INTO main.spellfix_entry(word, rank)
        SELECT DISTINCT
            written_rep,
            score * score * score AS rank  -- incease weight of rank over distance
        FROM main.entry
            JOIN (
                SELECT substr(vocable, 5) AS written_rep,
                       rel_score * 100 AS score
                FROM rel_importance
            ) USING (written_rep)
    """)


def make_display(conn, lang):
    conn.execute("DROP VIEW IF EXISTS main.lexentry_display")
    if lang == 'de':
        conn.execute("""
            CREATE VIEW lexentry_display AS
            WITH noun AS (
                SELECT lexentry, other_written, number
                FROM form
                WHERE pos = 'noun'
                    AND "case" = 'Nominative'
                    AND (inflection = 'WeakInflection'
                         OR inflection IS NULL)
            )
            SELECT lexentry, singular AS display,
                'Pl.: ' || plural AS display_addition
            FROM (
                SELECT lexentry, other_written AS singular
                FROM noun
                WHERE number = 'Singular'
                GROUP BY 1
                HAVING count(DISTINCT other_written) = 1
            ) JOIN (
                SELECT lexentry, other_written AS plural
                FROM noun
                WHERE number = 'Plural'
                GROUP BY 1
                HAVING count(DISTINCT other_written) = 1
            ) USING (lexentry)
        """)
    else:
        conn.execute("""
            CREATE VIEW lexentry_display AS
            SELECT '' AS lexentry, '' AS display, '' AS display_addition
        """)


def make_translation(conn, lang_pair):
    apply_views(conn)
    conn.executescript("""
        -- required to get a rowid
        CREATE TEMPORARY TABLE grouped_translation_table
        AS SELECT * FROM grouped_translation;

        DROP TABLE IF EXISTS main.translation;
        CREATE TABLE main.translation AS
        SELECT lexentry, written_rep, part_of_speech, sense_list,
               min_sense_num, trans_list
        FROM grouped_translation_table
            JOIN (
                SELECT lexentry, part_of_speech
                FROM entry
            ) USING (lexentry)
        ORDER BY grouped_translation_table.rowid;
        CREATE INDEX main.translation_lexentry_idx ON translation('lexentry');
        CREATE INDEX main.translation_written_rep_idx ON translation('written_rep');
    """)


def make_search_index(conn, lang_pair):
    from_lang, to_lang = lang_pair.split('-')

    # main search index
    conn.executescript("""
        -- search table
        DROP TABLE IF EXISTS main.search_trans;
        CREATE VIRTUAL TABLE main.search_trans USING fts4(
            form, lexentry, tokenize={}, notindexed=lexentry
        );

        -- insert data
        INSERT INTO main.search_trans
        SELECT written_rep, lexentry
        FROM main.translation
        UNION
        SELECT other_written, lexentry
        FROM form
        WHERE lexentry IN (
            SELECT lexentry FROM main.translation
        );
    """.format(TOKENIZER[from_lang]))

    # reversed search index
    conn.executescript("""
        DROP TABLE IF EXISTS main.search_reverse_trans;
        CREATE VIRTUAL TABLE main.search_reverse_trans USING fts4(
            written_rep, trans_list, tokenize={}, notindexed=trans_list
        );
        INSERT INTO main.search_reverse_trans
        SELECT written_rep, trans_list
        FROM grouped_reverse_trans
    """.format(TOKENIZER[from_lang]))

    # optimize
    conn.execute("INSERT INTO main.search_trans(search_trans) VALUES('optimize');")
    conn.execute("INSERT INTO main.search_reverse_trans(search_reverse_trans) VALUES('optimize');")


def update_stats(conn, lang_pair):
    from_lang, to_lang = lang_pair.split('-')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wikdict.lang_pair (
            from_lang text,
            to_lang text,
            translations int,
            reverse_translations int,
            forms int,
            PRIMARY KEY (from_lang, to_lang)
        );
    """)
    conn.execute("""
        DELETE FROM wikdict.lang_pair WHERE from_lang = ? AND to_lang = ?
    """, [from_lang, to_lang])
    conn.execute("""
        INSERT INTO wikdict.lang_pair
        SELECT ?, ?,
            (SELECT count(*) FROM main.translation),
            (SELECT count(*) FROM main.search_reverse_trans),
            (SELECT count(*) FROM form)
    """, [from_lang, to_lang])


def do_steps(lang, in_path, out_path, targets, only, attach=[]):
    os.makedirs(out_path, exist_ok=True)
    conn = sqlite3.connect('%s/%s.sqlite3' % (out_path, lang))
    conn.execute(
        "ATTACH DATABASE '%s/%s.sqlite3' AS processed" % (in_path, lang))
    for a in attach:
        conn.execute(
            "ATTACH DATABASE " + a)
    conn.enable_load_extension(True)
    print('processing %s:' % lang, flush=True, end=' ')
    for name, f in targets:
        if not only or only == name:
            print(name, flush=True, end=' ')
            f(conn, lang)
    conn.commit()
    print()


def make_single(lang, only=None, **kwargs):
    do_steps(
        lang,
        in_path='dictionaries/processed',
        out_path='dictionaries/wdweb',
        targets=[
            ('display', make_display),
            ('entry', make_entry),
            ('vacuum', lambda conn, lang: conn.execute('VACUUM')),
        ],
        only=only,
    )


def make_pair(from_lang, to_lang, only=None, **kwargs):
    do_steps(
        from_lang + '-' + to_lang,
        in_path='dictionaries/processed',
        out_path='dictionaries/wdweb',
        attach=[
            "'dictionaries/processed/%s-%s.sqlite3' AS other_pair"
                % (to_lang, from_lang),
            "'dictionaries/processed/%s.sqlite3' AS other"
                % (to_lang),
            "'dictionaries/wdweb/wikdict.sqlite3' AS wikdict",
        ],
        targets=[
            ('translation', make_translation),
            ('search_index', make_search_index),
            ('vacuum', lambda conn, lang: conn.execute('VACUUM')),
            ('stats', update_stats),
        ],
        only=only,
    )


def add_subparsers(subparsers):
    process = subparsers.add_parser(
        'wdweb', help='generate lang db for wikdict-web')
    process.add_argument('lang')
    process.set_defaults(func=make_single)
    process.add_argument('--only')

    process_pair = subparsers.add_parser('wdweb_pair',
        help='generate lang pair db for wikdict-web')
    process_pair.add_argument('from_lang')
    process_pair.add_argument('to_lang')
    process_pair.set_defaults(func=make_pair)
    process_pair.add_argument('--only')
