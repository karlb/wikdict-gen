#!/bin/bash
for LANG in bg de el en es fi fr id it ja la lt mg nl no pl pt ru sh sv tr ja
do
	echo Loading $LANG
	./insert_single_ttl.py $LANG
done
#ls -1 ttl/* | cut -d '/' -f 2 | cut -d '_' -f 1 | uniq | xargs -n1 script/insert_single_ttl.py
