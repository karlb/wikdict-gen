DROP VIEW IF EXISTS backlink_full;
CREATE VIEW backlink_full AS
SELECT trans.from_lang, trans.to_lang,
    trans.from_vocable AS from_vocable, trans.to_vocable AS to_vocable,
    trans.sense AS trans_sense, back.sense AS back_sense,
    count(CASE WHEN back.to_vocable = trans.from_vocable THEN 1 END) AS good_backlinks,
    count(back.from_vocable) AS all_backlinks
FROM all_trans trans
    JOIN all_trans back ON (
        trans.from_lang = back.to_lang AND
        trans.to_lang = back.from_lang AND
        trans.to_vocable = back.from_vocable
    )
GROUP BY trans.from_lang, trans.to_lang, trans.from_vocable, trans.to_vocable,
    trans.sense, back.sense;


DROP TABLE IF EXISTS backlink_score;
CREATE TABLE backlink_score AS
SELECT from_lang, to_lang, from_vocable, to_vocable, back_sense,
    max(cast(good_backlinks AS float) / all_backlinks) AS backlink_score
FROM backlink_full
GROUP BY from_lang, to_lang, from_vocable, to_vocable, back_sense;


DROP TABLE IF EXISTS indirect;
CREATE TABLE indirect AS
SELECT t1.from_lang, t2.to_lang, 'indirect' AS source,
    t1.to_lang || CASE
            WHEN backlink_score = 1 THEN '+'
            WHEN backlink_score < 1 THEN '-'
            ELSE ''
        END || ':' || t1.to_vocable AS source_detail,
    t1.from_vocable, t2.to_vocable,
    t1.lexentry, t1.sense_num, t1.sense,
    coalesce(round(max(backlink_score * backlink_score) * 10, 1), 1) AS score,
    t1.from_importance, t2.to_importance
FROM all_trans t1
    JOIN all_trans t2 ON (
        t1.to_lang = t2.from_lang AND
        t1.to_vocable = t2.from_vocable
    )
    LEFT JOIN backlink_score backlink ON (
        -- When the intermediate language has a sense with a translation
        -- back to the original word, then translations of this sense to
        -- the target language are much better.
        backlink.from_lang = t1.from_lang AND
        backlink.to_lang = t1.to_lang AND
        backlink.from_vocable = t1.from_vocable AND
        backlink.to_vocable = t1.to_vocable AND
        backlink.back_sense = t2.sense
    )
-- Translating from a language to itself makes no sense, but it's great for debugging!
--WHERE t1.from_lang != t2.to_lang
GROUP BY t1.from_lang, t2.to_lang, t1.from_vocable, t2.to_vocable, t1.to_lang,
    t1.lexentry, t1.sense_num, t1.sense;


DROP VIEW IF EXISTS direct;
CREATE VIEW direct AS
SELECT from_lang, to_lang, 'direct' AS source,
    null AS source_detail,
    from_vocable, to_vocable,
    lexentry, sense_num, sense,
    100 AS score,
    from_importance, to_importance
FROM all_trans;


DROP VIEW IF EXISTS direct_reverse;
CREATE VIEW direct_reverse AS
SELECT to_lang AS from_lang, from_lang AS to_lang, 'direct_reverse' AS source,
    null AS source_detail,
    to_vocable AS from_vocable, from_vocable AS to_vocable,
    null AS lexentry, null AS sense_num, null AS sense,
    2 AS score,
    from_importance, to_importance
FROM all_trans;


DROP TABLE IF EXISTS with_lexentry;
CREATE TABLE with_lexentry AS
SELECT * FROM direct
UNION ALL
SELECT * FROM indirect;
CREATE INDEX w_lex_idx  ON with_lexentry(from_lang, to_lang, from_vocable, to_vocable);


DROP VIEW IF EXISTS all_inputs;
CREATE VIEW all_inputs AS
SELECT *
FROM with_lexentry
UNION ALL
SELECT * FROM (
    SELECT * FROM direct_reverse r
    -- Only keep translations with lexentry if translations both with and
    -- without lexentry are available.
    WHERE NOT EXISTS (
        SELECT 1
        FROM with_lexentry l
        WHERE (l.from_lang, l.to_lang, l.from_vocable, l.to_vocable) =
            (r.from_lang, r.to_lang, r.from_vocable, r.to_vocable)
    )
);


DROP TABLE IF EXISTS infer;
CREATE TABLE infer AS
SELECT from_lang, to_lang, lexentry, sense_num, nullif(sense, '') AS sense,
    from_vocable, to_vocable,
    group_concat(source) AS sources,
    group_concat(source_detail) AS source_details,
    sum(score) AS score,
    from_importance, to_importance
FROM all_inputs
GROUP BY from_lang, to_lang, lexentry, sense_num, sense,
    from_vocable, to_vocable, from_importance, to_importance;
/* TODO: The following constraint should be ok, but there's still a few violations. */
/* CREATE UNIQUE INDEX infer_pkey ON infer(from_lang, to_lang, lexentry, */
/*     sense, from_vocable, to_vocable); */
CREATE INDEX infer_from_to_idx ON infer(from_lang, to_lang);


DROP TABLE IF EXISTS infer_grouped;
CREATE TABLE infer_grouped AS
SELECT from_lang, to_lang, lexentry, sense_num, sense,
    from_vocable, agg_by_score(to_vocable, score) AS trans_list,
    max(score) AS score,
    from_importance, to_importance
FROM infer
GROUP BY from_lang, to_lang, lexentry, sense_num, sense, from_vocable;
