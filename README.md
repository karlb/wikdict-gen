# WikDict dictionary generator

This generator extracts data from [dbnary] dumps, which it bulk-loads into an
embedded [pyoxigraph] RDF store (no server or Docker required). The extracted data
is then used to generate WikDict dictionaries. These dictionaries main usage is at
the [WikDict website][wikdict.com].

[dbnary]: http://kaiko.getalp.org/about-dbnary/
[pyoxigraph]: https://pyoxigraph.readthedocs.io/
[wikdict.com]: http://www.wikdict.com

# Usage

    git clone git@github.com:karlb/wikdict-gen.git
    cd wikdict-gen
    make download   # fetch the dbnary dumps (into virtuoso/ttl/)
    make            # load them into the store and build the dictionaries

Use the resulting dictionaries in `dictionaries/wdweb` with [wikdict-web], try a quick lookup using the `search` command like

    src/run.py search de en haus

or use the dictionaries in `dictionaries/generic` for any other use case.

[wikdict-web]: https://github.com/karlb/wikdict-web

# Support

If you encounter problems when building or using dictionaries, please [submit an issue](https://github.com/karlb/wikdict-web/issues) or contact [karl@karl.berlin](mailto:karl@karl.berlin).
