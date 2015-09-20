.shell clear

DROP VIEW IF EXISTS lexentry_display;
CREATE VIEW lexentry_display AS
WITH noun AS (
	SELECT lexentry, other_written, number
	FROM form
	WHERE pos = 'noun'
          AND "case" = 'Nominative'
          AND inflection = 'WeakInflection'
)
SELECT lexentry, singular AS main, 'Pl.: ' || plural AS addition
FROM (
	SELECT lexentry, other_written AS singular
	FROM noun
	WHERE number = 'Singular'
) JOIN (
	SELECT lexentry, other_written AS plural
	FROM noun
	WHERE number = 'Plural'
) USING (lexentry);


-- Build a list of translations by using the translations from the other language and reversing the translation order
DROP VIEW IF EXISTS main.reverse_trans;
CREATE TEMP VIEW reverse_trans AS
SELECT trans AS written_rep, written_rep AS trans, min(sense_num) AS min_sense_num
FROM other_pair.translation
     JOIN other.entry USING (lexentry)
GROUP BY trans, written_rep;


-- Remove those entries from reverse_trans which are already included in the original translations
DROP VIEW IF EXISTS reverse_trans_no_duplicates;
CREATE TEMP VIEW reverse_trans_no_duplicates AS
SELECT *
FROM reverse_trans
     LEFT JOIN (
        SELECT written_rep, trans
        FROM translation
             JOIN entry USING (lexentry)
     ) orig USING (written_rep, trans)
WHERE orig.written_rep IS NULL
;


DROP VIEW IF EXISTS grouped_reverse_trans;
CREATE TEMP VIEW grouped_reverse_trans AS
SELECT written_rep, group_concat(trans, ' | ') AS trans_list
FROM (
    SELECT *
    FROM reverse_trans_no_duplicates
    ORDER BY min_sense_num
)
GROUP BY 1
;


--SELECT count(*)
--FROM reverse_trans;

--SELECT count(*)
--FROM reverse_trans_no_duplicates;

DROP VIEW IF EXISTS merged_translation;
CREATE TEMP VIEW merged_translation AS
SELECT DISTINCT lexentry, written_rep, trans, sense, sense_num 
FROM translation
     JOIN entry USING (lexentry)
UNION ALL
SELECT NULL, written_rep, trans, NULL, NULL
FROM reverse_trans_no_duplicates;


--SELECT * FROM merged_translation
--ORDER BY written_rep
--LIMIT 10;

--SELECT written_rep, count(*)
--FROM merged_translation
--GROUP BY 1
--ORDER BY 2 DESC
--LIMIT 20;

--SELECT lexentry, written_rep, sense, sense_num, group_concat(trans, ' | ')
--FROM merged_translation
--GROUP BY lexentry, written_rep, sense, sense_num
--HAVING count(*) > 1 AND lexentry IS NOT NULL
--LIMIT 60;

DROP VIEW IF EXISTS grouped_translation;
CREATE TEMP VIEW grouped_translation AS
SELECT lexentry, display, display_addition,
    group_concat(sense, ' | ') AS sense_list, min(sense_num) AS min_sense_num, trans_list
FROM (
    SELECT lexentry, display, display_addition, sense, sense_num, group_concat(trans, ' | ') AS trans_list,
        min(trans_entity) AS min_trans_entity
    FROM (
        SELECT lexentry, coalesce(main, written_rep) AS display, addition AS display_addition,
               sense, sense_num, trans, trans_entity
        FROM lang_pair.translation
             JOIN entry USING (lexentry)
             LEFT JOIN lexentry_display USING (lexentry)
        ORDER BY trans_entity
    )
    GROUP BY lexentry, display, display_addition, sense, sense_num
    ORDER BY sense_num, min(trans_entity)
)
GROUP BY lexentry, display, display_addition, trans_list
ORDER BY lexentry, min_trans_entity;

