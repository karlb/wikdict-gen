
.PHONY: test extensions
.SECONDARY:  # keep intermediate files
.DELETE_ON_ERROR:

ALL_PAIRS = $(shell python3 helper.py all_pairs)
ALL_LANGS = $(shell python3 helper.py all_langs)
ALL_RAW = $(addprefix dictionaries/raw/,$(addsuffix .sqlite3,${ALL_LANGS} ${ALL_PAIRS}))
ALL_PROCESSED_LANGS = $(addprefix dictionaries/processed/,$(addsuffix .sqlite3,${ALL_LANGS}))
ALL_PROCESSED_PAIRS = $(addprefix dictionaries/processed/,$(addsuffix .sqlite3,${ALL_PAIRS}))
ALL_PROCESSED = ${ALL_PROCESSED_LANGS} ${ALL_PROCESSED_PAIRS}
ALL_WDWEB_PAIRS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_PAIRS}))
ALL_WDWEB_LANGS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_LANGS}))
ALL_GENERIC = $(addprefix dictionaries/generic/,$(addsuffix .sqlite3,${ALL_PAIRS}))

all: ${ALL_WDWEB_PAIRS} ${ALL_WDWEB_LANGS} ${ALL_GENERIC} ${ALL_PROCESSED} ${ALL_RAW} check
raw: ${ALL_RAW}
processed: ${ALL_PROCESSED}
generic: ${ALL_GENERIC}

test:
	python3 -m unittest tests.test_parse tests.test_infer

clean:
	rm dictionaries/*/*

dictionaries/infer.sqlite3: ${ALL_PROCESSED}
	rm -f dictionaries/infer.sqlite3
	for langpair in ${ALL_PAIRS}; do ./run.py infer-collect $$langpair; done
	./run.py infer

${ALL_RAW}: dictionaries/raw/%.sqlite3: 
	./run.py raw $*

${ALL_PROCESSED_LANGS}: dictionaries/processed/%.sqlite3: dictionaries/raw/%.sqlite3
	./run.py process $*

.SECONDEXPANSION:
${ALL_PROCESSED_PAIRS}: dictionaries/processed/%.sqlite3: dictionaries/raw/%.sqlite3 \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst -, ,%)).sqlite3
	./run.py process $*

${ALL_GENERIC}: dictionaries/generic/%.sqlite3: dictionaries/processed/%.sqlite3 dictionaries/infer.sqlite3 
	./run.py generic $*

.SECONDEXPANSION:
${ALL_WDWEB_PAIRS}: dictionaries/wdweb/%.sqlite3: \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst -, ,%)).sqlite3 \
    dictionaries/generic/%.sqlite3 \
    dictionaries/infer.sqlite3
    #dictionaries/generic/$$(word 2,$$(subst ., ,$$(subst -, ,$$@)))-$$(firstword $$(subst -, ,$$(notdir $$@))).sqlite3
	./run.py wdweb $*

${ALL_WDWEB_LANGS}: dictionaries/wdweb/%.sqlite3: dictionaries/processed/%.sqlite3
	./run.py wdweb $*

extensions:
	python3 -c "`wget -qO- https://bitbucket.org/!api/2.0/snippets/karlb/j6gxM/38eff66f830e1c96b99e2ebb1312cae13c772c34/files/make_sqlite_ext.py`" lib spellfix icu

check:
	find . -name '*.sqlite3' -empty | grep . && echo 'WARNING: Empty databases found!'
