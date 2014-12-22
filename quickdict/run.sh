#!/bin/bash
cat tsv/parts/$1-$2* > tsv/$1-$2.tsv
java -Xmx512m -jar DictionaryBuilder.jar \
	--dictOut=dicts/$1-$2.quickdic \
	--lang1=$1 \
	--lang2=$2 \
	--lang1Stoplist=stoplists/$1.txt \
	--lang2Stoplist=stoplists/$2.txt \
	--dictInfo=$1-$2_dictcc_simulated \
	--input1=tsv/$1-$2.tsv \
	--input1Name=dbnary$1 \
	--input1Charset=UTF8 \
	--input1Format=tab_separated
