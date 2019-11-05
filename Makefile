
.PHONY: test extensions
.SECONDARY:  # keep intermediate files
.DELETE_ON_ERROR:

ALL_PAIRS = $(shell python3 src/helper.py all_pairs)
ALL_LANGS = $(shell python3 src/helper.py all_langs)
ALL_RAW = $(addprefix dictionaries/raw/,$(addsuffix .sqlite3,${ALL_LANGS} ${ALL_PAIRS}))
ALL_PROCESSED_LANGS = $(addprefix dictionaries/processed/,$(addsuffix .sqlite3,${ALL_LANGS}))
ALL_PROCESSED_PAIRS = $(addprefix dictionaries/processed/,$(addsuffix .sqlite3,${ALL_PAIRS}))
ALL_PROCESSED = ${ALL_PROCESSED_LANGS} ${ALL_PROCESSED_PAIRS}
ALL_WDWEB_PAIRS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_PAIRS}))
ALL_WDWEB_LANGS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_LANGS}))
ALL_GENERIC = $(addprefix dictionaries/generic/,$(addsuffix .sqlite3,${ALL_PAIRS}))

all: venv ${ALL_WDWEB_PAIRS} ${ALL_WDWEB_LANGS} ${ALL_GENERIC} ${ALL_PROCESSED} ${ALL_RAW} check
raw: ${ALL_RAW}
processed: ${ALL_PROCESSED}
generic: ${ALL_GENERIC}

test:
	python3 -m unittest tests.test_parse tests.test_infer

clean:
	rm dictionaries/*/*

distclean: clean
	rm -fr venv

dictionaries/infer.sqlite3: ${ALL_PROCESSED}
	rm -f dictionaries/infer.sqlite3
	for langpair in ${ALL_PAIRS}; do src/run.py infer-collect $$langpair; done
	src/run.py infer

${ALL_RAW}: dictionaries/raw/%.sqlite3:
	src/run.py raw $*

${ALL_PROCESSED_LANGS}: dictionaries/processed/%.sqlite3: dictionaries/raw/%.sqlite3
	src/run.py process $*

.SECONDEXPANSION:
${ALL_PROCESSED_PAIRS}: dictionaries/processed/%.sqlite3: dictionaries/raw/%.sqlite3 \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst -, ,%)).sqlite3
	src/run.py process $*

${ALL_GENERIC}: dictionaries/generic/%.sqlite3: dictionaries/processed/%.sqlite3 dictionaries/infer.sqlite3 
	src/run.py generic $*

.SECONDEXPANSION:
${ALL_WDWEB_PAIRS}: dictionaries/wdweb/%.sqlite3: \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst -, ,%)).sqlite3 \
    dictionaries/generic/%.sqlite3 \
    dictionaries/infer.sqlite3
    #dictionaries/generic/$$(word 2,$$(subst ., ,$$(subst -, ,$$@)))-$$(firstword $$(subst -, ,$$(notdir $$@))).sqlite3
	src/run.py wdweb $*

${ALL_WDWEB_LANGS}: dictionaries/wdweb/%.sqlite3: dictionaries/processed/%.sqlite3
	src/run.py wdweb $*

venv:
	python3 -m venv venv
	CFLAGS='-DSQLITE_ENABLE_ICU' CPPFLAGS=`pkg-config --cflags icu-uc icu-uc icu-i18n` LDFLAGS=`pkg-config --libs icu-uc icu-uc icu-i18n` venv/bin/pip install git+git://github.com/karlb/pysqlite3
	#CFLAGS='-DSQLITE_ENABLE_ICU' CPPFLAGS=`icu-config --cppflags` LDFLAGS=`icu-config --ldflags` venv/bin/pip install git+git://github.com/karlb/pysqlite3
	venv/bin/pip install -r requirements.txt

check:
	find . -name '*.sqlite3' -empty | grep . && echo 'WARNING: Empty databases found!' || echo 'Results look ok' ; true

release-web:
	rsync -avz --progress -e ssh dictionaries/wdweb/ www.wikdict.com:wikdict-prod/data/$(shell date +%Y-%m)
	#scp -rC dictionaries/wdweb/ www.wikdict.com:wikdict-prod/data/$(shell date +%Y-%m)
	ssh www.wikdict.com ln -sfT $(shell date +%Y-%m) wikdict-prod/data/dict

release-download:
	rsync -avz --progress -e ssh dictionaries/generic www.wikdict.com:hosts/download/dictionaries/sqlite/2_$(shell date +%Y-%m)
	rsync -avz --progress -e ssh dictionaries/processed/??.sqlite3 www.wikdict.com:hosts/download/dictionaries/sqlite/2_$(shell date +%Y-%m)
	ssh www.wikdict.com ln -sfT 2_$(shell date +%Y-%m) hosts/download/dictionaries/sqlite/2

release-tei:
	rsync -avz --progress -e ssh dictionaries/tei/* www.wikdict.com:hosts/download/dictionaries/tei/recommended
