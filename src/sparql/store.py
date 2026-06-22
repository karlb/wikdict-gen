"""Embedded pyoxigraph store: bulk-load dbnary TTL dumps and open them for querying.

Replaces the Virtuoso/Docker setup. A single writer builds an on-disk RocksDB store
from every edition's dumps, loaded into the *default* graph so queries see the union
of all editions (reproducing Virtuoso's ``default-graph-uri=""``). Raw extraction
opens the store read-only, which takes no lock, so ``make -j`` can run many readers
concurrently.
"""

import bz2
import os
import resource
import shutil
import time
from glob import glob

import pyoxigraph

from helper import dict_dir

TTL_DIR = "virtuoso/ttl"


def _store_path():
    """Path to the on-disk pyoxigraph store, resolved per call.

    ``WIKDICT_STORE`` overrides it; otherwise it lives under the output root
    (``WIKDICT_DICT_DIR``, default ``dictionaries``), so redirecting that one env
    var moves the store too.
    """
    return os.environ.get("WIKDICT_STORE") or f"{dict_dir()}/store"

# Only the dump types the SPARQL queries actually touch: ontolex (entries, senses,
# translations), exolex_ontolex (foreign-language entries other editions contribute
# to the union) and morphology (inflected forms). lime/etymology/statistics/
# enhancement are never queried, so we skip them.
LOADED_DUMP_TYPES = ("ontolex", "exolex_ontolex", "morphology")

# Namespace prefixes. Virtuoso declared these globally (XML_SET_NS_DECL); standards
# compliant oxigraph needs them per query, so we pass this map to Store.query().
PREFIXES = {
    "ontolex": "http://www.w3.org/ns/lemon/ontolex#",
    "dct": "http://purl.org/dc/terms/",
    "lexvo": "http://lexvo.org/id/iso639-3/",
    "lexinfo": "http://www.lexinfo.net/ontology/2.0/lexinfo#",
    "olia": "http://purl.org/olia/olia.owl#",
    "dbnary": "http://kaiko.getalp.org/dbnary#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


def edition_graph(lang):
    """Named graph holding one edition's dumps (keyed by 2-letter edition code).

    Each edition lives in its own graph so single-edition queries (forms,
    translations) can be scoped to one graph instead of scanning the whole store,
    while cross-edition queries (entry/pos/...) query the union of all graphs.
    """
    return pyoxigraph.NamedNode(f"urn:wikdict:edition:{lang}")


def ttl_files(ttl_dir=TTL_DIR):
    """(edition, path) for every dump present on disk for the loaded types.

    Editions are whatever is on disk (incl. sh/et), so every edition present
    contributes to the union, matching the Virtuoso setup which loaded all of them.
    """
    files = []
    for dump_type in LOADED_DUMP_TYPES:
        for path in sorted(glob(os.path.join(ttl_dir, f"*_dbnary_{dump_type}.ttl.bz2"))):
            edition = os.path.basename(path).split("_", 1)[0]
            files.append((edition, path))
    return files


# RocksDB's bulk load keeps every SST file of the store open at once (~1670 for the
# full store today), so the common systemd default soft limit of 1024 aborts the
# load with "Too many open files". 65536 leaves ~40x headroom. We deliberately do not
# raise it to the hard maximum: the soft limit stays low by design so code using
# select()/FD_SETSIZE keeps working, so we lift it only to what the load needs.
_FD_TARGET = 65536


def _raise_fd_limit():
    """Lift the open-file soft limit to ``_FD_TARGET`` if it is lower (capped at hard).

    Inherited soft limits vary by launching shell, so we fix it here rather than
    relying on the caller's ``ulimit``.
    """
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < _FD_TARGET:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(_FD_TARGET, hard), hard))


def build_store(ttl_dir=TTL_DIR, store_path=None):
    """(Re)build the on-disk store, each edition's dumps in its own named graph."""
    store_path = store_path or _store_path()
    files = ttl_files(ttl_dir)
    if not files:
        raise SystemExit(f"No TTL dumps found in {ttl_dir!r}")

    _raise_fd_limit()
    shutil.rmtree(store_path, ignore_errors=True)  # never query a stale/partial store
    parent = os.path.dirname(store_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    store = pyoxigraph.Store(store_path)  # writer: takes the exclusive RocksDB lock
    start = time.time()
    for edition, path in files:
        t0 = time.time()
        with bz2.open(path, "rb") as fh:
            # lenient=True skips IRI/lexical validation so a single malformed IRI in a
            # dump (e.g. a stray variation selector) doesn't abort the whole load, as
            # Virtuoso tolerated.
            store.bulk_load(
                fh,
                format=pyoxigraph.RdfFormat.TURTLE,
                to_graph=edition_graph(edition),
                lenient=True,
            )
        print(f"  loaded {os.path.basename(path)} in {time.time() - t0:.1f}s")

    store.flush()
    total = len(store)
    print(
        f"Loaded {total:,} triples from {len(files)} files "
        f"in {time.time() - start:.0f}s into {store_path}"
    )
    del store  # release the lock and finalize before the Makefile touches the sentinel


def open_reader(store_path=None):
    """Open the store read-only (no lock) so many ``make -j`` readers can coexist."""
    store_path = store_path or _store_path()
    if not os.path.isdir(store_path):
        raise SystemExit(
            f"Store {store_path!r} not found - run `uv run src/run.py load-store` first"
        )
    return pyoxigraph.Store.read_only(store_path)
