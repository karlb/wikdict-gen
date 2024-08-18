SHELL=/bin/bash -o pipefail
.PHONY: download gzip insert virtuoso-start virtuoso-clean
.DELETE_ON_ERROR:

LANGS := bg ca de el en es fi fr ga id it ja ku la lt mg nl no pl pt ru sh sv tr zh

all: download gzip insert

insert: $(addprefix ttl/,$(addsuffix .inserted,$(LANGS)))

gzip: $(patsubst ttl/%.bz2,ttl/%.gz,$(wildcard ttl/*.bz2))

# bz2 to gzip, because virtuoso can only load gz
ttl/%.gz: ttl/%.bz2
	bzcat $< | gzip > $@

ttl/%.inserted: ttl/%_dbnary_ontolex.ttl.gz
	./insert_single_ttl.py $*
	touch $@

# Inserting into virtuoso in parallel can overload the database
.NOTPARALLEL: ttl/%.inserted

download:
	wget -r -nd --timestamping --no-parent --accept '*.ttl.bz2' --directory-prefix=ttl http://kaiko.getalp.org/static/ontolex/latest/
	ls -l ttl/*.bz2 --time-style=long-iso | awk '{print $$6}' | sort | uniq -c

virtuoso-start:
	# If the container has already been run, start it with
	# docker container start wikdict-virtuoso -a
	docker run \
		--name wikdict-virtuoso \
		-p 8890:8890 -p 1111:1111 \
		-v data:/data \
		--mount type=bind,source=$$PWD/ttl,target=/ttl \
		`# Allow loading files from the "ttl" dir` \
		-e VIRT_Parameters_DirsAllowed=/ttl \
		`# Allow large and slow queries` \
		-e VIRT_SPARQL_ResultSetMaxRows=0 \
		-e VIRT_SPARQL_MaxQueryCostEstimationTime=0 \
		-e VIRT_SPARQL_MaxQueryExecutionTime=0 \
		--cpu-shares 512 \
		tenforce/virtuoso

virtuoso-clean:
	docker container rm wikdict-virtuoso && docker volume rm data
