-- Views for single languages

-- When searching in two languages, the more popular one will have
-- the higher importance scores for words. To show at least some
-- results from the less poplular language, we normalize the scores
-- for the typeahead and similar features
DROP VIEW IF EXISTS rel_importance;
CREATE TEMP VIEW rel_importance AS
SELECT vocable, score, score / high_score AS rel_score
FROM importance, (
    SELECT avg(score) AS high_score
    FROM (
        SELECT * FROM importance
        ORDER BY score DESC LIMIT 10000
    )
);
