DROP VIEW IF EXISTS indirect;
CREATE VIEW indirect AS
SELECT t1.from_lang, t2.to_lang, 'indirect' AS source,
    group_concat(DISTINCT t1.to_lang ||
        CASE WHEN backlink.to_lang IS NOT NULL THEN '+' ELSE '' END ||
        ':' || t1.to_vocable) AS source_detail,
    t1.from_vocable, t2.to_vocable,
    t1.lexentry, t1.sense_num, t1.sense,
    count(DISTINCT t1.to_lang) + count(DISTINCT backlink.from_lang) * 4 AS score
FROM all_trans t1
    JOIN all_trans t2 ON (
        t1.to_lang = t2.from_lang AND
        t1.to_vocable = t2.from_vocable
    )
    LEFT JOIN all_trans backlink ON (
        -- When the intermediate language has a sense with a translation
        -- back to the original word, then translations of this sense to
        -- the target language are much better.
        backlink.from_lang = t1.to_lang AND
        backlink.to_lang = t1.from_lang AND
        backlink.to_vocable = t1.from_vocable AND
        backlink.sense = t2.sense
    )
-- Translating from a language to itself makes no sense, but it's great for debugging!
--WHERE t1.from_lang != t2.to_lang
GROUP BY t1.from_lang, t2.to_lang, t1.from_vocable, t2.to_vocable,
    t1.lexentry, t1.sense_num, t1.sense;


DROP VIEW IF EXISTS direct;
CREATE VIEW direct AS
SELECT from_lang, to_lang, 'direct' AS source,
    null AS source_detail,
    from_vocable, to_vocable,
    lexentry, sense_num, sense,
    20 AS score
FROM all_trans;


DROP VIEW IF EXISTS direct_reverse;
CREATE VIEW direct_reverse AS
SELECT to_lang AS from_lang, from_lang AS to_lang, 'direct_reverse' AS source,
    null AS source_detail,
    to_vocable AS from_vocable, from_vocable AS to_vocable,
    null AS lexentry, null AS sense_num, null AS sense,
    2 AS score
FROM all_trans;


DROP VIEW IF EXISTS all_inputs;
CREATE VIEW all_inputs AS
SELECT * FROM direct
UNION ALL
SELECT * FROM indirect
UNION ALL
SELECT * FROM direct_reverse
;


DROP TABLE IF EXISTS infer;
CREATE TABLE infer AS
SELECT from_lang, to_lang, lexentry, sense_num, sense,
    from_vocable, to_vocable,
    group_concat(source) AS sources,
    group_concat(source_detail) AS source_details,
    sum(score) AS score
FROM all_inputs
GROUP BY from_lang, to_lang, lexentry, sense_num, sense,
    from_vocable, to_vocable ;


DROP TABLE IF EXISTS infer_grouped;
CREATE TABLE infer_grouped AS
SELECT from_lang, to_lang, lexentry, sense_num, sense,
    from_vocable, agg_by_score(to_vocable, score) AS trans_list,
    max(score) AS score
FROM infer
GROUP BY from_lang, to_lang, lexentry, sense_num, sense, from_vocable;
