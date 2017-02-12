import re

from helper import make_targets
import parse

sense_num_re = re.compile(r'(\d+)(\w)?')


class PartOfSpeechChooser:

    def __init__(self):
        self.pos_list = []

    def step(self, value):
        self.pos_list.append(value)

    def finalize(self):
        # TODO: proper choosing of pos
        return sorted(self.pos_list)[0]


def log_exceptions(f):
    def f_with_log(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print('Error in function "{}":'.format(f.__name__))
            print(e)
            raise
    return f_with_log


@log_exceptions
def parse_sense_num(c):
    if not c:
        return None
    match = sense_num_re.match(c)
    assert match, 'Sense re does not match for %r' % c
    normalized_sense_num = '{:02d}'.format(int(match.group(1)))
    if match.group(2):
        normalized_sense_num += match.group(2)
    return normalized_sense_num


@log_exceptions
def parse_sense(sense, lang):
    if sense is None:
        return None
    sense = sense.strip()
    if sense == '':
        return None

    sense = parse.clean_wiki_syntax(sense)
    sense = parse.html_parser.parse(sense)

    # do this after syntax cleanup to make matches easier
    if parse.is_dummy_sense(sense, lang):
        return None

    return sense


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
        SELECT substr(vocable, 5) AS vocable, score
        FROM raw.importance;

        -- When searching in two languages, the more popular one will have
        -- the higher importance scores for words. To show at least some
        -- results from the less poplular language, we normalize the scores
        -- for the typeahead and similar features
        DROP VIEW IF EXISTS rel_importance;
        CREATE VIEW rel_importance AS
        SELECT vocable, score, score / high_score AS rel_score
        FROM importance, (
            SELECT avg(score) AS high_score
            FROM (
                SELECT * FROM importance
                ORDER BY score DESC LIMIT 10000
            )
        );
    """)


def make_translation(conn, lang):
    (from_lang, _) = lang.split('-')

    def parse_sense_with_lang(x):
        return parse_sense(x, from_lang)

    conn.create_function('parse_sense_num', 1, parse_sense_num)
    conn.create_function('parse_sense', 1, parse_sense_with_lang)
    conn.executescript("""
        DROP TABLE IF EXISTS main.translation;
        CREATE TABLE translation AS
        SELECT lexentry, parse_sense_num(sense_num) AS sense_num,
            sense_num AS orig_sense_num,
            parse_sense(sense) AS sense,
            trans
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
