MAKEFLAGS += --no-builtin-rules
# Update with `uv run src/helper.py makefile > generated.mk`
include generated.mk

.PHONY: test extensions download update tei tei-noinfl converted kobo stardict
.SECONDARY:  # keep intermediate files
.DELETE_ON_ERROR:

ALL_PAIRS = $(shell uv run src/helper.py all_pairs)
ALL_LANGS = $(shell uv run src/helper.py all_langs)
ALL_RAW = $(addprefix dictionaries/raw/,$(addsuffix .sqlite3,${ALL_LANGS} ${ALL_PAIRS}))
ALL_PROCESSED_LANGS = $(addprefix dictionaries/processed/,$(addsuffix .sqlite3,${ALL_LANGS}))
ALL_PROCESSED_PAIRS = $(addprefix dictionaries/processed/,$(addsuffix .sqlite3,${ALL_PAIRS}))
ALL_PROCESSED = ${ALL_PROCESSED_LANGS} ${ALL_PROCESSED_PAIRS}
ALL_WDWEB_PAIRS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_PAIRS}))
ALL_WDWEB_LANGS = $(addprefix dictionaries/wdweb/,$(addsuffix .sqlite3,${ALL_LANGS}))
ALL_GENERIC = $(addprefix dictionaries/generic/,$(addsuffix .sqlite3,${ALL_PAIRS}))

WEB_HOST = piku.karl.berlin
RSYNC_FLAGS = -trvz --progress -e ssh

.DEFAULT_GOAL := all
all: wdweb check
raw: ${ALL_RAW} raw-check
processed: ${ALL_PROCESSED}
generic: ${ALL_GENERIC}
wdweb: ${ALL_WDWEB_PAIRS} ${ALL_WDWEB_LANGS}

test:
	uv run -m unittest discover -s src

# On-demand: measure the translation-scoring model (held-out precision/recall).
# Not a build gate; reads the built dictionaries/infer.sqlite3.
evaluate: dictionaries/infer.sqlite3
	uv run src/run.py evaluate --sweep

clean:
	rm -fr dictionaries

dictionaries/infer.sqlite3: ${ALL_PROCESSED}
	rm -f dictionaries/infer.sqlite3
	for langpair in ${ALL_PAIRS}; do uv run src/run.py infer-collect $$langpair; done
	uv run src/run.py infer

