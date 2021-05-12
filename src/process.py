import re

from helper import make_targets
import parse

sense_num_re = re.compile(r'(\d+)(\w)?')


CONJUGATION_TABLES = {
    'de': """
        INSERT INTO conjugation_table (rank, mood, number, person, tense, voice) VALUES
            (1, 'IndicativeMood', 'Singular', 'First', 'Present', 'ActiveVoice'),
            (2, 'IndicativeMood', 'Singular', 'Second', 'Present', 'ActiveVoice'),
            (3, 'IndicativeMood', 'Singular', 'Third', 'Present', 'ActiveVoice'),
            (4, 'IndicativeMood', 'Singular', 'First', 'Past', 'ActiveVoice'),
            (5, 'SubjunctiveMood', 'Singular', 'First', 'Past', 'ActiveVoice'),
            (6, 'ImperativeMood', 'Singular', 'Second', 'Present', 'ActiveVoice'),
            (7, 'ImperativeMood', 'Plural', 'Second', 'Present', 'ActiveVoice'),
            (8, 'IndicativeMood', 'Singular', 'First', 'Perfect', 'ActiveVoice');
    """,
    'en': """
        INSERT INTO conjugation_table (rank, mood, number, person, tense) VALUES
            -- (1, NULL, 'Singular', 'Third', 'Present'),
            -- (2, 'Participle', NULL, NULL, 'Present'),
            (3, NULL, NULL, NULL, 'Past'),
            (4, 'Participle', NULL , NULL, 'Past');
    """,
    'sv': """
        INSERT INTO conjugation_table (rank, mood, tense, voice, tense_name) VALUES
            (1, NULL, 'Past', 'ActiveVoice', 'Preteritum'),
            (2, NULL, 'Supine', 'ActiveVoice', 'Supinum'),
            (3, 'ImperativeMood', NULL, 'ActiveVoice', 'Imperativ'),
            (4, NULL, 'Present', 'ActiveVoice', 'Presens');
    """
}


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
    if lang == 'sv':
        # Swedish has the gender attributed to the forms. Fill the gender table from there.
        conn.executescript("""
            DROP TABLE IF EXISTS main.gender;
            CREATE TABLE main.gender AS SELECT DISTINCT lexentry, gender FROM raw.form;
        """);

    conn.create_aggregate("choose_pos", 1, PartOfSpeechChooser)
    conn.executescript("""
        DROP TABLE IF EXISTS main.entry;
        CREATE TABLE entry AS
        SELECT lexentry, vocable, written_rep, part_of_speech, gender,
            group_concat(pronun, ' | ') AS pronun_list
        FROM raw.entry
            LEFT JOIN raw.pos USING (lexentry)
            LEFT JOIN (
                SELECT lexentry,
                    CASE
                        WHEN min(gender) == max(gender) THEN gender
                    END AS gender
                FROM gender
                GROUP BY lexentry
            ) USING (lexentry)
            LEFT JOIN raw.pronun USING (lexentry)
        -- Actually, I only want to group by lexentry. But by combinding this
        -- grouping with a unique index, we'll get an error if the result is
        -- ambiguous.
        -- TODO: enable this check and resolve the problems
        --GROUP BY 1, 2, 3,4;
        GROUP BY lexentry;
        CREATE UNIQUE INDEX entry_pkey ON entry(lexentry);

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
    """)


def make_form(conn, lang):
    conn.create_function('clean_wiki_syntax', 1, parse.clean_wiki_syntax)
    conn.create_function('clean_html', 1, parse.html_parser.parse)
    conn.create_function('clean_conjugation', 1, parse.make_conjugation_cleaner(lang))
    conn.create_function('clean_inflection', 1, parse.make_inflection_cleaner(lang))
    conn.executescript("""
        DROP TABLE IF EXISTS main.form;
        CREATE TABLE form AS
        SELECT *,
            clean_inflection(other_written_full) AS other_written
        FROM (
            SELECT lexentry,
                clean_wiki_syntax(clean_html(other_written)) AS other_written_full,
                pos,
                form.mood, form.number, form.person, form.tense, form.voice,
                "case", inflection, c.rank
            FROM raw.form
                LEFT JOIN conjugation_table c ON (
                    form.mood IS c.mood
                    AND form.number IS c.number
                    AND form.person IS c.person
                    AND form.tense IS c.tense
                    AND form.voice IS c.voice
                )
        )
    """)


