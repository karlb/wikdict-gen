# WikDict Virtoso

Information and scripts on how to set up an OpenLink Virtuoso server for usage with WikDict-gen.

## Running a Virtuoso Server

By far the easiest way to run a properly configured Virtuoso Server is using
docker. The `run-docker.sh` script provides all parameters and should be run
from this directory.

## Download data and insert it into the Virtuoso database

Now we can start using the Makefile in the repo to do the real work. First let's download all dbnary .ttl files wee need.

    make download

With the ttl files on disk, we can load it into Virtuoso.

    make

These two steps are meant to be run whenever you want to refresh your database content. They should properly delete old data before inserting new data and only download .ttl files which changed in the mean time.
