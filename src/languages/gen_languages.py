#!/usr/bin/env python2
from io import open

language_names = {}
language_codes3 = {}

with open("languages/languages.tsv") as f:
    for line in f:
        fields = line.split("\t")
        language_names[fields[3]] = fields[2].split(",")[0]
        language_codes3[fields[3]] = fields[4]

with open("languages/__init__.py", "w") as f:
    f.write(u"language_names = %r\n\n" % language_names)
    f.write(u"language_codes3 = %r\n\n" % language_codes3)
