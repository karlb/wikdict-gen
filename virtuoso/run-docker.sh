#!/bin/sh

# If the container has already been run, start it with
# docker container start wikdict-virtuoso -a

docker run \
	--name wikdict-virtuoso \
	-p 8890:8890 -p 1111:1111 \
	-v data:/data \
	--mount type=bind,source=$PWD/ttl,target=/ttl \
	`# Allow loading files from the "ttl" dir` \
	-e VIRT_Parameters_DirsAllowed=/ttl \
	`# Allow large and slow queries` \
	-e VIRT_SPARQL_ResultSetMaxRows=0 \
	-e VIRT_SPARQL_MaxQueryCostEstimationTime=0 \
	-e VIRT_SPARQL_MaxQueryExecutionTime=0 \
	--cpu-shares 512 \
	tenforce/virtuoso
