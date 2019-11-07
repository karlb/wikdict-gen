#!/bin/bash
wget -r -nd --timestamping --no-parent --accept '*.bz2' --directory-prefix=ttl http://kaiko.getalp.org/static/ontolex/latest/
#wget -r -nd --timestamping --no-parent --accept '*.bz2' --directory-prefix=ttl http://kaiko.getalp.org/static/lemon/latest/
#wget -r -nd --timestamping --no-parent --accept '*.bz2' --directory-prefix=ttl http://kaiko.getalp.org/static/lemon/disambiguated-translations/latest/
ls -l ttl/*.bz2 --time-style=long-iso | awk '{print $6}' | sort | uniq -c
