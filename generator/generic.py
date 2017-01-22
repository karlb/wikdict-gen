from helper import make_targets


def translation(conn, lang):
    conn.execute("DROP TABLE IF EXISTS main.translation")
    conn.execute("""
        CREATE TABLE translation AS
        WITH lang_trans AS (
            SELECT lexentry, sense_num, sense,
                from_vocable AS written_rep, trans_list, score,
                score >= 20 AND lexentry IS NOT NULL AS is_good
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
