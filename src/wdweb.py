from collections import defaultdict
import json

from helper import make_targets


TOKENIZER = defaultdict(lambda: "unicode61", {"en": "porter"})


def make_vocable(conn, lang):
    conn.executescript(
        """
        DROP TABLE IF EXISTS main.vocable;
        CREATE TABLE main.vocable AS
        SELECT DISTINCT
            written_rep,
            lower(written_rep) AS written_lower
        FROM processed.entry;
        CREATE INDEX vocable_lower_idx ON vocable(written_lower);
    """
    )


def make_entry(conn, lang):
    conn.load_extension("lib/spellfix1")
    conn.executescript(
        """
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
            score * score * score AS rank  -- increase weight of rank over distance
        FROM main.entry
            JOIN (
                SELECT substr(vocable, 5) AS written_rep,
                       rel_score * 100 AS score
                FROM rel_importance
            ) USING (written_rep)
    """
    )


def make_display(conn, lang):
    conn.execute("DROP TABLE IF EXISTS main.lexentry_display")
    if lang == "de":
        conn.execute(
            """
            CREATE TABLE lexentry_display AS
            WITH noun AS (
                SELECT lexentry, other_written, number
                FROM processed.form
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
        """
        )
    else:
        conn.execute(
            """
            CREATE TABLE lexentry_display AS
            SELECT '' AS lexentry, '' AS display, '' AS display_addition
        """
        )


def make_translation(conn, lang_pair):
    conn.executescript(
        """
        DROP TABLE IF EXISTS main.translation;
        CREATE TABLE main.translation AS
        SELECT lexentry, written_rep, part_of_speech, sense_list,
               min_sense_num, trans_list,
               translation_grouped.score AS translation_score,
               importance
        FROM translation_grouped 
            LEFT JOIN (
                SELECT lexentry, part_of_speech
                FROM entry
            ) USING (lexentry)
        ORDER BY lexentry, min_sense_num;
        --CREATE INDEX main.translation_lexentry_idx ON translation('lexentry');
        CREATE INDEX main.translation_written_rep_idx ON translation('written_rep');
    """
    )


def _list_to_array(pipe_list):
    """Convert a pipe separated list into a json array"""
    if pipe_list is None:
        return
    return json.dumps(pipe_list.split(" | "))


def make_translation_block(conn, lang_pair):
    """Combine all information for a bilingual dict entry in a single row"""
    conn.create_function("list_to_array", 1, _list_to_array)

    # Improved speed in following queries
    conn.executescript(
        """
        CREATE TEMPORARY TABLE translation_grouped AS
        SELECT * FROM generic.translation_grouped;

        CREATE INDEX temp.translation_grouped_written_rep_idx ON translation_grouped(written_rep);
    """
    )

    conn.executescript(
        """
        DROP TABLE IF EXISTS idioms;
        CREATE VIRTUAL TABLE main.idioms USING fts4(
            written_rep, translations, importance,
            notindexed=translations, notindexed=importance
        );
        INSERT INTO idioms
        SELECT written_rep,
            (
                SELECT json_group_array (DISTINCT json_each.value)
                FROM json_each(list_to_array(group_concat(trans_list, ' | ')))
            ) AS translations,
            sum(score * importance) AS importance
        FROM translation_grouped
        GROUP BY written_rep;
    """
    )

    conn.executescript(
        """
        DROP TABLE IF EXISTS main.translation_block;
        CREATE TABLE main.translation_block AS
        SELECT *, 
            grouped_forms.forms AS forms
        FROM (
            SELECT
                lexentry,
                written_rep,
                part_of_speech,
                gender,
                list_to_array(pronun_list) AS pronuns,
                sense_groups,
                --min_sense_num,
                translation_score,
                importance
            FROM
                (
                    SELECT lexentry, written_rep,
                        json_group_array(json_object(
                            'senses', json(list_to_array(sense_list)),
                            'translations', json(list_to_array(trans_list))
                        )) AS sense_groups,
                        max(score) AS translation_score,
                        max(importance) AS importance
                    FROM (
                        SELECT *
                        FROM translation_grouped
                        ORDER BY lexentry, score DESC
                    )
                    GROUP BY lexentry, written_rep
                ) translation_grouped 
                LEFT JOIN (
                    SELECT lexentry, part_of_speech, gender, pronun_list
                    FROM entry
                ) USING (lexentry)
            GROUP BY lexentry, written_rep, part_of_speech, gender, pronun_list
        ) t
        LEFT JOIN (
            SELECT lexentry, json_group_array(other_written) AS forms
            FROM (
                SELECT lexentry, group_concat(other_written, '/') AS other_written
                FROM (
                    SELECT lexentry, other_written, min(rank) AS rank
                    FROM form
                    WHERE rank IS NOT NULL
                    GROUP BY lexentry, other_written
                )
                GROUP BY lexentry, rank
                ORDER BY rank
            )
            GROUP BY lexentry
        ) grouped_forms USING (lexentry);

        CREATE INDEX main.translation_block_written_rep_idx ON translation_block('written_rep');
    """
    )


