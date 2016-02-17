DROP TABLE IF EXISTS lang_pair;
CREATE TABLE lang_pair (
    from_lang text,
    to_lang text,
    translations int,
    reverse_translations int,
    forms int,
    PRIMARY KEY (from_lang, to_lang)
);
