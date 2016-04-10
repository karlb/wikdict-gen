# WikDict dictionary generator

This generator extracts data from a virtuoso database filled with [dbnary] data. Details on how to set up such a database can be found in the [wikdict-virtuoso repository][wd-virt], or you can [ask me][mail] for access to a running server. The extracted data is then used to generate WikDict dictionaries. Currently, these dictionaries are only used by the [WikDict website][wikdict.com].

[dbnary]: kaiko.getalp.org/about-dbnary/
[wd-virt]: https://bitbucket.org/wikdict/wikdict-virtuoso
[wikdict.com]: http://www.wikdict.com
[mail]: karl42@gmail.com

# Usage

    hg clone https://bitbucket.org/wikdict/wikdict-gen
    cd wikdict-gen/generator
    ./run.py complete_lang all 
    ./run.py complete_pair all

Use the resulting dictionaries in `dictionaries/sqlite/prod` with [wikdict-web], or try a quick lookup using the `search` command like

    ./run.py search de en haus

[wikdict-web]: https://bitbucket.org/wikdict/wikdict-web
