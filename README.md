# WikDict dictionary generator

This generator extracts data from a Virtuoso database filled with [dbnary]
data. Details on how to set up such a database can be found in the [virtuoso
directory](virtuoso). The extracted data is then used to generate WikDict
dictionaries. These dictionaries main usage is at the [WikDict
website][wikdict.com].

[dbnary]: http://kaiko.getalp.org/about-dbnary/
[wikdict.com]: http://www.wikdict.com

# Usage
  
After setting up the Virtuoso database, run

    git clone git@github.com:karlb/wikdict-gen.git
    cd wikdict-gen
    make

Use the resulting dictionaries in `dictionaries/wdweb` with [wikdict-web], try a quick lookup using the `search` command like

    src/run.py search de en haus

or use the dictionaries in `dictionaries/generic` for any other use case.

[wikdict-web]: https://github.com/karlb/wikdict-web

# Support

If you encounter problems when building or using dictionaries, please [submit an issue](https://github.com/karlb/wikdict-web/issues) or contact [karl@karl.berlin](mailto:karl@karl.berlin).
