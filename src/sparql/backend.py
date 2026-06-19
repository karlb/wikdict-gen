"""Run SPARQL queries against the pyoxigraph store and turn the result terms into
rows matching the raw-SQLite contract that process.py consumes.

Replaces the old HTTP-to-Virtuoso layer (make_url / page_through_results). The
namespace stripping, french gloss cleanup, datatype coercion and bad-utf8 handling
are the same transformations the old code applied to Virtuoso's JSON results.
"""

import re

import pyoxigraph

from . import store as store_mod

namespace_re = re.compile(r"^(?:http://kaiko.getalp.org/dbnary/|http://.*#)")
fr_sense_re = re.compile(r"^(.*?)[.]?\s*(?:\(\d+\)|\|\d+)?:?$", re.DOTALL)

XSD = "http://www.w3.org/2001/XMLSchema#"
_INT = XSD + "integer"
_REAL = (XSD + "decimal", XSD + "double")


def cell(term, col, lang):
    """Convert a single result term to the python value stored in the raw db."""
    if term is None:
        return None
    if isinstance(term, pyoxigraph.NamedNode):
        return namespace_re.sub("", term.value)
    # Literal (plain xsd:string, language-tagged, or a typed number)
    datatype = term.datatype.value if isinstance(term, pyoxigraph.Literal) else None
    if datatype == _INT:
        return int(term.value)
    if datatype in _REAL:
        return float(term.value)
    value = term.value
    if col == "sense" and lang and lang.startswith("fr"):
        # remove trailing sense-number references from the french gloss
        match = fr_sense_re.match(value)
        value = match.group(1) if match else value
    # the input contains some badly encoded characters; replace to avoid later errors
    return value.encode("utf-8", "replace").decode()


def get(solution, name):
    """Return the bound term for a variable, or None if absent/unbound."""
    try:
        return solution[name]
    except KeyError:
        return None


def query(reader, sparql, graph=None, union=False):
    """Run a query, scoped to one named `graph` or to the `union` of all graphs.

    All data lives in named graphs, so exactly one of `graph`/`union` must be set,
    otherwise the (empty) default graph would be queried.
    """
    kwargs = {"prefixes": store_mod.PREFIXES}
    if graph is not None:
        kwargs["default_graph"] = [graph]
    elif union:
        kwargs["use_default_graph_as_union"] = True
    else:
        raise ValueError("query needs either graph= or union=True")
    return reader.query(sparql, **kwargs)


def run_query(reader, sparql, columns, lang, graph=None, union=False):
    """Yield one tuple per solution, in `columns` order (a generator, never a list)."""
    for solution in query(reader, sparql, graph=graph, union=union):
        yield tuple(cell(get(solution, col), col, lang) for col in columns)
