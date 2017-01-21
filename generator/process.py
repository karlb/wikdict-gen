from helper import make_targets


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
        SELECT lexentry, written_rep, part_of_speech, gender,
            group_concat(pronun, ' | ') AS pronun_list
        FROM raw.entry
            LEFT JOIN raw.pos USING (lexentry)
            LEFT JOIN raw.gender USING (lexentry)
            LEFT JOIN raw.pronun USING (lexentry)
        GROUP BY lexentry;
--        SELECT lexentry, written_rep, choose_pos(part_of_speech) AS part_of_speech,
--            CASE
--                WHEN min(gender) == max(gender) THEN gender
--                ELSE NULL
--            END AS gender,
--            pronun_list
--        FROM raw.entry
--        WHERE written_rep is NOT NULL
--          AND written_rep != ''
--        GROUP BY lexentry;
        CREATE UNIQUE INDEX entry_pkey ON entry(lexentry);
    """)


def make_form(conn, lang):
    conn.executescript("""
        DROP TABLE IF EXISTS main.form;
        CREATE TABLE form AS
        SELECT *
        FROM raw.form
    """)


def make_importance(conn, lang):
    conn.executescript("""
        DROP TABLE IF EXISTS main.importance;
        CREATE TABLE importance AS
        SELECT *
        FROM raw.importance
    """)


def make_translation(conn, lang):
    conn.executescript("""
        DROP TABLE IF EXISTS main.translation;
        CREATE TABLE translation AS
        SELECT *
        FROM raw.translation
    """)


def do(lang, only, sql, **kwargs):
    if '-' not in lang:
        targets = [
            ('entry', make_entry),
            ('form', make_form),
            ('importance', make_importance),
        ]
    else:
        targets = [
            ('translation', make_translation),
        ]

    make_targets(
        lang,
        in_path='raw',
        out_path='processed',
        targets=targets,
        only=only,
        sql=sql,
    )


def add_subparsers(subparsers):
    process = subparsers.add_parser(
        'process', help='process raw db into a new processed db')
    process.add_argument('lang')
    process.set_defaults(func=do)
    process.add_argument('--only')
    process.add_argument('--sql')
