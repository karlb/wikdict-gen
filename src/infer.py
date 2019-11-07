import sqlite3

from helper import make_targets


def collect(conn, lang):
    (from_lang, to_lang) = lang.split('-')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS all_trans(
            from_lang text NOT NULL,
            to_lang text NOT NULL,
            lexentry text,
            sense_num text,
            sense text NOT NULL,
            from_vocable text NOT NULL,
            to_vocable text NOT NULL,
            from_importance float NOT NULL,
            to_importance floa NOT NULL
        );
    """)
    conn.execute("""
        DELETE FROM all_trans
        WHERE from_lang = ? AND to_lang = ?
    """, [from_lang, to_lang])
    conn.execute("""
        INSERT INTO all_trans
        SELECT ?, ?, lexentry, sense_num, coalesce(sense, ''),
            written_rep, trans, from_importance, to_importance
        FROM processed.translation
    """, [from_lang, to_lang])


class AggByScore:

    def __init__(self):
        self.trans_list = []

    def step(self, trans, score):
        self.trans_list.append((trans, score))

    def finalize(self):
        result = []
        min_score = 0
        trans_list = sorted(self.trans_list, key=lambda x: -x[1])
        for trans, score in trans_list:
            if score >= min_score:
                result.append(trans)
            else:
                break
            min_score += 20
        return ' | '.join(result)


def infer(**kwargs):
    conn = sqlite3.connect('dictionaries/infer.sqlite3')
    conn.create_aggregate("agg_by_score", 2, AggByScore)
    conn.executescript(open('infer.sql').read())


def do(lang, sql, **kwargs):
    (from_lang, _) = lang.split('-')
    targets = [
        ('collect', collect),
    ]

    make_targets(
        lang,
        in_path='processed',
        out_path='infer.sqlite3',
        targets=targets,
        attach=["'dictionaries/processed/%s.sqlite3' AS lang" % from_lang],
        sql=sql,
    )


def add_subparsers(subparsers):
    process = subparsers.add_parser(
        'infer-collect', help='')
    process.add_argument('lang')
    process.set_defaults(func=do)
    process.add_argument('--sql')

    process = subparsers.add_parser(
        'infer', help='')
    process.set_defaults(func=infer)