def make_importance(conn, lang):
    conn.executescript("""
        DROP TABLE IF EXISTS main.importance;
        CREATE TABLE importance AS
        -- The input data should already be distinct, but Virtuoso fails to do
        -- a proper GROUP BY for some texts like 'eng/??', so we need to group
        -- here, again.
        SELECT vocable, avg(score) AS score,
           -- TODO: This is an ugly hack. A vocable/page does not have a single
           --       representation. Case might be different, probably other
           --       things, too.
           replace(substr(vocable, 5), '_', ' ') AS written_rep_guess
        FROM raw.importance
        GROUP BY vocable;
        CREATE UNIQUE INDEX imp_unique_rep ON importance(written_rep_guess);

        -- When searching in two languages, the more popular one will have
        -- the higher importance scores for words. To show at least some
        -- results from the less poplular language, we normalize the scores
        -- for the typeahead and similar features
        DROP VIEW IF EXISTS rel_importance;
        CREATE VIEW rel_importance AS
        SELECT vocable, score, score / high_score AS rel_score, written_rep_guess
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
    conn.create_function('clean_wiki_syntax', 1, parse.clean_wiki_syntax)
    # The outer query removes duplicates in the case of different lexentries
    # with the same translation and sense. E.g. for transitive and intransitive
    # variants of a vocable which both map to the same translation.
    conn.executescript("""
        DROP TABLE IF EXISTS main.translation;
        CREATE TABLE translation AS
        SELECT min(lexentry) AS lexentry, sense_num, sense, written_rep, trans,
            max(from_importance) AS from_importance, max(to_importance) AS to_importance,
            json_group_array(lexentry) AS all_lexentries
        FROM (
            SELECT lexentry, parse_sense_num(sense_num) AS sense_num,
                sense_num AS orig_sense_num,
                parse_sense(sense) AS sense,
                written_rep,
                clean_wiki_syntax(trans) AS trans,
                from_imp.rel_score AS from_importance,
                coalesce(to_imp.rel_score, 0.001) AS to_importance
            FROM raw.translation
                JOIN lang.entry USING (lexentry)
                JOIN lang.rel_importance from_imp USING (vocable)
                -- TODO: the join condition is an ugly hack, and slow!
                LEFT JOIN other_lang.rel_importance to_imp ON (trans = to_imp.written_rep_guess)
        )
        WHERE trans != ''
        GROUP BY sense_num, sense, written_rep, trans;
    """)


def make_conjugation_table(conn, lang):
    conn.executescript("""
        DROP TABLE IF EXISTS conjugation_table;
        CREATE TABLE conjugation_table(
            rank, mood, number, person, tense, voice, tense_name);
    """)

    if lang in CONJUGATION_TABLES:
        conn.executescript(CONJUGATION_TABLES[lang])


def do(lang, only, sql, **kwargs):
    if '-' not in lang:
        targets = [
            ('entry', make_entry),
            ('conjugation_table', make_conjugation_table),
            ('form', make_form),
            ('importance', make_importance),
        ]
        attach = []
    else:
        (from_lang, to_lang) = lang.split('-')
        targets = [
            ('translation', make_translation),
        ]
        attach = [
            "'dictionaries/processed/%s.sqlite3' AS lang" % (from_lang),
            "'dictionaries/processed/%s.sqlite3' AS other_lang" % (to_lang),
        ]

    make_targets(
        lang,
        in_path='raw',
        out_path='processed',
        targets=targets,
        attach=attach,
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