def make_simple_translation(conn, lang_pair):
    conn.executescript(
        """
        DROP TABLE IF EXISTS main.simple_translation;

        CREATE TABLE main.simple_translation AS
        SELECT written_rep COLLATE NOCASE,
            trans_list, max_score, rel_importance
        FROM generic.simple_translation
        ORDER BY max_score * rel_importance DESC;

        CREATE INDEX main.simple_translation_index
            ON simple_translation('written_rep');
    """
    )


def make_search_index(conn, lang_pair):
    from_lang, _ = lang_pair.split("-")

    # main search index
    conn.executescript(
        """
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
    """.format(
            TOKENIZER[from_lang]
        )
    )

    # optimize
    conn.execute("INSERT INTO main.search_trans(search_trans) VALUES('optimize');")


def make_search_by_form(conn, lang_pair):
    from_lang, _ = lang_pair.split("-")

    conn.executescript(
        """
        -- search table
        DROP TABLE IF EXISTS main.search_by_form;
        CREATE VIRTUAL TABLE main.search_by_form USING fts4(
            form, translation_block_rowid, form_importance, tokenize={},
            notindexed=translation_block_rowid,
            notindexed=form_importance
        );

        -- insert data
        INSERT INTO main.search_by_form
        SELECT other_written, translation_block.rowid, 0.5 AS form_importance
        FROM translation_block
            JOIN form USING (lexentry)
        UNION
        SELECT written_rep, translation_block.rowid, 1 AS form_importance
        FROM translation_block;
    """.format(
            TOKENIZER[from_lang]
        )
    )

    # optimize
    conn.execute("INSERT INTO main.search_trans(search_trans) VALUES('optimize');")


def update_stats(conn, lang_pair):
    from_lang, to_lang = lang_pair.split("-")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wikdict.lang_pair (
            from_lang text,
            to_lang text,
            translations int,
            forms int,
            score int,
            PRIMARY KEY (from_lang, to_lang)
        );
    """
    )
    conn.execute(
        """
        DELETE FROM wikdict.lang_pair WHERE from_lang = ? AND to_lang = ?
    """,
        [from_lang, to_lang],
    )
    conn.execute(
        """
        INSERT INTO wikdict.lang_pair(from_lang, to_lang,
            translations, forms, score)
        SELECT ?, ?, translations,
            (SELECT count(*) FROM form), round(score)
        FROM (
            SELECT count(*) AS translations,
                sum(translation_score) AS score
            FROM main.translation
        )
    """,
        [from_lang, to_lang],
    )


def do(lang, only, sql, **kwargs):
    if "-" not in lang:
        attach = []
        targets = [
            ("vocable", make_vocable),
            ("display", make_display),
            ("entry", make_entry),
        ]
        in_path = "processed"
    else:
        (from_lang, to_lang) = lang.split("-")
        attach = [
            "'dictionaries/generic/%s-%s.sqlite3' AS other_pair" % (to_lang, from_lang),
            "'dictionaries/processed/%s.sqlite3' AS lang" % (from_lang),
            "'dictionaries/processed/%s.sqlite3' AS other" % (to_lang),
            "'dictionaries/wdweb/wikdict.sqlite3' AS wikdict",
        ]
        targets = [
            ("translation", make_translation),
            ("simple_translation", make_simple_translation),
            ("search_index", make_search_index),
            ("translation_block", make_translation_block),
            ("search_by_form", make_search_by_form),
            ("stats", update_stats),
        ]
        in_path = "generic"

    make_targets(
        lang,
        in_path=in_path,
        out_path="wdweb",
        attach=attach,
        targets=targets,
        only=only,
        sql=sql,
    )


def add_subparsers(subparsers):
    process = subparsers.add_parser("wdweb", help="generate lang db for wikdict-web")
    process.add_argument("lang")
    process.set_defaults(func=do)
    process.add_argument("--only")
    process.add_argument("--sql")
