from helper import make_targets
from infer import AggByScore


def translation(conn, lang):
    conn.execute("DROP TABLE IF EXISTS main.translation")
    conn.execute("""
        CREATE TABLE translation AS
        WITH lang_trans AS (
            SELECT lexentry, sense_num, sense,
                from_vocable AS written_rep, trans_list, score,
                score >= 20 AND lexentry IS NOT NULL AS is_good,
                from_importance * to_importance AS importance
            FROM infer.infer_grouped
            WHERE from_lang = ? AND to_lang = ?
        )
        SELECT lang_trans.*
        FROM lang_trans
        WHERE (
            -- Keep if it's good or there are no good translations for this
            -- vocable. This skips bad translations for vocables where there
            -- is at least one lexentry with a good translation
            is_good OR written_rep NOT IN (
                SELECT written_rep
                FROM lang_trans
                WHERE is_good
            )
          )
    """, lang.split('-'))
    conn.executescript("""
        DROP VIEW IF EXISTS main.translation_grouped;
        CREATE VIEW translation_grouped AS
        SELECT lexentry, written_rep, min(sense_num) AS min_sense_num,
            group_concat(sense, ' | ') AS sense_list,
            trans_list, max(score) AS score, max(importance) AS importance
        FROM (
            -- force order in group_concat
            SELECT *
            FROM translation
            ORDER BY lexentry, written_rep, trans_list, sense_num, score DESC
        )
        GROUP BY lexentry, written_rep, trans_list
    """)


def simple_translation(conn, lang):
    conn.create_aggregate("agg_by_score", 2, AggByScore)
    conn.execute("""DROP TABLE IF EXISTS simple_translation""")
    conn.execute("""
        CREATE TABLE simple_translation AS
        SELECT from_vocable AS written_rep,
            agg_by_score(to_vocable, max_score) AS trans_list,
            max(max_score) AS max_score,
            rel_importance.rel_score AS rel_importance
        FROM (
            SELECT from_vocable, to_vocable, max(score) AS max_score
            FROM infer
            WHERE (from_lang, to_lang) = (?, ?)
            GROUP BY from_vocable, to_vocable
            ORDER BY from_vocable, coalesce(min(sense_num), '999'), max(score) DESC
        ) LEFT JOIN lang.rel_importance ON (from_vocable = lang.rel_importance.written_rep_guess)
        GROUP BY from_vocable
        """, lang.split('-'))


def do(lang, sql, only, **kwargs):
    assert '-' in lang, 'No generic processing step for single lang'
    from_lang, _ = lang.split('-')
    targets = [
        ('translation', translation),
        ('simple_translation', simple_translation),
    ]

    make_targets(
        lang,
        in_path='processed',
        out_path='generic',
        targets=targets,
        attach=[
            "'dictionaries/infer.sqlite3' AS infer",
            "'dictionaries/processed/%s.sqlite3' AS lang" % (from_lang),
        ],
        sql=sql,
        only=only,
    )


def add_subparsers(subparsers):
    process = subparsers.add_parser(
        'generic', help='')
    process.add_argument('lang')
    process.set_defaults(func=do)
    process.add_argument('--sql')
    process.add_argument('--only')
