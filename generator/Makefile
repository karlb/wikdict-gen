
.PHONY: test
.SECONDARY:  # keep intermediate files

ALL_PAIRS = $(shell python3 helper.py all_pairs)
ALL_LANGS = $(shell python3 helper.py all_langs)
ALL_RAW = $(addprefix dictionaries/raw/,$(addsuffix .sqlite3,${ALL_LANGS} ${ALL_PAIRS}))
ALL_PROCESSED = $(addprefix dictionaries/processed/,$(addsuffix .sqlite3,${ALL_LANGS} ${ALL_PAIRS}))
ALL_WDWEB_PAIRS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_PAIRS}))
ALL_WDWEB_LANGS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_LANGS}))

all: ${ALL_WDWEB_PAIRS}

test:
	python3 -m unittest tests.test_parse

${ALL_RAW}: dictionaries/raw/%.sqlite3: 
	./run.py raw $*

${ALL_PROCESSED}: dictionaries/processed/%.sqlite3: dictionaries/raw/%.sqlite3
	./run.py process $*

.SECONDEXPANSION:
${ALL_WDWEB_PAIRS}: dictionaries/wdweb/%.sqlite3: \
    dictionaries/processed/%.sqlite3 \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst ., ,$$(subst -, ,$$@)))-$$(firstword $$(subst -, ,$$(notdir $$@))).sqlite3
	./run.py wdweb $*

.DELETE_ON_ERROR:
${ALL_WDWEB_LANGS}: dictionaries/wdweb/%.sqlite3: dictionaries/processed/%.sqlite3
	./run.py wdweb $*
