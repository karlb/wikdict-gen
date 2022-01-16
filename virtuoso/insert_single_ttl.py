#!/usr/bin/env python3
import sys
import os
from glob import glob
from subprocess import check_call, Popen, PIPE

from languages import language_codes3

os.chdir("ttl")
lang = sys.argv[1]

# call isql to do the actual loading
print("load " + lang)
isql_code = """
    -- remove old prefix dcterms, since we want to bind it to 'dct', now (same as kaiko.getalp.org)
    DB.DBA.XML_REMOVE_NS_BY_PREFIX('dcterms', 2);
    -- set namespaces, needs to be only done once, but redoing doesn't do any harm
    DB.DBA.XML_SET_NS_DECL ('lexinfo', 'http://www.lexinfo.net/ontology/2.0/lexinfo#', 2);
    DB.DBA.XML_SET_NS_DECL ('lexvo', 'http://lexvo.org/id/iso639-3/', 2);
    DB.DBA.XML_SET_NS_DECL ('lemon', 'http://lemon-model.net/lemon#', 2);
    DB.DBA.XML_SET_NS_DECL ('dbnary', 'http://kaiko.getalp.org/dbnary#', 2);
    DB.DBA.XML_SET_NS_DECL ('olia', 'http://purl.org/olia/olia.owl#', 2);
    -- new ontolex namespaces
    DB.DBA.XML_SET_NS_DECL ('ontolex', 'http://www.w3.org/ns/lemon/ontolex#', 2);
    DB.DBA.XML_SET_NS_DECL ('synsem', 'http://www.w3.org/ns/lemon/synsem#', 2);
    DB.DBA.XML_SET_NS_DECL ('decomp', 'http://www.w3.org/ns/lemon/decomp#', 2);
    DB.DBA.XML_SET_NS_DECL ('vartrans', 'http://www.w3.org/ns/lemon/vartrans#', 2);
    DB.DBA.XML_SET_NS_DECL ('lime', 'http://www.w3.org/ns/lemon/lime#', 2);
    DB.DBA.XML_SET_NS_DECL ('dct', 'http://purl.org/dc/terms/', 2);
    DB.DBA.XML_SET_NS_DECL ('skos', 'http://www.w3.org/2004/02/skos/core#', 2);
    DB.DBA.XML_SET_NS_DECL ('rdfs', 'http://www.w3.org/2000/01/rdf-schema#', 2);
    DB.DBA.XML_SET_NS_DECL ('rdf', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#', 2);
    DB.DBA.XML_SET_NS_DECL ('xs', 'http://www.w3.org/2001/XMLSchema#', 2);

    -- set namespace for current language
    DB.DBA.XML_SET_NS_DECL('dbnary-%(lang3)s',
                           'http://kaiko.getalp.org/dbnary/%(lang3)s', 2);

    -- clear old data
    SPARQL CLEAR GRAPH <http://kaiko.getalp.org/dbnary/%(lang3)s>;
    DELETE FROM DB.DBA.LOAD_LIST;

    -- add files to load_list
    ld_dir('%(dir)s', '%(lang)s_*.ttl.gz', 'http://kaiko.getalp.org/dbnary/%(lang3)s');
    ld_dir('%(dir)s', '%(lang3)s_*.ttl.gz', 'http://kaiko.getalp.org/dbnary/%(lang3)s');
    SELECT * FROM DB.DBA.LOAD_LIST;

    -- load
    rdf_loader_run();

    -- commit
    checkpoint;
    commit WORK;
    checkpoint;
    EXIT;
""" % dict(
    lang=lang, lang3=language_codes3[lang], dir="/ttl"
)
p = Popen(("docker exec -i wikdict-virtuoso isql-v").split(" "), stdin=PIPE)
p.communicate(input=bytes(isql_code, encoding="utf8"))
if p.returncode:
    print("isql failed")
    exit(1)
else:
    print("success")
