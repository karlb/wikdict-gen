import re

from helper import make_targets
from parse import html_parser, clean_wiki_syntax

sense_num_re = re.compile(r'(\d+)(\w)?')


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
    if c == '':
        return None
    match = sense_num_re.match(c)
    assert match, 'Sense re does not match for %r' % c
    normalized_sense_num = '{:02d}'.format(int(match.group(1)))
    if match.group(2):
        normalized_sense_num += match.group(2)
    return normalized_sense_num


@log_exceptions
def parse_sense(sense):
    if sense is None:
        return None
    sense = sense.strip()
    if sense == '':
        return None

    sense = html_parser.parse(sense)
    sense = clean_wiki_syntax(sense)
    return sense


def translation(conn, lang):
    conn.create_function('parse_sense_num', 1, parse_sense_num)
    conn.create_function('parse_sense', 1, parse_sense)
    conn.execute("DROP TABLE IF EXISTS main.translation")
    conn.execute("""
        CREATE TABLE translation AS
        WITH lang_trans AS (
            SELECT lexentry, parse_sense_num(sense_num) AS sense_num,
                sense_num AS orig_sense_num,
                parse_sense(sense) AS sense,
                from_vocable AS written_rep, trans_list, score
            FROM infer.infer_grouped
            WHERE from_lang = ? AND to_lang = ?
        )
        SELECT lang_trans.*
        FROM lang_trans
        WHERE (
            -- Keep if it's good or the only translation
            score >= 10 OR
            written_rep IN (
                SELECT written_rep
                FROM lang_trans
                GROUP BY lexentry
                HAVING count(*) == 1
            )
          )
    """, lang.split('-'))
    conn.executescript("""
        DROP VIEW IF EXISTS main.translation_grouped;
        CREATE VIEW translation_grouped AS
        SELECT lexentry, written_rep, min(sense_num) AS min_sense_num,
            group_concat(sense, ' | ') AS sense_list,
            trans_list, max(score) AS score
        FROM (
            -- force order in group_concat
            SELECT *
            FROM translation
            ORDER BY lexentry, written_rep, trans_list, sense_num, score DESC
        )
        GROUP BY lexentry, written_rep, trans_list
    """)


def do(lang, sql, **kwargs):
    (from_lang, to_lang) = lang.split('-')
    targets = [
        ('translation', translation),
    ]

    make_targets(
        lang,
        in_path='processed',
        out_path='generic',
        targets=targets,
        attach=["'dictionaries/infer.sqlite3' AS infer"],
        sql=sql,
    )


def add_subparsers(subparsers):
    process = subparsers.add_parser(
        'generic', help='')
    process.add_argument('lang')
    process.set_defaults(func=do)
    process.add_argument('--sql')
