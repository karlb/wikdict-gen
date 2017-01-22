from collections import defaultdict

from helper import make_targets


TOKENIZER = defaultdict(lambda: 'unicode61', {
    'en': 'porter'
})


def apply_views(conn, view_file='views.sql'):
    with open(view_file) as f:
        f.readline()  # skip first line
        conn.executescript(f.read())


def make_vocable(conn, lang):
    conn.executescript("""
        DROP TABLE IF EXISTS main.vocable;
        CREATE TABLE main.vocable AS
        SELECT DISTINCT
            written_rep,
            lower(written_rep) AS written_lower
        FROM processed.entry;
        CREATE INDEX vocable_lower_idx ON vocable(written_lower);
    """)


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
        DROP TABLE IF EXISTS main.translation;
        CREATE TABLE main.translation AS
        SELECT lexentry, written_rep, part_of_speech, sense_list,
               min_sense_num, trans_list,
               translation_grouped.score AS translation_score
        FROM translation_grouped 
            LEFT JOIN (
                SELECT lexentry, part_of_speech
                FROM entry
            ) USING (lexentry)
        ORDER BY lexentry, min_sense_num;
        --CREATE INDEX main.translation_lexentry_idx ON translation('lexentry');
        CREATE INDEX main.translation_written_rep_idx ON translation('written_rep');
    """)


def make_search_index(conn, lang_pair):
    from_lang, _ = lang_pair.split('-')

    # main search index
    conn.executescript("""
        -- search table
        DROP TABLE IF EXISTS main.search_trans;
        CREATE VIRTUAL TABLE main.search_trans USING fts4(
            form, written_rep, tokenize={}, notindexed=written_rep
        );

        -- insert data
        INSERT INTO main.search_trans
        SELECT written_rep, written_rep
        FROM main.translation
        UNION
        SELECT other_written, written_rep
        FROM form
            JOIN entry USING (lexentry)
        WHERE written_rep IN (
            SELECT written_rep FROM main.translation
        );
    """.format(TOKENIZER[from_lang]))

    # optimize
    conn.execute(
        "INSERT INTO main.search_trans(search_trans) VALUES('optimize');")


def update_stats(conn, lang_pair):
    from_lang, to_lang = lang_pair.split('-')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wikdict.lang_pair (
            from_lang text,
            to_lang text,
            translations int,
            forms int,
            PRIMARY KEY (from_lang, to_lang)
        );
    """)
    conn.execute("""
        DELETE FROM wikdict.lang_pair WHERE from_lang = ? AND to_lang = ?
    """, [from_lang, to_lang])
    conn.execute("""
        INSERT INTO wikdict.lang_pair(from_lang, to_lang, translations, forms)
        SELECT ?, ?,
            (SELECT count(*) FROM main.translation),
            (SELECT count(*) FROM form)
    """, [from_lang, to_lang])


def do(lang, only, sql, **kwargs):
    if '-' not in lang:
        attach = []
        targets = [
            ('vocable', make_vocable),
            ('display', make_display),
            ('entry', make_entry),
            ('vacuum', lambda conn, lang: conn.execute('VACUUM')),
        ]
        in_path = 'processed'
    else:
        (from_lang, to_lang) = lang.split('-')
        attach = [
            "'dictionaries/generic/%s-%s.sqlite3' AS other_pair" % (
                to_lang, from_lang),
            "'dictionaries/processed/%s.sqlite3' AS lang" % (from_lang),
            "'dictionaries/processed/%s.sqlite3' AS other" % (to_lang),
            "'dictionaries/wdweb/wikdict.sqlite3' AS wikdict",
        ]
        targets = [
            ('translation', make_translation),
            ('search_index', make_search_index),
            ('vacuum', lambda conn, lang: conn.execute('VACUUM')),
            ('stats', update_stats),
        ]
        in_path = 'generic'

    make_targets(
        lang,
        in_path=in_path,
        out_path='wdweb',
        attach=attach,
        targets=targets,
        only=only,
        sql=sql,
    )


def add_subparsers(subparsers):
    process = subparsers.add_parser(
        'wdweb', help='generate lang db for wikdict-web')
    process.add_argument('lang')
    process.set_defaults(func=do)
    process.add_argument('--only')
    process.add_argument('--sql')
