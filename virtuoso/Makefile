.PHONY: download gzip insert
.DELETE_ON_ERROR:

LANGS := bg de el en es fi fr id it ja la lt mg nl no pl pt ru sh sv tr ja

all: download gzip insert

insert: $(addprefix ttl/,$(addsuffix .inserted,$(LANGS)))

gzip: $(patsubst ttl/%.bz2,ttl/%.gz,$(wildcard ttl/*.bz2))

# bz2 to gzip, because virtuoso can only load gz
ttl/%.gz: ttl/%.bz2
	bzcat $< | gzip > $@

ttl/%.inserted: ttl/%_dbnary_ontolex.ttl.gz
	./insert_single_ttl.py $*
	touch $@

download:
	wget -r -nd --timestamping --no-parent --accept '*.bz2' --directory-prefix=ttl http://kaiko.getalp.org/static/ontolex/latest/
	ls -l ttl/*.bz2 --time-style=long-iso | awk '{print $$6}' | sort | uniq -c