# Bulk-load all dbnary dumps into one pyoxigraph store (the union of all editions).
# Rebuilt when any loaded dump changes. Readers (raw extraction) open it read-only,
# so `make -j raw` runs many readers against this one store.
dictionaries/store/.loaded: $(wildcard virtuoso/ttl/*_dbnary_ontolex.ttl.bz2) \
                            $(wildcard virtuoso/ttl/*_dbnary_exolex_ontolex.ttl.bz2) \
                            $(wildcard virtuoso/ttl/*_dbnary_morphology.ttl.bz2)
	uv run src/run.py load-store
	touch $@

# Download the dbnary dumps; the loader reads the .ttl.bz2 directly.
download:
	wget -r -nd --timestamping --no-parent --accept '*.ttl.bz2' \
		--directory-prefix=virtuoso/ttl http://kaiko.getalp.org/static/ontolex/latest/
	# Sanity check: count dumps per modification date. A single date means every
	# edition came from the same dbnary release; a split flags stale/partial dumps.
	ls -l virtuoso/ttl/*.ttl.bz2 --time-style=long-iso | awk '{print $$6}' | sort | uniq -c

# Refresh the dumps, then rebuild everything downstream — in that order. Use this
# instead of `make download wdweb`: download is phony, so it can't be a plain
# prerequisite of the build without re-fetching on every run, and under -j the two
# would otherwise race. The sub-make also re-expands the $(wildcard) below *after*
# the download, so brand-new editions are picked up. `make -j update` still
# parallelizes the build (the sub-make inherits the jobserver).
#
# Finish with `check` so a regression can't ship silently: it runs only after the
# wdweb sub-make returns (separate sub-makes serialize), and check-translations
# exits non-zero — failing `update` — if any edition's definition ratio collapsed.
update: download
	$(MAKE) wdweb
	$(MAKE) check

${ALL_RAW}: dictionaries/raw/%.sqlite3: dictionaries/store/.loaded
	uv run src/run.py raw $*

raw-check:
	for f in dictionaries/raw/*-*.sqlite3 ; do translations=$$(echo "SELECT count(*) FROM translation" | sqlite3 -noheader $$f) ; [ $$translations -eq 0 ] && echo "$$f has no translations!" || true ; done

${ALL_PROCESSED_LANGS}: dictionaries/processed/%.sqlite3: dictionaries/raw/%.sqlite3
	uv run src/run.py process $*

.SECONDEXPANSION:
${ALL_PROCESSED_PAIRS}: dictionaries/processed/%.sqlite3: dictionaries/raw/%.sqlite3 \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst -, ,%)).sqlite3
	uv run src/run.py process $*

${ALL_GENERIC}: dictionaries/generic/%.sqlite3: dictionaries/processed/%.sqlite3 \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/infer.sqlite3
	uv run src/run.py generic $*

.SECONDEXPANSION:
${ALL_WDWEB_PAIRS}: dictionaries/wdweb/%.sqlite3: \
    dictionaries/processed/$$(firstword $$(subst -, ,%)).sqlite3 \
    dictionaries/processed/$$(word 2,$$(subst -, ,%)).sqlite3 \
    dictionaries/generic/%.sqlite3 \
    dictionaries/generic/$$(firstword $$(subst -, ,%))-$$(word 2,$$(subst -, ,%)).sqlite3 \
    dictionaries/infer.sqlite3
	uv run src/run.py wdweb $*

${ALL_WDWEB_LANGS}: dictionaries/wdweb/%.sqlite3: dictionaries/processed/%.sqlite3
	uv run src/run.py wdweb $*

check:
	find . -name '*.sqlite3' -empty | grep . && echo 'WARNING: Empty databases found!' || echo 'Results look ok' ; true
	uv run src/helper.py check-translations

release-web:
	rsync $(RSYNC_FLAGS) dictionaries/wdweb/ $(WEB_HOST):/home/piku/.piku/data/wikdict/$(shell date +%Y-%m)
	ssh $(WEB_HOST) ln -sfT $(shell date +%Y-%m) /home/piku/.piku/data/wikdict/dict

release-sitemap:
	rsync $(RSYNC_FLAGS) sitemap $(WEB_HOST):/home/piku/.piku/data/wikdict/

release-download:
	rsync $(RSYNC_FLAGS) dictionaries/generic/ $(WEB_HOST):hosts/download/dictionaries/sqlite/2_$(shell date +%Y-%m)
	rsync $(RSYNC_FLAGS) dictionaries/processed/??.sqlite3 $(WEB_HOST):hosts/download/dictionaries/sqlite/2_$(shell date +%Y-%m)
	ssh $(WEB_HOST) ln -sfT 2_$(shell date +%Y-%m) hosts/download/dictionaries/sqlite/2

release-tei:
	rsync $(RSYNC_FLAGS) dictionaries/tei/* $(WEB_HOST):hosts/download/dictionaries/tei/recommended
release-tei-noinfl:
	rsync $(RSYNC_FLAGS) dictionaries/tei-noinfl/* $(WEB_HOST):hosts/download/dictionaries/tei/no-infl

dictionaries/kobo/dicthtml-%.zip:
	pyglossary $< $@ --write-format Kobo
dictionaries/stardict/%.zip: dictionaries/stardict/%
	cd $</.. && rm -f `basename $@` && zip -r `basename $@` `basename $<`
dictionaries/stardict/%:
	rm -rf $@
	mkdir -p $@
	pyglossary $< $@/stardict --write-format Stardict

# TEI generation reads the already-built wdweb databases (build them first with
# `make` / `make wdweb`). It is deliberately NOT wired to the wdweb files as
# prerequisites: depending on all 650+ wdweb DBs would make `make converted`
# re-validate the whole upstream pipeline and rebuild it whenever an input merely
# looks stale -- and tei.py itself bumps the processed DBs' mtimes while building
# a scratch index, which would trigger exactly that. A render+convert step should
# consume wdweb, not rebuild it. The default variant includes inflected forms and
# is what kobo/stardict consume; tei-noinfl writes an inflection-free variant to
# dictionaries/tei-noinfl (see release-tei-noinfl).
tei:
	uv run src/tei.py all
tei-noinfl:
	uv run src/tei.py all --no-inflections

# One-call build: generate the (with-inflections) TEI first, then convert it to
# kobo + stardict. The two phases are separate sub-makes so the kobo/stardict
# prerequisite lists below -- which $(shell)-inspect the filesystem for the .tei
# files that exist -- are expanded only after TEI generation finishes ($(shell)
# in a prerequisite is evaluated when that make parses the rule, and the second
# sub-make re-parses after the first returns). No race under -j; the jobserver is
# inherited so the pyglossary conversions still run in parallel. Same pattern as
# the `update` target above.
converted:
	$(MAKE) tei
	$(MAKE) kobo stardict

# Build kobo/stardict only for pairs whose with-inflections .tei exists at the top
# level of dictionaries/tei. Too-small pairs (< 5000 headwords) are written to
# dictionaries/tei/small/ and 0-headword pairs aren't written at all, so
# dictionaries/tei/<codes>.tei is absent for them and they are skipped here -- no
# missing-prerequisite failure, no `make --keep-going` needed.
# NOTE: relies on tei.py's "< 5000 -> small/" split while generated.mk points at
# dictionaries/tei/<codes>.tei; keep the two in sync.
kobo: $(shell awk -F': ' '/kobo\/dicthtml/{print $$1" "$$2}' generated.mk | while read tgt tei; do [ -f "$$tei" ] && echo "$$tgt"; done)
stardict: $(shell awk -F': ' '/stardict/{print $$1" "$$2}' generated.mk | while read tgt tei; do [ -f "$$tei" ] && echo "$$tgt.zip"; done)

release-converted:
	rsync $(RSYNC_FLAGS) dictionaries/kobo/*.zip $(WEB_HOST):hosts/download/dictionaries/kobo
	rsync $(RSYNC_FLAGS) dictionaries/stardict/*.zip $(WEB_HOST):hosts/download/dictionaries/stardict
